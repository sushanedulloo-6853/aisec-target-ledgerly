from pathlib import Path

from flask import Blueprint, g, jsonify, request
from markupsafe import escape
from werkzeug.utils import secure_filename

from ledgerly.auth import require_auth
from ledgerly.config import settings
from ledgerly.db import get_db, rows_to_dicts
from ledgerly.services import ingestion, rag

bp = Blueprint("documents", __name__, url_prefix="/api/documents")


@bp.get("")
@require_auth()
def list_documents():
    rows = get_db().execute(
        "SELECT id, source, filename, doc_type, vendor_name, invoice_number, total_cents, due_date, created_at"
        " FROM documents WHERE business_id = ? ORDER BY id DESC",
        (g.user["business_id"],),
    ).fetchall()
    return jsonify(rows_to_dicts(rows))


@bp.post("/upload")
@require_auth()
def upload():
    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify(error="file is required"), 400
    filename = secure_filename(file.filename)
    ext = Path(filename).suffix.lower()
    if ext not in ingestion.ALLOWED_EXTENSIONS:
        return jsonify(error=f"unsupported file type {ext}"), 400
    data = file.read()
    upload_dir = Path(settings.UPLOAD_DIR) / str(g.user["business_id"])
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / filename).write_bytes(data)

    text, image_url = ingestion.text_from_upload(filename, data)
    result = ingestion.ingest(get_db(), g.user, "upload", filename, text, image_url)
    return jsonify(result), 201


@bp.post("/from-url")
@require_auth()
def from_url():
    body = request.get_json(force=True) or {}
    url = (body.get("url") or "").strip()
    try:
        text = ingestion.fetch_url(url)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception as exc:
        return jsonify(error=f"could not fetch document: {exc}"), 502
    result = ingestion.ingest(get_db(), g.user, "url", url, text)
    result["preview"] = text[:2000]
    return jsonify(result), 201


@bp.post("/ask")
@require_auth()
def ask():
    body = request.get_json(force=True) or {}
    question = (body.get("question") or "").strip()
    if not question:
        return jsonify(error="question is required"), 400
    result = rag.ask(g.user["business_id"], g.user["business_name"], question)
    result["answer_html"] = str(escape(result["answer"])).replace("\n", "<br>")
    return jsonify(result)
