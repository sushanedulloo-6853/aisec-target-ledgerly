import io
import json
from types import SimpleNamespace

from ledgerly.services import ingestion, rag
from tests.conftest import auth, text_response

FIELDS = {
    "doc_type": "invoice",
    "vendor_name": "Packright Supplies",
    "invoice_number": "PR-778",
    "total": 129.99,
    "currency": "USD",
    "due_date": "2026-12-01",
    "vendor_bank_account_number": None,
    "vendor_bank_routing_number": None,
    "summary": "Packaging supplies",
}


def test_upload_text_invoice(client, fake_openai, fake_llama, db):
    fake_openai.responses.queue.append(text_response(json.dumps(FIELDS)))
    data = {"file": (io.BytesIO(b"INVOICE PR-778\nBoxes x200\nTotal 129.99"), "pr-778.txt")}
    r = client.post("/api/documents/upload", data=data, headers=auth("b1_employee"), content_type="multipart/form-data")
    assert r.status_code == 201, r.json
    doc = db.execute("SELECT * FROM documents WHERE id = ?", (r.json["document_id"],)).fetchone()
    assert doc["business_id"] == 1 and doc["total_cents"] == 12999 and doc["indexed"] == 1
    schema_call = fake_openai.responses.calls[0]
    assert schema_call["text"]["format"]["type"] == "json_schema"


def test_upload_rejects_unknown_extension(client):
    data = {"file": (io.BytesIO(b"MZ..."), "payload.exe")}
    r = client.post("/api/documents/upload", data=data, headers=auth("b1_owner"), content_type="multipart/form-data")
    assert r.status_code == 400


def test_new_vendor_created(client, fake_openai, fake_llama, db):
    fields = dict(FIELDS, vendor_name="Sunny Eggs Farm")
    fake_openai.responses.queue.append(text_response(json.dumps(fields)))
    data = {"file": (io.BytesIO(b"eggs"), "eggs.txt")}
    r = client.post("/api/documents/upload", data=data, headers=auth("b1_owner"), content_type="multipart/form-data")
    vendor = db.execute("SELECT * FROM vendors WHERE id = ?", (r.json["vendor_id"],)).fetchone()
    assert vendor["name"] == "Sunny Eggs Farm" and vendor["business_id"] == 1


def test_ingest_from_url(client, fake_openai, fake_llama, monkeypatch):
    page = "<html><body><h1>Receipt</h1><script>x()</script><p>Total 12.00</p></body></html>"
    monkeypatch.setattr(
        ingestion.requests,
        "get",
        lambda url, **kw: SimpleNamespace(
            text=page, content=page.encode(), headers={"Content-Type": "text/html"}, raise_for_status=lambda: None
        ),
    )
    fake_openai.responses.queue.append(text_response(json.dumps(dict(FIELDS, doc_type="receipt"))))
    r = client.post("/api/documents/from-url", json={"url": "https://receipts.example/r/1"}, headers=auth("b2_owner"))
    assert r.status_code == 201
    assert "Total 12.00" in r.json["preview"] and "x()" not in r.json["preview"]


def test_url_scheme_checked(client):
    r = client.post("/api/documents/from-url", json={"url": "file:///etc/passwd"}, headers=auth("b1_owner"))
    assert r.status_code == 400


def test_search_is_filtered_by_business(app, fake_llama):
    with app.app_context():
        hits = rag.search(1, "invoice total", top_k=10)
    assert hits and all(h["filename"] in {"golden-mill-inv-20931.txt", "lease-renewal-2026.txt"} for h in hits)


def test_ask_returns_escaped_html(client, fake_llama):
    r = client.post("/api/documents/ask", json={"question": "When is rent due?"}, headers=auth("b1_owner"))
    assert r.status_code == 200
    assert "answer" in r.json and "sources" in r.json
    assert "<script" not in r.json["answer_html"]


def test_copilot_document_search_tool(client, fake_openai, fake_llama):
    from tests.conftest import tool_response

    fake_openai.responses.queue += [tool_response(("search_documents", {"query": "insurance"})), text_response("ok")]
    client.post("/api/copilot/chat", json={"message": "insurance?"}, headers=auth("b2_owner"))
    out = fake_openai.responses.calls[1]["input"][-1]["output"]
    assert "NW-GL-4410" in out and "GM-20931" not in out
