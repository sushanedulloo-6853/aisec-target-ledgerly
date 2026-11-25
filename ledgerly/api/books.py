from flask import Blueprint, g, jsonify, request

from ledgerly.auth import require_auth
from ledgerly.db import get_db, rows_to_dicts

bp = Blueprint("books", __name__, url_prefix="/api")


@bp.get("/me")
@require_auth()
def me():
    return jsonify(g.user)


@bp.get("/accounts")
@require_auth()
def list_accounts():
    rows = get_db().execute(
        "SELECT id, name, institution, balance_cents FROM bank_accounts WHERE business_id = ?",
        (g.user["business_id"],),
    ).fetchall()
    return jsonify(rows_to_dicts(rows))


@bp.get("/transactions")
@require_auth()
def list_transactions():
    limit = min(int(request.args.get("limit", 50)), 500)
    offset = int(request.args.get("offset", 0))
    params: list = [g.user["business_id"]]
    where = "business_id = ?"
    if category := request.args.get("category"):
        where += " AND category = ?"
        params.append(category)
    rows = get_db().execute(
        f"SELECT * FROM transactions WHERE {where} ORDER BY posted_at DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    return jsonify(rows_to_dicts(rows))


@bp.get("/transactions/<int:txn_id>")
@require_auth()
def get_transaction(txn_id: int):
    row = get_db().execute(
        "SELECT * FROM transactions WHERE id = ? AND business_id = ?",
        (txn_id, g.user["business_id"]),
    ).fetchone()
    if row is None:
        return jsonify(error="not found"), 404
    return jsonify(dict(row))


@bp.post("/transactions")
@require_auth("owner", "accountant")
def create_transaction():
    body = request.get_json(force=True)
    db = get_db()
    cur = db.execute(
        "INSERT INTO transactions (business_id, bank_account_id, posted_at, description, vendor, amount_cents)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            g.user["business_id"],
            body.get("bank_account_id"),
            body["posted_at"],
            body["description"],
            body.get("vendor"),
            int(body["amount_cents"]),
        ),
    )
    db.commit()
    return jsonify(id=cur.lastrowid), 201


@bp.get("/vendors")
@require_auth()
def list_vendors():
    rows = get_db().execute(
        "SELECT id, name, email, updated_at FROM vendors WHERE business_id = ?", (g.user["business_id"],)
    ).fetchall()
    return jsonify(rows_to_dicts(rows))
