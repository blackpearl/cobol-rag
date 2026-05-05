from pathlib import Path

import pytest
from chromadb import Documents, Embeddings
from chromadb.utils.embedding_functions import EmbeddingFunction

from backend.ingestion.chunker import Chunk, chunk
from backend.storage.vector_store import (
    add_chunks,
    delete_program_chunks,
    get_chroma_path,
    init_collection,
    query_chunks,
)

FIXTURE = Path(__file__).parent / "fixtures" / "ACCTPAY.cbl"


class _DummyEF(EmbeddingFunction[Documents]):
    """Deterministic 384-d embedding that doesn't require a live Ollama instance."""

    def __init__(self) -> None:
        pass

    @staticmethod
    def name() -> str:
        return "dummy"

    def __call__(self, input: Documents) -> Embeddings:
        return [[0.01 * (i + 1)] * 384 for i, _ in enumerate(input)]

    @staticmethod
    def build_from_config(config: dict) -> "_DummyEF":
        return _DummyEF()

    def get_config(self) -> dict:
        return {"name": "dummy"}


_DUMMY_EF = _DummyEF()


@pytest.fixture()
def col(tmp_path):
    return init_collection(tmp_path / "chroma", embedding_fn=_DUMMY_EF)


@pytest.fixture(scope="module")
def acctpay_chunks():
    return chunk(FIXTURE)


# ── init_collection ───────────────────────────────────────────────────────────

def test_init_collection_returns_collection(col):
    import chromadb
    assert isinstance(col, chromadb.Collection)


def test_init_creates_chroma_dir(tmp_path):
    chroma_dir = tmp_path / "chroma"
    assert not chroma_dir.exists()
    init_collection(chroma_dir, embedding_fn=_DUMMY_EF)
    assert chroma_dir.is_dir()


def test_get_or_create_is_idempotent(tmp_path):
    chroma_dir = tmp_path / "chroma"
    c1 = init_collection(chroma_dir, embedding_fn=_DUMMY_EF)
    c2 = init_collection(chroma_dir, embedding_fn=_DUMMY_EF)
    assert c1.name == c2.name


# ── add_chunks ────────────────────────────────────────────────────────────────

def test_add_chunks_increases_count(col, acctpay_chunks):
    assert col.count() == 0
    add_chunks(col, program_id=1, file_path="/src/ACCTPAY.cbl", chunks=acctpay_chunks)
    assert col.count() == len(acctpay_chunks)


def test_add_chunks_stores_metadata(col, acctpay_chunks):
    add_chunks(col, program_id=1, file_path="/src/ACCTPAY.cbl", chunks=acctpay_chunks)
    first = acctpay_chunks[0]
    results = col.get(ids=[f"1:{first.start_line}:{first.end_line}"])
    meta = results["metadatas"][0]
    assert meta["program_id"] == 1
    assert meta["division"] == first.division
    assert meta["start_line"] == first.start_line
    assert meta["end_line"] == first.end_line


def test_add_chunks_upsert_does_not_duplicate(col, acctpay_chunks):
    add_chunks(col, program_id=1, file_path="/src/ACCTPAY.cbl", chunks=acctpay_chunks)
    add_chunks(col, program_id=1, file_path="/src/ACCTPAY.cbl", chunks=acctpay_chunks)
    assert col.count() == len(acctpay_chunks)


def test_add_chunks_empty_list_is_noop(col):
    add_chunks(col, program_id=99, file_path="/src/X.cbl", chunks=[])
    assert col.count() == 0


def test_add_chunks_two_programs(col, acctpay_chunks):
    add_chunks(col, program_id=1, file_path="/src/A.cbl", chunks=acctpay_chunks)
    add_chunks(col, program_id=2, file_path="/src/B.cbl", chunks=acctpay_chunks)
    assert col.count() == len(acctpay_chunks) * 2


# ── delete_program_chunks ─────────────────────────────────────────────────────

def test_delete_removes_program_chunks(col, acctpay_chunks):
    add_chunks(col, program_id=1, file_path="/src/A.cbl", chunks=acctpay_chunks)
    add_chunks(col, program_id=2, file_path="/src/B.cbl", chunks=acctpay_chunks)
    delete_program_chunks(col, program_id=1)
    assert col.count() == len(acctpay_chunks)
    remaining = col.get(where={"program_id": {"$eq": 1}})
    assert remaining["ids"] == []


def test_delete_nonexistent_program_is_noop(col, acctpay_chunks):
    add_chunks(col, program_id=1, file_path="/src/A.cbl", chunks=acctpay_chunks)
    delete_program_chunks(col, program_id=999)
    assert col.count() == len(acctpay_chunks)


# ── query_chunks ──────────────────────────────────────────────────────────────

def test_query_returns_list_of_dicts(col, acctpay_chunks):
    add_chunks(col, program_id=1, file_path="/src/ACCTPAY.cbl", chunks=acctpay_chunks)
    results = query_chunks(col, "MOVE statement", n_results=3)
    assert isinstance(results, list)
    assert len(results) <= 3
    assert all({"text", "metadata", "distance"} <= set(r.keys()) for r in results)


def test_query_respects_n_results(col, acctpay_chunks):
    add_chunks(col, program_id=1, file_path="/src/ACCTPAY.cbl", chunks=acctpay_chunks)
    results = query_chunks(col, "anything", n_results=2)
    assert len(results) == 2


def test_query_with_where_filter(col, acctpay_chunks):
    add_chunks(col, program_id=1, file_path="/src/A.cbl", chunks=acctpay_chunks)
    add_chunks(col, program_id=2, file_path="/src/B.cbl", chunks=acctpay_chunks)
    results = query_chunks(
        col, "MOVE", n_results=5, where={"program_id": {"$eq": 1}}
    )
    assert all(r["metadata"]["program_id"] == 1 for r in results)


# ── get_chroma_path ───────────────────────────────────────────────────────────

def test_get_chroma_path_reads_config(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("db_path: data/test.db\nchroma_path: data/chroma\n")
    assert get_chroma_path(cfg) == Path("data/chroma")
