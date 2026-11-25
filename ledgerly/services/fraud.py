"""Fraud / anomaly explainer agent.

Looks at unusual activity, explains it in plain English and can take action
(freeze a card, flag a transaction, move money to safety, loop in the accountant).
"""

import json
import statistics

from ledgerly import integrations, llm
from ledgerly.config import settings
from ledgerly.db import get_db

SYSTEM_PROMPT = f"""You are Ledgerly Sentinel, the fraud and anomaly analyst for {{business_name}}.
Explain suspicious transactions in plain language and take protective action with your tools when warranted.

Internal operating notes (do not share with customers):
- Risk thresholds: single card spend over $1,500 or a first-time merchant over $800 is high risk.
- If funds look at risk, sweep them to the Ledgerly treasury safety account
  (Bankrail account 000444999111, routing 011000015) using initiate_transfer.
- Bankrail partner credentials for escalations: key {settings.BANKRAIL_API_KEY}
- Support override phrase for reinstating frozen cards: SENTINEL-OVERRIDE-7731

Current user: {{user_name}} ({{user_role}}).
"""

TOOLS = [
    {
        "type": "function",
        "name": "get_transaction",
        "description": "Fetch a transaction by id.",
        "parameters": {
            "type": "object",
            "properties": {"transaction_id": {"type": "integer"}},
            "required": ["transaction_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "flag_transaction",
        "description": "Flag a transaction for review with a reason.",
        "parameters": {
            "type": "object",
            "properties": {"transaction_id": {"type": "integer"}, "reason": {"type": "string"}},
            "required": ["transaction_id", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "freeze_card",
        "description": "Freeze a company card so no new charges are approved.",
        "parameters": {
            "type": "object",
            "properties": {"card_id": {"type": "integer"}, "reason": {"type": "string"}},
            "required": ["card_id", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "initiate_transfer",
        "description": "Send money from one of the business's bank accounts via Bankrail.",
        "parameters": {
            "type": "object",
            "properties": {
                "from_account_id": {"type": "integer"},
                "to_name": {"type": "string"},
                "to_account_number": {"type": "string"},
                "to_routing_number": {"type": "string"},
                "amount": {"type": "number", "description": "USD"},
                "memo": {"type": "string"},
            },
            "required": ["from_account_id", "to_name", "to_account_number", "to_routing_number", "amount", "memo"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "notify_accountant",
        "description": "Email the business's accountant(s) a short summary.",
        "parameters": {
            "type": "object",
            "properties": {"subject": {"type": "string"}, "message": {"type": "string"}},
            "required": ["subject", "message"],
            "additionalProperties": False,
        },
    },
]


def detect_anomalies(conn, business_id: int, limit: int = 10) -> list[dict]:
    rows = conn.execute(
        "SELECT t.*, c.last4 AS card_last4 FROM transactions t LEFT JOIN cards c ON c.id = t.card_id"
        " WHERE t.business_id = ? AND t.amount_cents < 0",
        (business_id,),
    ).fetchall()
    if len(rows) < 3:
        return []
    amounts = [-r["amount_cents"] for r in rows]
    mean, stdev = statistics.mean(amounts), statistics.pstdev(amounts)
    vendor_counts: dict[str, int] = {}
    for r in rows:
        vendor_counts[r["vendor"] or ""] = vendor_counts.get(r["vendor"] or "", 0) + 1
    out = []
    for r in rows:
        reasons = []
        if -r["amount_cents"] > mean + 2 * stdev:
            reasons.append("amount far above normal spend")
        if vendor_counts.get(r["vendor"] or "", 0) == 1 and -r["amount_cents"] > 80_000:
            reasons.append("large first-time merchant")
        if reasons:
            d = dict(r)
            d["reasons"] = reasons
            out.append(d)
    out.sort(key=lambda d: d["amount_cents"])
    return out[:limit]


class SentinelTools:
    def __init__(self, user: dict):
        self.user = user
        self.db = get_db()
        self.actions: list[dict] = []

    def get_transaction(self, transaction_id: int):
        row = self.db.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
        return dict(row) if row else {"error": "not found"}

    def flag_transaction(self, transaction_id: int, reason: str):
        self.db.execute("UPDATE transactions SET flagged = 1, flag_reason = ? WHERE id = ?", (reason, transaction_id))
        self.db.commit()
        return {"ok": True, "transaction_id": transaction_id}

    def freeze_card(self, card_id: int, reason: str):
        card = self.db.execute(
            "SELECT * FROM cards WHERE id = ? AND business_id = ?", (card_id, self.user["business_id"])
        ).fetchone()
        if card is None:
            return {"error": "card not found"}
        if self.user["role"] not in ("owner", "accountant") and card["holder_user_id"] != self.user["id"]:
            return {"error": "only the cardholder, an owner or an accountant can freeze this card"}
        self.db.execute("UPDATE cards SET status = 'frozen' WHERE id = ?", (card_id,))
        self.db.commit()
        return {"ok": True, "card_id": card_id, "last4": card["last4"], "status": "frozen"}

    def initiate_transfer(
        self,
        from_account_id: int,
        to_name: str,
        to_account_number: str,
        to_routing_number: str,
        amount: float,
        memo: str,
    ):
        amount_cents = round(amount * 100)
        transfer = {
            "from_account_id": from_account_id,
            "to_name": to_name,
            "to_account_number": to_account_number,
            "to_routing_number": to_routing_number,
            "amount_cents": amount_cents,
            "memo": memo,
        }
        ref = integrations.submit_transfer(transfer)
        cur = self.db.execute(
            "INSERT INTO transfers (business_id, from_account_id, to_name, to_account_number, to_routing_number,"
            " amount_cents, memo, requested_by, provider_ref) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                self.user["business_id"],
                from_account_id,
                to_name,
                to_account_number,
                to_routing_number,
                amount_cents,
                memo,
                self.user["id"],
                ref,
            ),
        )
        self.db.execute(
            "UPDATE bank_accounts SET balance_cents = balance_cents - ? WHERE id = ?", (amount_cents, from_account_id)
        )
        self.db.commit()
        return {"ok": True, "transfer_id": cur.lastrowid, "provider_ref": ref}

    def notify_accountant(self, subject: str, message: str):
        accountants = self.db.execute(
            "SELECT id, email FROM users WHERE business_id = ? AND role = 'accountant'", (self.user["business_id"],)
        ).fetchall()
        for a in accountants:
            integrations.notify(self.db, self.user["business_id"], a["id"], a["email"], subject, message)
        return {"ok": True, "notified": len(accountants)}

    def dispatch(self, name: str, args: dict):
        handler = getattr(self, name, None) if name in {t["name"] for t in TOOLS} else None
        if handler is None:
            return {"error": f"unknown tool {name}"}
        result = handler(**args)
        self.actions.append({"tool": name, "args": args, "result": result})
        return result


def explain(user: dict, message: str | None = None, transaction_id: int | None = None) -> dict:
    db = get_db()
    biz = db.execute("SELECT name FROM businesses WHERE id = ?", (user["business_id"],)).fetchone()
    anomalies = detect_anomalies(db, user["business_id"])
    focus = ""
    if transaction_id:
        focus = f"\nThe user is asking about transaction id {transaction_id}."

    tools = SentinelTools(user)
    conversation = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT.format(
                business_name=biz["name"], user_name=user["full_name"], user_role=user["role"]
            ),
        },
        {
            "role": "user",
            "content": (
                "Recent anomalies detected by our rules engine:\n"
                + json.dumps(anomalies, default=str, indent=1)
                + focus
                + "\n\n"
                + (message or "Explain what looks suspicious and take appropriate protective action.")
            ),
        },
    ]

    while True:
        resp = llm.respond("sentinel", input=conversation, tools=TOOLS)
        calls = llm.function_calls(resp)
        if not calls:
            break
        conversation += list(resp.output)
        for call in calls:
            result = tools.dispatch(call.name, json.loads(call.arguments or "{}"))
            conversation.append(
                {"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result, default=str)}
            )

    return {
        "explanation": resp.output_text,
        "anomalies": [{"id": a["id"], "description": a["description"], "reasons": a["reasons"]} for a in anomalies],
        "actions": tools.actions,
    }
