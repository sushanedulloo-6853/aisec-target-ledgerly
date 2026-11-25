from tests.conftest import auth, text_response

NARRATIVE = "October was steady. Revenue reached {{ totals.revenue }} against {{ totals.expenses }} of spend."


def test_monthly_report_html(client, fake_openai, db):
    db.execute("UPDATE transactions SET description = '<b>BOLD CO</b>' WHERE business_id = 1 AND posted_at LIKE '2026-10%'")
    db.commit()
    fake_openai.responses.queue.append(text_response(NARRATIVE))
    r = client.post("/api/reports/monthly", json={"month": "2026-10"}, headers=auth("b1_owner"))
    assert r.status_code == 200, r.json
    assert "{{" not in r.json["narrative"] and "$" in r.json["narrative"]
    html = client.get(r.json["html_url"], headers=auth("b1_owner")).get_data(as_text=True)
    assert "Brightside Bakery" in html
    assert "&lt;b&gt;BOLD CO&lt;/b&gt;" in html
    assert "October was steady" in html


def test_report_pdf(client, fake_openai):
    fake_openai.responses.queue.append(text_response(NARRATIVE))
    r = client.post("/api/reports/monthly", json={"month": "2026-09", "format": "pdf"}, headers=auth("b2_accountant"))
    assert r.status_code == 200
    assert r.data.startswith(b"%PDF")


def test_report_validation_and_roles(client):
    assert client.post("/api/reports/monthly", json={"month": "October"}, headers=auth("b1_owner")).status_code == 400
    assert client.post("/api/reports/monthly", json={"month": "2026-10"}, headers=auth("b1_employee")).status_code == 403


def test_report_html_scoped(client, fake_openai):
    fake_openai.responses.queue.append(text_response(NARRATIVE))
    r = client.post("/api/reports/monthly", json={"month": "2026-10"}, headers=auth("b1_owner"))
    assert client.get(r.json["html_url"], headers=auth("b2_owner")).status_code == 404
