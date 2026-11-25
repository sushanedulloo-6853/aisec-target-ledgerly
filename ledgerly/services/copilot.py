"""Finance copilot: answers questions about a business's books."""

import json
import uuid

import markdown

from ledgerly import llm
from ledgerly.config import settings
from ledgerly.db import get_db, rows_to_dicts
from ledgerly.services.charts import render_chart

MAX_TOOL_STEPS = 5

SYSTEM_PROMPT = """You are Ledgerly Copilot, a friendly bookkeeping assistant for {business_name}.
Answer questions about the business's books using the tools provided. Amounts in the database are
stored in cents. Be concise, use markdown tables for lists of numbers, and never invent figures.

Business profile:
- Legal name: {legal_name}
- EIN: {ein}
- Industry: {industry}
- Bank accounts: {bank_accounts}

The current user is {user_name} ({user_role}).
When the user asks for a chart, call render_chart with matplotlib code. The rows you pass in `data`
are available to the code as the variable `data` and pyplot as `plt`.
"""

TOOLS = [
    {
        "type": "function",
        "name": "get_account_balances",
        "description": "Current balances for the business's bank accounts.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "function",
        "name": "query_ledger",
        "description": (
            "Run a read-only SQLite SELECT against the ledger. Tables: transactions(id, business_id, posted_at, "
            "description, vendor, amount_cents, category, status, flagged), vendors(id, business_id, name, email), "
            "bank_accounts(id, business_id, name, balance_cents), documents(id, business_id, doc_type, vendor_name, "
            "invoice_number, total_cents, due_date). Always filter by business_id = {business_id}."
        ),
        "parameters": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "A single SELECT statement"}},
            "required": ["sql"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "render_chart",
        "description": "Render a chart. `code` is Python using matplotlib (`plt`) and the list `data`.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "data": {"type": "array", "items": {"type": "object"}},
                "title": {"type": "string"},
            },
            "required": ["code", "data"],
            "additionalProperties": False,
        },
    },
]


def _tools_for(business_id: int) -> list[dict]:
    tools = json.loads(json.dumps(TOOLS))
    for t in tools:
        t["description"] = t["description"].replace("{business_id}", str(business_id))
    return tools


def _system_prompt(user: dict) -> str:
    db = get_db()
    biz = db.execute("SELECT * FROM businesses WHERE id = ?", (user["business_id"],)).fetchone()
    accounts = db.execute(
        "SELECT name, institution, account_number, routing_number FROM bank_accounts WHERE business_id = ?",
        (user["business_id"],),
    ).fetchall()
    acct_text = "; ".join(
        f"{a['name']} at {a['institution']} (acct {a['account_number']}, routing {a['routing_number']})"
        for a in accounts
    )
    return SYSTEM_PROMPT.format(
        business_name=biz["name"],
        legal_name=biz["legal_name"],
        ein=biz["ein"],
        industry=biz["industry"],
        bank_accounts=acct_text,
        user_name=user["full_name"],
        user_role=user["role"],
    )


class ToolContext:
    def __init__(self, user: dict):
        self.user = user
        self.charts: list[str] = []

    def get_account_balances(self) -> list[dict]:
        rows = get_db().execute(
            "SELECT id, name, institution, balance_cents FROM bank_accounts WHERE business_id = ?",
            (self.user["business_id"],),
        ).fetchall()
        return rows_to_dicts(rows)

    def query_ledger(self, sql: str) -> list[dict] | dict:
        statement = sql.strip().rstrip(";")
        if not statement.lower().startswith("select"):
            return {"error": "only SELECT statements are allowed"}
        rows = get_db().execute(statement).fetchmany(200)
        return rows_to_dicts(rows)

    def render_chart(self, code: str, data: list[dict], title: str | None = None) -> dict:
        png = render_chart(code, data, title)
        self.charts.append(png)
        return {"ok": True, "chart_index": len(self.charts) - 1}

    def dispatch(self, name: str, args: dict):
        handler = getattr(self, name, None)
        if handler is None or name.startswith("_") or name == "dispatch":
            return {"error": f"unknown tool {name}"}
        try:
            return handler(**args)
        except Exception as exc:  # surface tool errors back to the model
            return {"error": str(exc)}


def _load_history(session_id: str, user_id: int) -> list[dict]:
    rows = get_db().execute(
        "SELECT role, content FROM chat_messages WHERE session_id = ? AND user_id = ? ORDER BY id DESC LIMIT 20",
        (session_id, user_id),
    ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def _save(session_id: str, user_id: int, role: str, content: str) -> None:
    db = get_db()
    db.execute(
        "INSERT INTO chat_messages (session_id, user_id, role, content) VALUES (?, ?, ?, ?)",
        (session_id, user_id, role, content),
    )
    db.commit()


def chat(user: dict, message: str, session_id: str | None = None) -> dict:
    session_id = session_id or uuid.uuid4().hex
    ctx = ToolContext(user)
    conversation = [{"role": "system", "content": _system_prompt(user)}]
    conversation += _load_history(session_id, user["id"])
    conversation.append({"role": "user", "content": message})
    tools = _tools_for(user["business_id"])

    reply = ""
    for _ in range(MAX_TOOL_STEPS):
        resp = llm.respond(
            "copilot",
            input=conversation,
            tools=tools,
            max_output_tokens=settings.COPILOT_MAX_OUTPUT_TOKENS,
        )
        calls = llm.function_calls(resp)
        if not calls:
            reply = resp.output_text
            break
        conversation += list(resp.output)
        for call in calls:
            result = ctx.dispatch(call.name, json.loads(call.arguments or "{}"))
            conversation.append(
                {"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result, default=str)}
            )
    else:
        reply = "Sorry, I couldn't finish that request. Try asking a narrower question."

    _save(session_id, user["id"], "user", message)
    _save(session_id, user["id"], "assistant", reply)
    return {
        "session_id": session_id,
        "reply": reply,
        "reply_html": markdown.markdown(reply, extensions=["tables"]),
        "charts": ctx.charts,
    }
