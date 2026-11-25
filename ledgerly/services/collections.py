"""Collections assistant: chases overdue customer invoices with friendly reminder emails."""

import json
from datetime import date

from ledgerly import integrations, llm
from ledgerly.db import get_db, rows_to_dicts

MAX_STEPS = 4

SYSTEM_PROMPT = """You are the accounts-receivable assistant for {business_name}.
Write short, polite payment reminder emails for overdue invoices and send them with the send_email tool.
Match the requested tone. Sign off as "The {business_name} team". Today is {today}.

Open receivables:
{receivables}
"""

TOOLS = [
    {
        "type": "function",
        "name": "send_email",
        "description": "Send an email on behalf of the business.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
            "additionalProperties": False,
        },
    }
]


def open_receivables(conn, business_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT r.id, r.invoice_number, r.amount_cents, r.issued_at, r.due_date, r.customer_note,"
        " c.id AS customer_id, c.name AS customer_name, c.email AS customer_email, c.phone AS customer_phone"
        " FROM receivables r JOIN customers c ON c.id = r.customer_id"
        " WHERE r.business_id = ? AND r.status = 'open' ORDER BY r.due_date",
        (business_id,),
    ).fetchall()
    return rows_to_dicts(rows)


def run(user: dict, customer_id: int, tone: str = "friendly", instructions: str | None = None) -> dict:
    db = get_db()
    biz = db.execute("SELECT name FROM businesses WHERE id = ?", (user["business_id"],)).fetchone()
    customer = db.execute(
        "SELECT * FROM customers WHERE id = ? AND business_id = ?", (customer_id, user["business_id"])
    ).fetchone()
    if customer is None:
        return {"error": "customer not found"}

    receivables = open_receivables(db, user["business_id"])
    conversation = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT.format(
                business_name=biz["name"],
                today=date.today().isoformat(),
                receivables=json.dumps(receivables, indent=1),
            ),
        },
        {
            "role": "user",
            "content": f"Send a {tone} reminder to {customer['name']} about their overdue invoices."
            + (f"\nExtra instructions: {instructions}" if instructions else ""),
        },
    ]

    sent = []
    reply = ""
    for _ in range(MAX_STEPS):
        resp = llm.respond("collections", input=conversation, tools=TOOLS, max_output_tokens=1000)
        calls = llm.function_calls(resp)
        if not calls:
            reply = resp.output_text
            break
        conversation += list(resp.output)
        for call in calls:
            args = json.loads(call.arguments or "{}")
            if call.name != "send_email":
                output = {"error": "unknown tool"}
            else:
                integrations.notify(db, user["business_id"], None, args["to"], args["subject"], args["body"])
                sent.append(args)
                output = {"ok": True}
            conversation.append({"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(output)})
    return {"reply": reply, "sent": sent}
