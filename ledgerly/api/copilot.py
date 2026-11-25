from flask import Blueprint, g, jsonify, request

from ledgerly.auth import require_auth
from ledgerly.config import settings
from ledgerly.ratelimit import rate_limited
from ledgerly.services import copilot

bp = Blueprint("copilot", __name__, url_prefix="/api/copilot")


@bp.post("/chat")
@require_auth()
@rate_limited("copilot", lambda: settings.COPILOT_RATE_LIMIT_PER_MIN)
def chat():
    body = request.get_json(force=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify(error="message is required"), 400
    if len(message) > 4000:
        return jsonify(error="message too long"), 400
    return jsonify(copilot.chat(g.user, message, body.get("session_id")))
