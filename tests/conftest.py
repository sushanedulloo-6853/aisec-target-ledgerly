import json
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-a-real-key")

from ledgerly import llm, ratelimit  # noqa: E402
from ledgerly.config import settings  # noqa: E402
from ledgerly.seed import seed  # noqa: E402

TOKENS = {
    "b1_owner": "lgr_test_brightside_owner_4f9a1c",
    "b1_accountant": "lgr_test_brightside_accountant_8b2e7d",
    "b1_employee": "lgr_test_brightside_employee_3c6f0a",
    "b2_owner": "lgr_test_northwind_owner_9d4b2e",
    "b2_accountant": "lgr_test_northwind_accountant_1a7c5f",
    "b2_employee": "lgr_test_northwind_employee_6e3d8b",
}


def auth(name: str) -> dict:
    return {"Authorization": f"Bearer {TOKENS[name]}"}


def text_response(text: str):
    return SimpleNamespace(output=[SimpleNamespace(type="message", content=text)], output_text=text)


def tool_response(*calls: tuple[str, dict]):
    items = [
        SimpleNamespace(type="function_call", name=name, arguments=json.dumps(args), call_id=f"call_{i}")
        for i, (name, args) in enumerate(calls)
    ]
    return SimpleNamespace(output=items, output_text="")


class FakeResponses:
    def __init__(self):
        self.queue: list = []
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.queue:
            return text_response("ok")
        item = self.queue.pop(0)
        return item(kwargs) if callable(item) else item


class FakeOpenAI:
    def __init__(self):
        self.responses = FakeResponses()


@pytest.fixture
def fake_openai(monkeypatch):
    client = FakeOpenAI()
    monkeypatch.setattr(llm, "get_client", lambda: client)
    return client


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "INDEX_DIR", str(tmp_path / "index"))
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "WORKER_MODE", "inline")
    seed(settings.DATABASE_PATH)
    ratelimit.reset()
    from ledgerly.services import rag

    rag.reset_index()
    from ledgerly.app import create_app

    application = create_app({"TESTING": True})
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db():
    from ledgerly.db import connect

    conn = connect(settings.DATABASE_PATH)
    yield conn
    conn.close()


@pytest.fixture
def fake_llama(monkeypatch):
    from llama_index.core.embeddings import MockEmbedding
    from llama_index.core.llms import MockLLM

    monkeypatch.setattr(llm, "get_embed_model", lambda: MockEmbedding(embed_dim=8))
    monkeypatch.setattr(llm, "get_llama_llm", lambda: MockLLM(max_tokens=16))
