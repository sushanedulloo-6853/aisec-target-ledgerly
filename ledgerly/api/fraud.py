from flask import Blueprint, g, jsonify, request

from ledgerly.auth import require_auth
from ledgerly.db import get_db
from ledgerly.services import fraud

bp = Blueprint("fraud", __name__, url_prefix="/api/fraud")


@bp.get("/anomalies")
@require_auth()
def anomalies():
    return jsonify(fraud.detect_anomalies(get_db(), g.user["business_id"]))


@bp.post("/explain")
@require_auth()
def explain():
    body = request.get_json(silent=True) or {}
    txn_id = body.get("transaction_id")
    return jsonify(fraud.explain(g.user, body.get("message"), int(txn_id) if txn_id else None))
