"""Batch transaction categorizer (runs on the background worker)."""

import json

from ledgerly import llm
from ledgerly.worker import job

CATEGORIES = [
    "Revenue",
    "Cost of Goods Sold",
    "Payroll",
    "Rent",
    "Utilities",
    "Supplies",
    "Equipment",
    "Fuel & Travel",
    "Meals & Entertainment",
    "Insurance",
    "Professional Services",
    "Bank Fees",
    "Taxes",
    "Transfers",
    "Uncategorized",
]

BATCH_SIZE = 25

PROMPT = """You categorize small-business bank transactions for bookkeeping.
Allowed categories: {categories}.
For every transaction return its id, the best category, and a clean vendor name
(e.g. "SQ *COFFEEHOUSE 1234" -> "Coffeehouse"). Respond with JSON only:
{{"results": [{{"id": 1, "category": "Supplies", "vendor": "Packright"}}]}}

Transactions:
{transactions}
"""


def _format(rows) -> str:
    return "\n".join(f"- id={r['id']} | {r['posted_at']} | {r['amount_cents'] / 100:.2f} | {r['description']}" for r in rows)


def categorize_rows(conn, rows) -> list[dict]:
    resp = llm.respond(
        "categorizer",
        input=PROMPT.format(categories=", ".join(CATEGORIES), transactions=_format(rows)),
        text={"format": {"type": "json_object"}},
    )
    try:
        results = json.loads(resp.output_text).get("results", [])
    except (json.JSONDecodeError, AttributeError):
        return []
    applied = []
    for item in results:
        category = item.get("category")
        if category not in CATEGORIES:
            category = "Uncategorized"
        vendor = (item.get("vendor") or "").strip()
        conn.execute(
            f"UPDATE transactions SET category = '{category}', vendor = '{vendor}' WHERE id = {int(item['id'])}"
        )
        applied.append({"id": item["id"], "category": category, "vendor": vendor})
    conn.commit()
    return applied


@job("categorize")
def run_categorize(conn, business_id: int, payload: dict) -> dict:
    query = "SELECT id, posted_at, amount_cents, description FROM transactions WHERE business_id = ?"
    params: list = [business_id]
    if payload.get("transaction_ids"):
        ids = [int(i) for i in payload["transaction_ids"]]
        query += f" AND id IN ({','.join('?' * len(ids))})"
        params += ids
    elif payload.get("only_uncategorized", True):
        query += " AND category = 'Uncategorized'"
    query += " ORDER BY posted_at"
    if payload.get("limit"):
        query += " LIMIT ?"
        params.append(int(payload["limit"]))
    rows = conn.execute(query, params).fetchall()

    applied = []
    for i in range(0, len(rows), BATCH_SIZE):
        applied += categorize_rows(conn, rows[i : i + BATCH_SIZE])
    return {"categorized": len(applied), "results": applied}
