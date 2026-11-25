"""Tiny background job runner backed by the `jobs` table.

WORKER_MODE=thread   -> a daemon thread inside the web process polls for jobs (default)
WORKER_MODE=external -> run `python -m ledgerly.worker` as a separate process
WORKER_MODE=inline   -> jobs run synchronously in the request (tests)
"""

import json
import logging
import threading
import time
import traceback

from ledgerly.config import settings
from ledgerly.db import connect

log = logging.getLogger("ledgerly.worker")

HANDLERS: dict = {}
_thread: threading.Thread | None = None


def job(kind: str):
    def decorator(fn):
        HANDLERS[kind] = fn
        return fn

    return decorator


def enqueue(conn, kind: str, business_id: int, payload: dict) -> int:
    cur = conn.execute(
        "INSERT INTO jobs (business_id, kind, payload) VALUES (?, ?, ?)",
        (business_id, kind, json.dumps(payload)),
    )
    conn.commit()
    job_id = cur.lastrowid
    if settings.WORKER_MODE == "inline":
        run_job(job_id)
    return job_id


def run_job(job_id: int) -> None:
    _load_handlers()
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        conn.execute("UPDATE jobs SET status = 'running' WHERE id = ?", (job_id,))
        conn.commit()
        try:
            result = HANDLERS[row["kind"]](conn, row["business_id"], json.loads(row["payload"]))
            conn.execute(
                "UPDATE jobs SET status = 'done', result = ?, finished_at = CURRENT_TIMESTAMP WHERE id = ?",
                (json.dumps(result, default=str), job_id),
            )
        except Exception as exc:
            log.error("job %s failed: %s", job_id, traceback.format_exc())
            conn.execute(
                "UPDATE jobs SET status = 'failed', error = ?, finished_at = CURRENT_TIMESTAMP WHERE id = ?",
                (str(exc), job_id),
            )
        conn.commit()
    finally:
        conn.close()


def _load_handlers() -> None:
    # importing registers the @job handlers
    from ledgerly.services import categorizer  # noqa: F401


def poll_forever(interval: float = 1.0) -> None:
    _load_handlers()
    while True:
        conn = connect()
        try:
            row = conn.execute("SELECT id FROM jobs WHERE status = 'queued' ORDER BY id LIMIT 1").fetchone()
        finally:
            conn.close()
        if row:
            run_job(row["id"])
        else:
            time.sleep(interval)


def start_background_thread() -> None:
    global _thread
    if settings.WORKER_MODE != "thread" or (_thread and _thread.is_alive()):
        return
    _thread = threading.Thread(target=poll_forever, name="ledgerly-worker", daemon=True)
    _thread.start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    log.info("worker started")
    poll_forever()
