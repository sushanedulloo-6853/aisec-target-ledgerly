import json
import re

from tests.conftest import auth, text_response


def _echo_categories(kwargs):
    ids = [int(m) for m in re.findall(r"id=(\d+)", kwargs["input"])]
    results = [{"id": i, "category": "Supplies", "vendor": "Packright"} for i in ids]
    return text_response(json.dumps({"results": results}))


def test_categorize_specific_transactions(client, fake_openai, db):
    ids = [r["id"] for r in db.execute("SELECT id FROM transactions WHERE business_id = 1 LIMIT 3")]
    fake_openai.responses.queue.append(_echo_categories)
    r = client.post("/api/categorizer/run", json={"transaction_ids": ids}, headers=auth("b1_accountant"))
    assert r.status_code == 202
    job = client.get(r.json["status_url"], headers=auth("b1_accountant")).json
    assert job["status"] == "done"
    assert job["result"]["categorized"] == 3
    cats = {row["category"] for row in db.execute(f"SELECT category FROM transactions WHERE id IN ({','.join(map(str, ids))})")}
    assert cats == {"Supplies"}


def test_unknown_category_falls_back(client, fake_openai, db):
    txn = db.execute("SELECT id FROM transactions WHERE business_id = 1 LIMIT 1").fetchone()["id"]
    fake_openai.responses.queue.append(
        text_response(json.dumps({"results": [{"id": txn, "category": "Yacht", "vendor": "X"}]}))
    )
    client.post("/api/categorizer/run", json={"transaction_ids": [txn]}, headers=auth("b1_owner"))
    assert db.execute("SELECT category FROM transactions WHERE id = ?", (txn,)).fetchone()[0] == "Uncategorized"


def test_batches_uncategorized(client, fake_openai):
    fake_openai.responses.queue += [_echo_categories] * 3
    r = client.post("/api/categorizer/run", json={}, headers=auth("b2_owner"))
    job = client.get(r.json["status_url"], headers=auth("b2_owner")).json
    assert job["result"]["categorized"] == 61
    assert len(fake_openai.responses.calls) == 3


def test_employee_cannot_run(client):
    assert client.post("/api/categorizer/run", json={}, headers=auth("b1_employee")).status_code == 403


def test_job_status_scoped(client, fake_openai):
    r = client.post("/api/categorizer/run", json={"limit": 1}, headers=auth("b1_owner"))
    assert client.get(r.json["status_url"], headers=auth("b2_owner")).status_code == 404
