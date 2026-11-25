"""Invoice / receipt ingestion: extract text + fields, sync vendor, index for Q&A."""

import base64
import io
import json
import re
from html.parser import HTMLParser

import requests
from pypdf import PdfReader

from ledgerly import llm
from ledgerly.services import rag

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".html", ".htm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_EXTENSIONS = TEXT_EXTENSIONS | IMAGE_EXTENSIONS | {".pdf"}

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "doc_type": {"type": "string", "enum": ["invoice", "receipt", "contract", "statement", "other"]},
        "vendor_name": {"type": ["string", "null"]},
        "invoice_number": {"type": ["string", "null"]},
        "total": {"type": ["number", "null"]},
        "currency": {"type": ["string", "null"]},
        "due_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
        "vendor_bank_account_number": {"type": ["string", "null"]},
        "vendor_bank_routing_number": {"type": ["string", "null"]},
        "summary": {"type": "string"},
    },
    "required": [
        "doc_type",
        "vendor_name",
        "invoice_number",
        "total",
        "currency",
        "due_date",
        "vendor_bank_account_number",
        "vendor_bank_routing_number",
        "summary",
    ],
    "additionalProperties": False,
}

EXTRACT_INSTRUCTIONS = (
    "Extract bookkeeping fields from this document for a small business. "
    "If the document lists payment / remittance details for the vendor, include them."
)


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        self._skip = tag in ("script", "style")

    def handle_endtag(self, tag):
        self._skip = False

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return "\n".join(parser.parts)


def text_from_upload(filename: str, data: bytes) -> tuple[str | None, str | None]:
    """Returns (text, image_data_url)."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == ".pdf":
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages), None
    if ext in (".html", ".htm"):
        return html_to_text(data.decode("utf-8", errors="replace")), None
    if ext in TEXT_EXTENSIONS:
        return data.decode("utf-8", errors="replace"), None
    if ext in IMAGE_EXTENSIONS:
        mime = "image/jpeg" if ext in (".jpg", ".jpeg") else f"image/{ext[1:]}"
        return None, f"data:{mime};base64,{base64.b64encode(data).decode()}"
    raise ValueError(f"unsupported file type {ext}")


def fetch_url(url: str) -> str:
    if not re.match(r"^https?://", url, re.IGNORECASE):
        raise ValueError("only http(s) links are supported")
    resp = requests.get(url, timeout=15, headers={"User-Agent": "LedgerlyFetcher/1.0"})
    resp.raise_for_status()
    ctype = resp.headers.get("Content-Type", "")
    if "pdf" in ctype:
        return text_from_upload("remote.pdf", resp.content)[0]
    if "html" in ctype:
        return html_to_text(resp.text)
    return resp.text


def extract_fields(text: str | None, image_url: str | None) -> dict:
    content: list[dict] = [{"type": "input_text", "text": EXTRACT_INSTRUCTIONS}]
    if text:
        content.append({"type": "input_text", "text": text[:50_000]})
    if image_url:
        content.append({"type": "input_image", "image_url": image_url})
    resp = llm.respond(
        "extraction",
        input=[{"role": "user", "content": content}],
        text={"format": {"type": "json_schema", "name": "document_fields", "schema": EXTRACTION_SCHEMA, "strict": True}},
        max_output_tokens=800,
    )
    return json.loads(resp.output_text)


def _sync_vendor(conn, business_id: int, fields: dict) -> int | None:
    name = (fields.get("vendor_name") or "").strip()
    if not name:
        return None
    vendor = conn.execute(
        "SELECT * FROM vendors WHERE business_id = ? AND lower(name) = lower(?)", (business_id, name)
    ).fetchone()
    acct = fields.get("vendor_bank_account_number")
    routing = fields.get("vendor_bank_routing_number")
    if vendor is None:
        cur = conn.execute(
            "INSERT INTO vendors (business_id, name, bank_account_number, bank_routing_number) VALUES (?, ?, ?, ?)",
            (business_id, name, acct, routing),
        )
        return cur.lastrowid
    if acct and acct != vendor["bank_account_number"]:
        # keep remittance details current with the latest invoice
        conn.execute(
            "UPDATE vendors SET bank_account_number = ?, bank_routing_number = COALESCE(?, bank_routing_number),"
            " updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (acct, routing, vendor["id"]),
        )
    return vendor["id"]


def ingest(conn, user: dict, source: str, filename: str, text: str | None, image_url: str | None = None) -> dict:
    fields = extract_fields(text, image_url)
    body = text or fields.get("summary") or ""
    total = fields.get("total")
    cur = conn.execute(
        "INSERT INTO documents (business_id, uploaded_by, source, filename, doc_type, vendor_name, invoice_number,"
        " total_cents, due_date, extracted_json, text_content) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            user["business_id"],
            user["id"],
            source,
            filename,
            fields.get("doc_type"),
            fields.get("vendor_name"),
            fields.get("invoice_number"),
            round(total * 100) if total is not None else None,
            fields.get("due_date"),
            json.dumps(fields),
            body,
        ),
    )
    doc_id = cur.lastrowid
    vendor_id = _sync_vendor(conn, user["business_id"], fields)
    conn.commit()

    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    rag.add_document(row)
    conn.execute("UPDATE documents SET indexed = 1 WHERE id = ?", (doc_id,))
    conn.commit()
    return {"document_id": doc_id, "vendor_id": vendor_id, "fields": fields}
