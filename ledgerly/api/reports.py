import re

from flask import Blueprint, Response, g, jsonify, request

from ledgerly.auth import require_auth
from ledgerly.db import get_db
from ledgerly.services import reports

bp = Blueprint("reports", __name__, url_prefix="/api/reports")

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@bp.post("/monthly")
@require_auth("owner", "accountant")
def monthly():
    body = request.get_json(silent=True) or {}
    month = body.get("month", "")
    if not MONTH_RE.match(month):
        return jsonify(error="month must look like 2026-10"), 400
    fmt = body.get("format", "html")
    db = get_db()
    business = dict(db.execute("SELECT * FROM businesses WHERE id = ?", (g.user["business_id"],)).fetchone())
    data = reports.gather(db, business["id"], month)
    narrative = reports.write_narrative(business, data, body.get("focus"))
    narrative_text = reports.render_narrative(narrative, business, data)

    if fmt == "pdf":
        return Response(
            reports.build_pdf(business, data, narrative_text),
            mimetype="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=ledgerly-{month}.pdf"},
        )

    html = reports.build_html(business, data, narrative_text)
    cur = db.execute(
        "INSERT INTO reports (business_id, month, narrative, html, created_by) VALUES (?, ?, ?, ?, ?)",
        (business["id"], month, narrative_text, html, g.user["id"]),
    )
    db.commit()
    return jsonify(report_id=cur.lastrowid, narrative=narrative_text, html_url=f"/api/reports/{cur.lastrowid}/html")


@bp.get("/<int:report_id>/html")
@require_auth()
def report_html(report_id: int):
    row = get_db().execute(
        "SELECT html FROM reports WHERE id = ? AND business_id = ?", (report_id, g.user["business_id"])
    ).fetchone()
    if row is None:
        return jsonify(error="not found"), 404
    return Response(row["html"], mimetype="text/html")
