"""Tests for routers/query.py.

LLM calls are always patched (no Ollama needed). DB and ChromaDB use real
tmp-path instances. SSE responses are parsed from the buffered TestClient body.
"""
from __future__ import annotations

import json
from pathlib import Path
from random import Random
from unittest.mock import patch

import pytest
from chromadb import Documents, Embeddings
from chromadb.utils.embedding_functions import EmbeddingFunction
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers.query import _sse, _stream_answer, router
from backend.storage.db import init_db
from backend.storage.vector_store import init_collection

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ── helpers ───────────────────────────────────────────────────────────────────

class _HashEF(EmbeddingFunction[Documents]):
    def __init__(self) -> None:
        pass

    def __call__(self, input: Documents) -> Embeddings:
        result = []
        for text in input:
            rng = Random(abs(hash(text)) % (2**31))
            vec = [rng.gauss(0, 1) for _ in range(64)]
            norm = sum(x * x for x in vec) ** 0.5 or 1.0
            result.append([x / norm for x in vec])
        return result

    @staticmethod
    def name() -> str:
        return "hash-test"

    @staticmethod
    def build_from_config(config: dict) -> "_HashEF":
        return _HashEF()

    def get_config(self) -> dict:
        return {"name": "hash-test"}


def _parse_sse(body: str) -> list[dict]:
    """Parse a buffered SSE body into a list of event dicts."""
    events = []
    for block in body.split("\n\n"):
        block = block.strip()
        if block.startswith("data: "):
            payload = block[len("data: "):]
            events.append(json.loads(payload))
    return events


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def app(tmp_path):
    application = FastAPI()
    application.include_router(router)
    application.state.db = init_db(tmp_path / "test.db")
    application.state.collection = init_collection(tmp_path / "chroma", embedding_fn=_HashEF())
    application.state.llm_model = "test-model"
    application.state.ollama_url = "http://localhost:11434"
    return application


@pytest.fixture()
def client(app):
    return TestClient(app)


def _patched_llm(tokens=("Hello", " world")):
    """Context manager: patch llm_stream to yield fixed tokens."""
    return patch("backend.routers.query.llm_stream", return_value=iter(tokens))


# ── _sse unit tests ───────────────────────────────────────────────────────────

def test_sse_starts_with_data_prefix():
    assert _sse({"type": "done"}).startswith("data: ")


def test_sse_ends_with_double_newline():
    assert _sse({"type": "done"}).endswith("\n\n")


def test_sse_body_is_valid_json():
    line = _sse({"type": "token", "text": "hi"})
    payload = line.strip().removeprefix("data: ")
    data = json.loads(payload)
    assert data == {"type": "token", "text": "hi"}


# ── GET /api/query/stream — HTTP response ─────────────────────────────────────

def test_query_stream_returns_200(client):
    with _patched_llm():
        resp = client.get("/api/query/stream", params={"q": "test"})
    assert resp.status_code == 200


def test_query_stream_content_type_is_sse(client):
    with _patched_llm():
        resp = client.get("/api/query/stream", params={"q": "test"})
    assert "text/event-stream" in resp.headers["content-type"]


def test_missing_q_returns_422(client):
    resp = client.get("/api/query/stream")
    assert resp.status_code == 422


def test_query_stream_events_are_valid_json(client):
    with _patched_llm(["tok"]):
        resp = client.get("/api/query/stream", params={"q": "test"})
    events = _parse_sse(resp.text)
    assert len(events) > 0


def test_query_stream_contains_token_events(client):
    with _patched_llm(["Hello", " world"]):
        resp = client.get("/api/query/stream", params={"q": "test"})
    events = _parse_sse(resp.text)
    token_events = [e for e in events if e.get("type") == "token"]
    assert len(token_events) == 2


def test_query_stream_token_text_matches_llm_output(client):
    with _patched_llm(["The", " answer"]):
        resp = client.get("/api/query/stream", params={"q": "test"})
    events = _parse_sse(resp.text)
    texts = [e["text"] for e in events if e.get("type") == "token"]
    assert texts == ["The", " answer"]


def test_query_stream_ends_with_done_event(client):
    with _patched_llm(["tok"]):
        resp = client.get("/api/query/stream", params={"q": "test"})
    events = _parse_sse(resp.text)
    assert events[-1] == {"type": "done"}


def test_query_stream_token_events_before_done(client):
    with _patched_llm(["a", "b"]):
        resp = client.get("/api/query/stream", params={"q": "test"})
    events = _parse_sse(resp.text)
    done_idx = next(i for i, e in enumerate(events) if e.get("type") == "done")
    token_idxs = [i for i, e in enumerate(events) if e.get("type") == "token"]
    assert all(i < done_idx for i in token_idxs)


def test_query_stream_no_events_after_done(client):
    with _patched_llm(["x"]):
        resp = client.get("/api/query/stream", params={"q": "test"})
    events = _parse_sse(resp.text)
    done_idx = next(i for i, e in enumerate(events) if e.get("type") == "done")
    assert done_idx == len(events) - 1


# ── _stream_answer — retrieval routing ───────────────────────────────────────

def _collect(gen) -> list[dict]:
    return [json.loads(s.strip().removeprefix("data: ")) for s in gen if s.strip()]


def test_stream_answer_semantic_query_calls_sem_retrieve(app):
    with (
        patch("backend.routers.query.classify", return_value="semantic"),
        patch("backend.routers.query.sem_retrieve", return_value=[]) as mock_sem,
        patch("backend.routers.query.sql_retrieve") as mock_sql,
        patch("backend.routers.query.llm_stream", return_value=iter([])),
    ):
        _collect(_stream_answer("explain ACCTPAY", app.state.db, app.state.collection, "m", "u"))
    mock_sem.assert_called_once()
    mock_sql.assert_not_called()


def test_stream_answer_sql_query_calls_sql_retrieve(app):
    from backend.retrieval.sql_retriever import SqlResult
    with (
        patch("backend.routers.query.classify", return_value="sql"),
        patch("backend.routers.query.sql_retrieve", return_value=SqlResult(rows=[], sql="")) as mock_sql,
        patch("backend.routers.query.sem_retrieve") as mock_sem,
        patch("backend.routers.query.llm_stream", return_value=iter([])),
    ):
        _collect(_stream_answer("how many programs", app.state.db, app.state.collection, "m", "u"))
    mock_sql.assert_called_once()
    mock_sem.assert_not_called()


def test_stream_answer_hybrid_query_calls_both(app):
    from backend.retrieval.sql_retriever import SqlResult
    with (
        patch("backend.routers.query.classify", return_value="hybrid"),
        patch("backend.routers.query.sql_retrieve", return_value=SqlResult(rows=[], sql="")) as mock_sql,
        patch("backend.routers.query.sem_retrieve", return_value=[]) as mock_sem,
        patch("backend.routers.query.llm_stream", return_value=iter([])),
    ):
        _collect(_stream_answer("list and explain ACCTPAY", app.state.db, app.state.collection, "m", "u"))
    mock_sql.assert_called_once()
    mock_sem.assert_called_once()


def test_stream_answer_exception_yields_error_event(app):
    with patch("backend.routers.query.classify", side_effect=RuntimeError("boom")):
        events = _collect(_stream_answer("q", app.state.db, app.state.collection, "m", "u"))
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "boom" in events[0]["detail"]


def test_stream_answer_llm_error_yields_error_event(app):
    with (
        patch("backend.routers.query.classify", return_value="semantic"),
        patch("backend.routers.query.sem_retrieve", return_value=[]),
        patch("backend.routers.query.llm_stream", side_effect=ConnectionError("no ollama")),
    ):
        events = _collect(_stream_answer("q", app.state.db, app.state.collection, "m", "u"))
    assert events[0]["type"] == "error"


# ── end-to-end with real retrieval (empty DB) ─────────────────────────────────

def test_e2e_semantic_query_empty_db(client):
    """Semantic query against empty DB/Chroma returns token+done events."""
    with _patched_llm(["answer"]):
        resp = client.get("/api/query/stream", params={"q": "how does ACCTPAY work"})
    events = _parse_sse(resp.text)
    assert any(e["type"] == "token" for e in events)
    assert events[-1]["type"] == "done"


def test_e2e_sql_query_empty_db(client):
    """SQL query against empty DB returns done (no rows, LLM still runs)."""
    with _patched_llm([]):
        resp = client.get("/api/query/stream", params={"q": "how many programs are there"})
    events = _parse_sse(resp.text)
    assert events[-1]["type"] == "done"
