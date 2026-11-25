import sqlite3
from pathlib import Path

from flask import g

from ledgerly.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS businesses (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    legal_name TEXT,
    ein TEXT,
    industry TEXT,
    currency TEXT DEFAULT 'USD',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id),
    email TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('owner', 'accountant', 'employee')),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS api_tokens (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    token_hash TEXT UNIQUE NOT NULL,
    label TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bank_accounts (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id),
    name TEXT NOT NULL,
    institution TEXT,
    account_number TEXT,
    routing_number TEXT,
    balance_cents INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id),
    holder_user_id INTEGER REFERENCES users(id),
    last4 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    spend_limit_cents INTEGER
);

CREATE TABLE IF NOT EXISTS vendors (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id),
    name TEXT NOT NULL,
    email TEXT,
    bank_account_number TEXT,
    bank_routing_number TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id),
    bank_account_id INTEGER REFERENCES bank_accounts(id),
    card_id INTEGER REFERENCES cards(id),
    posted_at TEXT NOT NULL,
    description TEXT NOT NULL,
    vendor TEXT,
    amount_cents INTEGER NOT NULL,
    category TEXT DEFAULT 'Uncategorized',
    status TEXT NOT NULL DEFAULT 'posted',
    flagged INTEGER NOT NULL DEFAULT 0,
    flag_reason TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id),
    uploaded_by INTEGER REFERENCES users(id),
    source TEXT NOT NULL,
    filename TEXT,
    doc_type TEXT,
    vendor_name TEXT,
    invoice_number TEXT,
    total_cents INTEGER,
    due_date TEXT,
    extracted_json TEXT,
    text_content TEXT,
    indexed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    result TEXT,
    error TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS transfers (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL,
    from_account_id INTEGER,
    to_name TEXT,
    to_account_number TEXT,
    to_routing_number TEXT,
    amount_cents INTEGER NOT NULL,
    memo TEXT,
    status TEXT NOT NULL DEFAULT 'submitted',
    requested_by INTEGER,
    provider_ref TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL,
    recipient_user_id INTEGER,
    recipient_email TEXT,
    subject TEXT,
    body TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL,
    month TEXT NOT NULL,
    narrative TEXT,
    html TEXT,
    created_by INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def connect(path: str | None = None) -> sqlite3.Connection:
    path = path or settings.DATABASE_PATH
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def rows_to_dicts(rows) -> list[dict]:
    return [dict(r) for r in rows]
