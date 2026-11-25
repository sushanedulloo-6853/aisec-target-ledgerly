import functools
import hashlib
import secrets

from flask import g, jsonify, request

from ledgerly.db import get_db


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return "lgr_" + secrets.token_urlsafe(32)


def _load_user(token: str):
    db = get_db()
    return db.execute(
        """
        SELECT u.id, u.business_id, u.email, u.full_name, u.role, b.name AS business_name
        FROM api_tokens t
        JOIN users u ON u.id = t.user_id
        JOIN businesses b ON b.id = u.business_id
        WHERE t.token_hash = ?
        """,
        (hash_token(token),),
    ).fetchone()


def require_auth(*roles: str):
    """Require a bearer token. Optionally restrict to the given roles."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return jsonify(error="missing bearer token"), 401
            user = _load_user(header.removeprefix("Bearer ").strip())
            if user is None:
                return jsonify(error="invalid token"), 401
            g.user = dict(user)
            if roles and g.user["role"] not in roles:
                return jsonify(error="forbidden"), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator
