import json

from flask import Blueprint, g, jsonify, request

from ledgerly import worker
from ledgerly.auth import require_auth
from ledgerly.db import get_db

bp = Blueprint("categorizer", __name__, url_prefix="/api")


@bp.post("/categorizer/run")
@require_auth("owner", "accountant")
def run():
    body = request.get_json(silent=True) or {}
    payload = {
        "transaction_ids": body.get("transaction_ids"),
        "only_uncategorized": body.get("only_uncategorized", True),
        "limit": body.get("limit"),
    }
    job_id = worker.enqueue(get_db(), "categorize", g.user["business_id"], payload)
    return jsonify(job_id=job_id, status_url=f"/api/jobs/{job_id}"), 202


@bp.get("/jobs/<int:job_id>")
@require_auth()
def job_status(job_id: int):
    row = get_db().execute(
        "SELECT * FROM jobs WHERE id = ? AND business_id = ?", (job_id, g.user["business_id"])
    ).fetchone()
    if row is None:
        return jsonify(error="not found"), 404
    data = dict(row)
    data["payload"] = json.loads(data["payload"])
    data["result"] = json.loads(data["result"]) if data["result"] else None
    return jsonify(data)
