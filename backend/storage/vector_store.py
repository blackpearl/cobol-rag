from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import chromadb
import yaml
from chromadb.utils.embedding_functions import EmbeddingFunction, OllamaEmbeddingFunction

from backend.ingestion.chunker import Chunk

EmbeddingFn = EmbeddingFunction

_COLLECTION = "cobol_chunks"


def get_chroma_path(config_path: Optional[Path] = None) -> Path:
    """Return the ChromaDB persistence directory read from config.yaml."""
    if config_path is None:
        config_path = Path(__file__).parents[2] / "config.yaml"
    with config_path.open() as fh:
        cfg = yaml.safe_load(fh)
    return Path(cfg["chroma_path"])


def get_ollama_ef(
    url: str = "http://localhost:11434",
    model: str = "nomic-embed-text",
) -> OllamaEmbeddingFunction:
    """Return an Ollama embedding function for the given model."""
    return OllamaEmbeddingFunction(url=url, model_name=model)


def init_collection(
    chroma_path: Path,
    collection_name: str = _COLLECTION,
    embedding_fn: Optional[EmbeddingFn] = None,
) -> chromadb.Collection:
    """Open (or create) a persistent ChromaDB collection.

    Pass embedding_fn explicitly in tests to avoid requiring a live Ollama
    instance. Omit it in production to use the default Ollama embedding.
    """
    if embedding_fn is None:
        embedding_fn = get_ollama_ef()
    chroma_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_path))
    return client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_fn,
    )


def add_chunks(
    collection: chromadb.Collection,
    program_id: int,
    file_path: str,
    chunks: List[Chunk],
) -> None:
    """Upsert chunks for one program into the collection.

    IDs are stable across re-index calls with the same content so that
    upsert naturally deduplicates unchanged chunks.
    """
    if not chunks:
        return
    collection.upsert(
        ids=[f"{program_id}:{c.start_line}:{c.end_line}" for c in chunks],
        documents=[c.text for c in chunks],
        metadatas=[
            {
                "program_id": program_id,
                "file_path": file_path,
                "division": c.division,
                "start_line": c.start_line,
                "end_line": c.end_line,
            }
            for c in chunks
        ],
    )


def delete_program_chunks(
    collection: chromadb.Collection,
    program_id: int,
) -> None:
    """Remove all chunks belonging to a program (called before re-indexing)."""
    collection.delete(where={"program_id": {"$eq": program_id}})


def query_chunks(
    collection: chromadb.Collection,
    query_text: str,
    n_results: int = 5,
    where: Optional[dict] = None,
) -> List[dict]:
    """Return the top-n most similar chunks as dicts with text, metadata, distance."""
    kwargs: dict = {"query_texts": [query_text], "n_results": n_results}
    if where:
        kwargs["where"] = where
    results = collection.query(**kwargs)
    return [
        {"text": doc, "metadata": meta, "distance": dist}
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    ]
