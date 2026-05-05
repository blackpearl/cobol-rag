"""Tests for routers/ingest.py.

HTTP tests use FastAPI's TestClient with a real (tmp-path) SQLite DB and
ChromaDB collection so no core logic is mocked. _broadcast and _run_ingest
are tested as plain synchronous functions.
"""
from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
from random import Random
from unittest.mock import MagicMock, patch

import pytest
from chromadb import Documents, Embeddings
from chromadb.utils.embedding_functions import EmbeddingFunction
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers.ingest import _broadcast, _progress_queues, _run_ingest, router
from backend.storage.db import init_db
from backend.storage.vector_store import init_collection

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ── test helpers ──────────────────────────────────────────────────────────────

class _HashEF(EmbeddingFunction[Documents]):
    """Deterministic, direction-distinct 64-d embeddings (no Ollama needed)."""

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


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def app(tmp_path):
    application = FastAPI()
    application.include_router(router)
    application.state.db = init_db(tmp_path / "test.db")
    application.state.collection = init_collection(tmp_path / "chroma", embedding_fn=_HashEF())
    return application


@pytest.fixture()
def client(app):
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_queues():
    _progress_queues.clear()
    yield
    _progress_queues.clear()


# ── POST /api/ingest ──────────────────────────────────────────────────────────

def test_post_invalid_path_returns_400(client):
    resp = client.post("/api/ingest", json={"path": "/no/such/directory/xyz"})
    assert resp.status_code == 400


def test_post_invalid_path_error_message(client):
    resp = client.post("/api/ingest", json={"path": "/no/such/directory/xyz"})
    assert "not found" in resp.json()["detail"].lower()


def test_post_valid_path_returns_200(client):
    resp = client.post("/api/ingest", json={"path": str(FIXTURE_DIR)})
    assert resp.status_code == 200


def test_post_response_status_is_started(client):
    resp = client.post("/api/ingest", json={"path": str(FIXTURE_DIR)})
    assert resp.json()["status"] == "started"


def test_post_files_found_matches_cbl_count(client):
    from backend.ingestion.scanner import scan
    expected = len(scan(FIXTURE_DIR))
    resp = client.post("/api/ingest", json={"path": str(FIXTURE_DIR)})
    assert resp.json()["files_found"] == expected


def test_post_files_found_is_nonzero(client):
    resp = client.post("/api/ingest", json={"path": str(FIXTURE_DIR)})
    assert resp.json()["files_found"] > 0


def test_post_indexes_program_in_db(client, app):
    client.post("/api/ingest", json={"path": str(FIXTURE_DIR)})
    rows = app.state.db.execute("SELECT name FROM programs").fetchall()
    assert len(rows) > 0


def test_post_indexes_chunks_in_vector_store(client, app):
    client.post("/api/ingest", json={"path": str(FIXTURE_DIR)})
    assert app.state.collection.count() > 0


def test_post_idempotent_double_ingest(client, app):
    client.post("/api/ingest", json={"path": str(FIXTURE_DIR)})
    count_after_first = app.state.collection.count()
    client.post("/api/ingest", json={"path": str(FIXTURE_DIR)})
    count_after_second = app.state.collection.count()
    assert count_after_first == count_after_second


# ── WS /ws/ingest-progress ────────────────────────────────────────────────────

def test_ws_connection_accepted(client):
    with client.websocket_connect("/ws/ingest-progress"):
        pass


def test_ws_queue_registered_on_connect(client):
    with client.websocket_connect("/ws/ingest-progress"):
        # Poll briefly: queue is appended after accept() in the server coroutine.
        deadline = time.monotonic() + 3
        while not _progress_queues and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(_progress_queues) == 1


def test_ws_queue_removed_on_disconnect(client):
    with client.websocket_connect("/ws/ingest-progress"):
        pass
    assert len(_progress_queues) == 0


def test_ws_receives_progress_events(client):
    """WS client receives start/progress/done events during a POST ingest."""
    received: list[dict] = []
    ready = threading.Event()

    def ws_reader():
        with client.websocket_connect("/ws/ingest-progress") as ws:
            ready.set()
            while True:
                data = ws.receive_json()
                received.append(data)
                if data.get("event") == "done":
                    break

    t = threading.Thread(target=ws_reader, daemon=True)
    t.start()
    assert ready.wait(timeout=5), "WebSocket failed to connect"

    # Poll until the queue is registered in the server coroutine before POST.
    deadline = time.monotonic() + 5
    while not _progress_queues and time.monotonic() < deadline:
        time.sleep(0.01)

    resp = client.post("/api/ingest", json={"path": str(FIXTURE_DIR)})
    assert resp.status_code == 200
    t.join(timeout=30)

    event_types = {e.get("event") for e in received}
    assert "start" in event_types
    assert "done" in event_types


# ── _broadcast unit tests ─────────────────────────────────────────────────────

def test_broadcast_delivers_to_single_queue():
    q: queue.Queue = queue.Queue()
    _progress_queues.append(q)
    _broadcast({"event": "ping"})
    assert not q.empty()
    assert q.get_nowait() == {"event": "ping"}
    _progress_queues.remove(q)


def test_broadcast_delivers_to_multiple_queues():
    q1: queue.Queue = queue.Queue()
    q2: queue.Queue = queue.Queue()
    _progress_queues.extend([q1, q2])
    _broadcast({"event": "multi"})
    assert q1.get_nowait() == {"event": "multi"}
    assert q2.get_nowait() == {"event": "multi"}
    _progress_queues.remove(q1)
    _progress_queues.remove(q2)


def test_broadcast_noop_when_no_queues():
    _broadcast({"event": "ignored"})  # must not raise


# ── _run_ingest unit tests (sync, mocked pipeline) ────────────────────────────

def _make_mock_struct():
    s = MagicMock()
    s.program_id = "TEST"
    s.path = "/src/TEST.cbl"
    return s


def test_run_ingest_broadcasts_start_and_done():
    q: queue.Queue = queue.Queue()
    _progress_queues.append(q)

    with (
        patch("backend.routers.ingest.extract_struct", return_value=_make_mock_struct()),
        patch("backend.routers.ingest.upsert_program", return_value=1),
        patch("backend.routers.ingest.chunk", return_value=[]),
        patch("backend.routers.ingest.delete_program_chunks"),
        patch("backend.routers.ingest.add_chunks"),
    ):
        _run_ingest([Path("dummy.cbl")], MagicMock(), MagicMock())

    _progress_queues.remove(q)
    events = list(q.queue)
    types = [e["event"] for e in events]
    assert "start" in types
    assert "done" in types


def test_run_ingest_broadcasts_progress_per_file():
    q: queue.Queue = queue.Queue()
    _progress_queues.append(q)

    with (
        patch("backend.routers.ingest.extract_struct", return_value=_make_mock_struct()),
        patch("backend.routers.ingest.upsert_program", return_value=1),
        patch("backend.routers.ingest.chunk", return_value=[]),
        patch("backend.routers.ingest.delete_program_chunks"),
        patch("backend.routers.ingest.add_chunks"),
    ):
        _run_ingest([Path("A.cbl"), Path("B.cbl")], MagicMock(), MagicMock())

    _progress_queues.remove(q)
    progress = [e for e in list(q.queue) if e["event"] == "progress"]
    assert len(progress) == 2


def test_run_ingest_file_error_broadcasts_file_error_event():
    q: queue.Queue = queue.Queue()
    _progress_queues.append(q)

    with patch("backend.routers.ingest.extract_struct", side_effect=RuntimeError("boom")):
        _run_ingest([Path("bad.cbl")], MagicMock(), MagicMock())

    _progress_queues.remove(q)
    assert any(e["event"] == "file_error" for e in list(q.queue))


def test_run_ingest_done_indexed_count():
    q: queue.Queue = queue.Queue()
    _progress_queues.append(q)

    files = [Path("A.cbl"), Path("B.cbl"), Path("bad.cbl")]

    def _extract(fp):
        if fp.name == "bad.cbl":
            raise ValueError("parse error")
        return _make_mock_struct()

    with (
        patch("backend.routers.ingest.extract_struct", side_effect=_extract),
        patch("backend.routers.ingest.upsert_program", return_value=1),
        patch("backend.routers.ingest.chunk", return_value=[]),
        patch("backend.routers.ingest.delete_program_chunks"),
        patch("backend.routers.ingest.add_chunks"),
    ):
        _run_ingest(files, MagicMock(), MagicMock())

    _progress_queues.remove(q)
    events = list(q.queue)
    done = next(e for e in events if e["event"] == "done")
    assert done["indexed"] == 2
    assert done["total"] == 3
