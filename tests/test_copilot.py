from ledgerly.config import settings
from tests.conftest import auth, text_response, tool_response


def test_chat_plain_answer(client, fake_openai):
    fake_openai.responses.queue.append(text_response("Your **revenue** is up."))
    r = client.post("/api/copilot/chat", json={"message": "how are we doing?"}, headers=auth("b1_owner"))
    assert r.status_code == 200
    assert r.json["reply"] == "Your **revenue** is up."
    assert "<strong>revenue</strong>" in r.json["reply_html"]
    call = fake_openai.responses.calls[0]
    assert call["model"] == "gpt-6-luna"
    assert call["max_output_tokens"] == settings.COPILOT_MAX_OUTPUT_TOKENS
    assert "Brightside Bakery" in call["input"][0]["content"]


def test_chat_uses_balance_tool(client, fake_openai):
    fake_openai.responses.queue += [tool_response(("get_account_balances", {})), text_response("done")]
    r = client.post("/api/copilot/chat", json={"message": "balances?"}, headers=auth("b2_owner"))
    assert r.json["reply"] == "done"
    outputs = [i for i in fake_openai.responses.calls[1]["input"] if isinstance(i, dict) and i.get("type")]
    assert "Business Checking" in outputs[-1]["output"]
    assert "Operating Checking" not in outputs[-1]["output"]


def test_chat_ledger_query(client, fake_openai):
    sql = "SELECT COUNT(*) AS n FROM transactions WHERE business_id = 1"
    fake_openai.responses.queue += [tool_response(("query_ledger", {"sql": sql})), text_response("61")]
    r = client.post("/api/copilot/chat", json={"message": "how many txns"}, headers=auth("b1_owner"))
    assert r.json["reply"] == "61"
    out = fake_openai.responses.calls[1]["input"][-1]["output"]
    assert '"n": 61' in out


def test_chat_rejects_non_select(client, fake_openai):
    fake_openai.responses.queue += [
        tool_response(("query_ledger", {"sql": "DELETE FROM transactions"})),
        text_response("nope"),
    ]
    client.post("/api/copilot/chat", json={"message": "x"}, headers=auth("b1_owner"))
    assert "only SELECT" in fake_openai.responses.calls[1]["input"][-1]["output"]


def test_chart_rendering(client, fake_openai):
    code = "plt.bar([d['m'] for d in data], [d['v'] for d in data])"
    fake_openai.responses.queue += [
        tool_response(("render_chart", {"code": code, "data": [{"m": "Oct", "v": 3}, {"m": "Nov", "v": 5}]})),
        text_response("Here is your chart"),
    ]
    r = client.post("/api/copilot/chat", json={"message": "chart please"}, headers=auth("b1_owner"))
    assert len(r.json["charts"]) == 1
    assert r.json["charts"][0].startswith("iVBOR")


def test_tool_loop_is_capped(client, fake_openai):
    fake_openai.responses.queue += [tool_response(("get_account_balances", {}))] * 10
    r = client.post("/api/copilot/chat", json={"message": "loop"}, headers=auth("b1_owner"))
    assert len(fake_openai.responses.calls) == 5
    assert "couldn't finish" in r.json["reply"]


def test_history_is_per_user(client, fake_openai):
    r = client.post("/api/copilot/chat", json={"message": "first"}, headers=auth("b1_owner"))
    sid = r.json["session_id"]
    client.post("/api/copilot/chat", json={"message": "second", "session_id": sid}, headers=auth("b1_accountant"))
    second_input = fake_openai.responses.calls[1]["input"]
    assert not any(m.get("content") == "first" for m in second_input if isinstance(m, dict))


def test_rate_limit(client, fake_openai, monkeypatch):
    monkeypatch.setattr(settings, "COPILOT_RATE_LIMIT_PER_MIN", 2)
    for _ in range(2):
        assert client.post("/api/copilot/chat", json={"message": "hi"}, headers=auth("b1_owner")).status_code == 200
    assert client.post("/api/copilot/chat", json={"message": "hi"}, headers=auth("b1_owner")).status_code == 429


def test_missing_key_returns_503(client, monkeypatch):
    from ledgerly import llm

    monkeypatch.delenv("OPENAI_API_KEY")
    llm.reset_client()
    r = client.post("/api/copilot/chat", json={"message": "hi"}, headers=auth("b1_owner"))
    assert r.status_code == 503
