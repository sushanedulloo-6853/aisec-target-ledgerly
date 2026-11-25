"""Shared OpenAI plumbing: one lazily-created client for the whole app."""

import json
import logging
import os
import threading
from pathlib import Path

from openai import OpenAI

from ledgerly.config import settings

_client: OpenAI | None = None
_lock = threading.Lock()

Path(settings.LOG_DIR).mkdir(parents=True, exist_ok=True)
llm_log = logging.getLogger("ledgerly.llm")
if not llm_log.handlers:
    _fh = logging.FileHandler(Path(settings.LOG_DIR) / "llm.log")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    llm_log.addHandler(_fh)
    llm_log.setLevel(logging.INFO)


class LLMNotConfigured(RuntimeError):
    pass


def get_client() -> OpenAI:
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                if not os.getenv("OPENAI_API_KEY"):
                    raise LLMNotConfigured("OPENAI_API_KEY is not set")
                _client = OpenAI(base_url=settings.OPENAI_BASE_URL)
    return _client


def reset_client() -> None:
    global _client
    _client = None


def respond(feature: str, **kwargs):
    """Call the Responses API with app defaults and keep a trace for debugging."""
    kwargs.setdefault("model", settings.OPENAI_MODEL)
    kwargs.setdefault("reasoning", {"effort": settings.OPENAI_REASONING_EFFORT})
    llm_log.info("feature=%s request=%s", feature, json.dumps(kwargs, default=str))
    resp = get_client().responses.create(**kwargs)
    llm_log.info("feature=%s response=%s", feature, getattr(resp, "output_text", ""))
    return resp


def function_calls(resp) -> list:
    return [item for item in (resp.output or []) if getattr(item, "type", None) == "function_call"]


# --- LlamaIndex -----------------------------------------------------------


def get_llama_llm():
    from llama_index.llms.openai_like import OpenAILike

    if not os.getenv("OPENAI_API_KEY"):
        raise LLMNotConfigured("OPENAI_API_KEY is not set")
    return OpenAILike(
        model=settings.OPENAI_MODEL,
        api_key=os.environ["OPENAI_API_KEY"],
        api_base=settings.OPENAI_BASE_URL or "https://api.openai.com/v1",
        is_chat_model=True,
        is_function_calling_model=False,
        context_window=400_000,
    )


def get_embed_model():
    from llama_index.embeddings.openai import OpenAIEmbedding

    if not os.getenv("OPENAI_API_KEY"):
        raise LLMNotConfigured("OPENAI_API_KEY is not set")
    return OpenAIEmbedding(
        model=settings.OPENAI_EMBEDDING_MODEL,
        api_key=os.environ["OPENAI_API_KEY"],
        api_base=settings.OPENAI_BASE_URL,
    )
