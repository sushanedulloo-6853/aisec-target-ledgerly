from tests.conftest import auth


def test_health(client):
    assert client.get("/healthz").json == {"status": "ok"}


def test_requires_token(client):
    assert client.get("/api/transactions").status_code == 401
    assert client.get("/api/transactions", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_me(client):
    me = client.get("/api/me", headers=auth("b2_accountant")).json
    assert me["business_id"] == 2
    assert me["role"] == "accountant"


def test_transactions_are_scoped_to_business(client):
    rows = client.get("/api/transactions?limit=500", headers=auth("b1_owner")).json
    assert rows and all(r["business_id"] == 1 for r in rows)


def test_cannot_read_other_business_transaction(client, db):
    other = db.execute("SELECT id FROM transactions WHERE business_id = 2 LIMIT 1").fetchone()["id"]
    assert client.get(f"/api/transactions/{other}", headers=auth("b1_owner")).status_code == 404
    assert client.get(f"/api/transactions/{other}", headers=auth("b2_owner")).status_code == 200


def test_employee_cannot_create_transaction(client):
    body = {"posted_at": "2026-11-01", "description": "x", "amount_cents": 100}
    assert client.post("/api/transactions", json=body, headers=auth("b1_employee")).status_code == 403
    assert client.post("/api/transactions", json=body, headers=auth("b1_owner")).status_code == 201
