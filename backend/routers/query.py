from __future__ import annotations

import json
from typing import Generator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from backend.generation.context_builder import build_context
from backend.generation.llm import stream as llm_stream
from backend.retrieval.classifier import classify
from backend.retrieval.sem_retriever import retrieve as sem_retrieve
from backend.retrieval.sql_retriever import retrieve as sql_retrieve

router = APIRouter()

_DEFAULT_MODEL = "llama3.2:8b"
_DEFAULT_OLLAMA_URL = "http://localhost:11434"


@router.get("/api/query/stream")
async def query_stream(q: str, request: Request) -> StreamingResponse:
    """Stream an LLM answer to the natural-language query as Server-Sent Events.

    Each SSE event body is JSON with one of these shapes:
      {"type": "token",  "text": "..."}   — one LLM output chunk
      {"type": "done"}                     — stream complete
      {"type": "error",  "detail": "..."}  — unhandled exception
    """
    conn = request.app.state.db
    collection = request.app.state.collection
    model = getattr(request.app.state, "llm_model", _DEFAULT_MODEL)
    ollama_url = getattr(request.app.state, "ollama_url", _DEFAULT_OLLAMA_URL)

    return StreamingResponse(
        _stream_answer(q, conn, collection, model, ollama_url),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _stream_answer(
    query: str,
    conn,
    collection,
    model: str,
    ollama_url: str,
) -> Generator[str, None, None]:
    """Classify → retrieve → build prompt → stream tokens as SSE data lines."""
    try:
        query_type = classify(query)

        sql_rows = []
        if query_type in ("sql", "hybrid"):
            sql_rows = sql_retrieve(conn, query).rows

        sem_chunks = []
        if query_type in ("semantic", "hybrid"):
            sem_chunks = sem_retrieve(collection, query)

        prompt = build_context(
            query,
            sql_rows=sql_rows or None,
            sem_chunks=sem_chunks or None,
        )

        for token in llm_stream(prompt, model=model, base_url=ollama_url):
            yield _sse({"type": "token", "text": token})

        yield _sse({"type": "done"})

    except Exception as exc:
        yield _sse({"type": "error", "detail": str(exc)})


def _sse(data: dict) -> str:
    """Format a dict as a single SSE data line."""
    return f"data: {json.dumps(data)}\n\n"
