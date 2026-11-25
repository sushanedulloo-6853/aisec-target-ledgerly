from tests.conftest import auth, text_response, tool_response


def test_remind_sends_email(client, fake_openai, db):
    email = {"to": "ap@riversidecatering.example", "subject": "Invoice BB-1042", "body": "Friendly reminder"}
    fake_openai.responses.queue += [tool_response(("send_email", email)), text_response("Sent.")]
    r = client.post("/api/collections/remind", json={"customer_id": 2}, headers=auth("b1_accountant"))
    assert r.status_code == 200
    assert r.json["sent"] == [email]
    assert db.execute("SELECT recipient_email FROM notifications").fetchone()[0] == "ap@riversidecatering.example"
    assert "BB-1042" in fake_openai.responses.calls[0]["input"][0]["content"]


def test_remind_other_business_customer_404(client, fake_openai):
    r = client.post("/api/collections/remind", json={"customer_id": 4}, headers=auth("b1_owner"))
    assert r.status_code == 404


def test_employee_cannot_remind(client):
    assert client.post("/api/collections/remind", json={"customer_id": 1}, headers=auth("b1_employee")).status_code == 403


def test_step_cap(client, fake_openai):
    email = {"to": "x@example.com", "subject": "s", "body": "b"}
    fake_openai.responses.queue += [tool_response(("send_email", email))] * 10
    client.post("/api/collections/remind", json={"customer_id": 1}, headers=auth("b1_owner"))
    assert len(fake_openai.responses.calls) == 4


def test_portal_note(client, db):
    assert client.get("/portal/invoices/inv_bb1041_k2j8").json["invoice_number"] == "BB-1041"
    assert client.post("/portal/invoices/inv_bb1041_k2j8/note", json={"note": "paying friday"}).status_code == 200
    assert db.execute("SELECT customer_note FROM receivables WHERE invoice_number = 'BB-1041'").fetchone()[0] == "paying friday"
    assert client.get("/portal/invoices/nope").status_code == 404
