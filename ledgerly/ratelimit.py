import functools
import threading
import time
from collections import defaultdict, deque

from flask import g, jsonify

_hits: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def rate_limited(bucket: str, per_minute_setting):
    """Simple per-user sliding window limiter (in-process)."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            limit = per_minute_setting() if callable(per_minute_setting) else per_minute_setting
            key = f"{bucket}:{g.user['id']}"
            now = time.monotonic()
            with _lock:
                q = _hits[key]
                while q and now - q[0] > 60:
                    q.popleft()
                if len(q) >= limit:
                    return jsonify(error="rate limit exceeded, try again in a minute"), 429
                q.append(now)
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def reset() -> None:
    with _lock:
        _hits.clear()
