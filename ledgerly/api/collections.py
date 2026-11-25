from flask import Blueprint, g, jsonify, request

from ledgerly.auth import require_auth
from ledgerly.db import get_db
from ledgerly.services import collections

bp = Blueprint("collections", __name__)


@bp.get("/api/receivables")
@require_auth()
def list_receivables():
    return jsonify(collections.open_receivables(get_db(), g.user["business_id"]))


@bp.post("/api/collections/remind")
@require_auth("owner", "accountant")
def remind():
    body = request.get_json(force=True) or {}
    if not body.get("customer_id"):
        return jsonify(error="customer_id is required"), 400
    result = collections.run(g.user, int(body["customer_id"]), body.get("tone", "friendly"), body.get("instructions"))
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)


# --- customer payment portal (link in every invoice email; no login) -------


@bp.get("/portal/invoices/<token>")
def portal_invoice(token: str):
    row = get_db().execute(
        "SELECT r.invoice_number, r.amount_cents, r.due_date, r.status, b.name AS business"
        " FROM receivables r JOIN businesses b ON b.id = r.business_id WHERE r.portal_token = ?",
        (token,),
    ).fetchone()
    if row is None:
        return jsonify(error="not found"), 404
    return jsonify(dict(row))


@bp.post("/portal/invoices/<token>/note")
def portal_note(token: str):
    body = request.get_json(force=True) or {}
    note = (body.get("note") or "").strip()[:2000]
    db = get_db()
    cur = db.execute("UPDATE receivables SET customer_note = ? WHERE portal_token = ?", (note, token))
    db.commit()
    if cur.rowcount == 0:
        return jsonify(error="not found"), 404
    return jsonify(ok=True)
