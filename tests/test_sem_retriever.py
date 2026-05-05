from pathlib import Path
from random import Random

import numpy as np
import pytest
from chromadb import Documents, Embeddings
from chromadb.utils.embedding_functions import EmbeddingFunction

from backend.ingestion.chunker import chunk
from backend.retrieval.sem_retriever import _mmr, retrieve
from backend.storage.vector_store import add_chunks, init_collection

FIXTURE = Path(__file__).parent / "fixtures" / "ACCTPAY.cbl"


class _HashEF(EmbeddingFunction[Documents]):
    """Deterministic, direction-distinct 64-d embeddings (no Ollama needed)."""

    def __init__(self) -> None:
        pass

    @staticmethod
    def name() -> str:
        return "hash-test"

    def __call__(self, input: Documents) -> Embeddings:
        result = []
        for text in input:
            rng = Random(abs(hash(text)) % (2**31))
            vec = [rng.gauss(0, 1) for _ in range(64)]
            norm = sum(x * x for x in vec) ** 0.5 or 1.0
            result.append([x / norm for x in vec])
        return result

    @staticmethod
    def build_from_config(config: dict) -> "_HashEF":
        return _HashEF()

    def get_config(self) -> dict:
        return {"name": "hash-test"}


_EF = _HashEF()


@pytest.fixture(scope="module")
def col(tmp_path_factory):
    path = tmp_path_factory.mktemp("chroma")
    c = init_collection(path, embedding_fn=_EF)
    chunks = chunk(FIXTURE)
    add_chunks(c, program_id=1, file_path=str(FIXTURE), chunks=chunks)
    return c


# ── retrieve — integration ────────────────────────────────────────────────────

def test_retrieve_returns_list_of_dicts(col):
    results = retrieve(col, "MOVE statement")
    assert isinstance(results, list)
    assert all({"text", "metadata", "distance"} <= set(r.keys()) for r in results)


def test_retrieve_respects_k(col):
    results = retrieve(col, "vendor processing", k=3, fetch_k=10)
    assert len(results) <= 3


def test_retrieve_returns_nonempty_for_valid_query(col):
    results = retrieve(col, "EXEC SQL SELECT")
    assert len(results) > 0


def test_retrieve_text_is_string(col):
    results = retrieve(col, "CALL statement", k=2)
    assert all(isinstance(r["text"], str) for r in results)


def test_retrieve_metadata_has_expected_keys(col):
    results = retrieve(col, "PROCEDURE DIVISION", k=2)
    for r in results:
        meta = r["metadata"]
        assert "program_id" in meta
        assert "division" in meta
        assert "start_line" in meta
        assert "end_line" in meta


def test_retrieve_where_filter(col):
    results = retrieve(
        col, "MOVE", k=3, where={"program_id": {"$eq": 1}}
    )
    assert all(r["metadata"]["program_id"] == 1 for r in results)


def test_retrieve_empty_collection(tmp_path):
    empty = init_collection(tmp_path / "empty", embedding_fn=_EF)
    assert retrieve(empty, "anything") == []


def test_retrieve_k_larger_than_collection(tmp_path):
    small = init_collection(tmp_path / "small", embedding_fn=_EF)
    chunks = chunk(FIXTURE)[:3]
    add_chunks(small, program_id=1, file_path=str(FIXTURE), chunks=chunks)
    results = retrieve(small, "MOVE", k=100)
    assert len(results) <= 3


def test_retrieve_distance_is_float(col):
    results = retrieve(col, "OPEN INPUT", k=2)
    assert all(isinstance(r["distance"], float) for r in results)


# ── _mmr — unit tests with controlled geometry ────────────────────────────────

def _unit(v: list) -> list:
    a = np.array(v, dtype=float)
    return (a / np.linalg.norm(a)).tolist()


def test_mmr_selects_k_items():
    embs = [_unit([1, 0, 0]), _unit([0, 1, 0]), _unit([0, 0, 1])]
    sims = [0.9, 0.8, 0.5]
    assert len(_mmr(embs, sims, k=2, lambda_mult=0.5)) == 2


def test_mmr_first_pick_is_most_relevant():
    embs = [_unit([1, 0]), _unit([0, 1]), _unit([0.7, 0.7])]
    sims = [0.9, 0.3, 0.5]
    selected = _mmr(embs, sims, k=1, lambda_mult=1.0)
    assert selected[0] == 0  # highest query similarity


def test_mmr_prefers_diversity_over_redundancy():
    # Doc 0: most relevant, direction [1,0]
    # Doc 1: slightly less relevant, nearly same direction as doc 0
    # Doc 2: less relevant, orthogonal to doc 0
    # After picking doc 0, MMR should prefer doc 2 (diverse) over doc 1 (redundant)
    embs = [
        _unit([1.0, 0.0]),    # doc 0
        _unit([0.99, 0.14]),  # doc 1 — near-identical direction to doc 0
        _unit([0.0, 1.0]),    # doc 2 — orthogonal
    ]
    sims = [1.0, 0.85, 0.5]
    selected = _mmr(embs, sims, k=2, lambda_mult=0.5)
    assert selected[0] == 0  # most relevant first
    assert selected[1] == 2  # diverse doc preferred over redundant doc 1


def test_mmr_lambda_1_pure_relevance():
    # lambda=1.0 → pure relevance (ignore diversity)
    embs = [_unit([1, 0]), _unit([0.99, 0.14]), _unit([0, 1])]
    sims = [1.0, 0.9, 0.5]
    selected = _mmr(embs, sims, k=2, lambda_mult=1.0)
    # With pure relevance, picks top-2 by sim: docs 0 and 1
    assert set(selected) == {0, 1}


def test_mmr_empty_embeddings():
    assert _mmr([], [], k=5, lambda_mult=0.5) == []


def test_mmr_k_larger_than_n_returns_all():
    embs = [_unit([1, 0]), _unit([0, 1])]
    sims = [0.9, 0.5]
    result = _mmr(embs, sims, k=10, lambda_mult=0.5)
    assert len(result) == 2


def test_mmr_no_duplicate_indices():
    embs = [_unit([1, 0, 0]), _unit([0, 1, 0]), _unit([0, 0, 1]),
            _unit([1, 1, 0]), _unit([0, 1, 1])]
    sims = [0.9, 0.8, 0.7, 0.6, 0.5]
    selected = _mmr(embs, sims, k=4, lambda_mult=0.5)
    assert len(selected) == len(set(selected))
