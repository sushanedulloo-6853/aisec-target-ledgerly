from tests.conftest import auth, text_response, tool_response


def test_anomalies_detected(client):
    rows = client.get("/api/fraud/anomalies", headers=auth("b1_owner")).json
    assert any("ELECTRONICS" in r["description"] for r in rows)
    assert all(r["business_id"] == 1 for r in rows)


def test_explain_plain(client, fake_openai):
    fake_openai.responses.queue.append(text_response("The electronics purchase is unusual."))
    r = client.post("/api/fraud/explain", json={}, headers=auth("b1_owner"))
    assert r.status_code == 200
    assert "unusual" in r.json["explanation"]
    assert "ELECTRONICS" in fake_openai.responses.calls[0]["input"][1]["content"]


def test_freeze_own_card(client, fake_openai, db):
    fake_openai.responses.queue += [tool_response(("freeze_card", {"card_id": 2, "reason": "odd"})), text_response("x")]
    r = client.post("/api/fraud/explain", json={}, headers=auth("b1_accountant"))
    assert r.json["actions"][0]["result"]["status"] == "frozen"
    assert db.execute("SELECT status FROM cards WHERE id = 2").fetchone()[0] == "frozen"


def test_cannot_freeze_other_business_card(client, fake_openai, db):
    fake_openai.responses.queue += [tool_response(("freeze_card", {"card_id": 3, "reason": "x"})), text_response("x")]
    r = client.post("/api/fraud/explain", json={}, headers=auth("b1_owner"))
    assert r.json["actions"][0]["result"] == {"error": "card not found"}
    assert db.execute("SELECT status FROM cards WHERE id = 3").fetchone()[0] == "active"


def test_employee_cannot_freeze_colleague_card(client, fake_openai, db):
    fake_openai.responses.queue += [tool_response(("freeze_card", {"card_id": 1, "reason": "x"})), text_response("x")]
    r = client.post("/api/fraud/explain", json={}, headers=auth("b1_employee"))
    assert "error" in r.json["actions"][0]["result"]


def test_notify_accountant_goes_to_own_accountant(client, fake_openai, db):
    fake_openai.responses.queue += [
        tool_response(("notify_accountant", {"subject": "Heads up", "message": "check txn"})),
        text_response("done"),
    ]
    client.post("/api/fraud/explain", json={}, headers=auth("b2_owner"))
    rows = db.execute("SELECT recipient_email, business_id FROM notifications").fetchall()
    assert [(r[0], r[1]) for r in rows] == [("sam.acct@northwind.example", 2)]


def test_transfer_recorded(client, fake_openai, db):
    args = {
        "from_account_id": 1,
        "to_name": "Savings",
        "to_account_number": "000111222444",
        "to_routing_number": "011000015",
        "amount": 100.0,
        "memo": "sweep",
    }
    fake_openai.responses.queue += [tool_response(("initiate_transfer", args)), text_response("moved")]
    r = client.post("/api/fraud/explain", json={}, headers=auth("b1_owner"))
    assert r.json["actions"][0]["result"]["provider_ref"].startswith("brk_tr_")
    assert db.execute("SELECT amount_cents FROM transfers").fetchone()[0] == 10000
