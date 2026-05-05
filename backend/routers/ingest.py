from __future__ import annotations

import asyncio
import queue as _stdlib_queue
from pathlib import Path
from typing import List

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from backend.ingestion.chunker import chunk
from backend.ingestion.scanner import scan
from backend.ingestion.struct_extractor import extract_struct
from backend.storage.db import upsert_program
from backend.storage.vector_store import add_chunks, delete_program_chunks

router = APIRouter()

# One thread-safe Queue per connected WebSocket client.
# Using stdlib queue.Queue so _broadcast can be called from any thread (e.g.
# BackgroundTasks runs sync functions in a threadpool, not the ASGI event loop).
_progress_queues: List[_stdlib_queue.Queue] = []


class IngestRequest(BaseModel):
    path: str


class IngestResponse(BaseModel):
    status: str
    files_found: int


@router.post("/api/ingest", response_model=IngestResponse)
async def ingest(req: IngestRequest, request: Request, background_tasks: BackgroundTasks) -> IngestResponse:
    """Scan a directory for COBOL files and index them in the background.

    Returns immediately after scanning; indexing happens asynchronously with
    progress streamed over /ws/ingest-progress.
    """
    root = Path(req.path)
    if not root.is_dir():
        raise HTTPException(status_code=400, detail=f"Directory not found: {req.path}")

    conn = request.app.state.db
    collection = request.app.state.collection
    files = scan(root)
    background_tasks.add_task(_run_ingest, files, conn, collection)
    return IngestResponse(status="started", files_found=len(files))


@router.websocket("/ws/ingest-progress")
async def ingest_progress(websocket: WebSocket) -> None:
    """Stream JSON progress events to the client until ingestion completes."""
    await websocket.accept()
    q: _stdlib_queue.Queue = _stdlib_queue.Queue()
    _progress_queues.append(q)
    loop = asyncio.get_running_loop()
    try:
        while True:
            # Delegate the blocking q.get() to the thread pool so the event
            # loop remains free. A 60 s timeout prevents zombie connections.
            try:
                event = await loop.run_in_executor(
                    None, lambda: q.get(timeout=60)
                )
            except _stdlib_queue.Empty:
                break
            await websocket.send_json(event)
            if event.get("event") == "done":
                break
    except WebSocketDisconnect:
        pass
    finally:
        if q in _progress_queues:
            _progress_queues.remove(q)


def _run_ingest(files: List[Path], conn, collection) -> None:
    """Index each COBOL file: struct → DB upsert → chunk → vector store.

    Runs synchronously in a thread pool (via BackgroundTasks). Thread-safe
    _broadcast is safe to call here.
    """
    total = len(files)
    _broadcast({"event": "start", "total": total})
    indexed = 0
    for i, fp in enumerate(files, 1):
        try:
            struct = extract_struct(fp)
            program_id = upsert_program(conn, struct)
            chunks = chunk(fp)
            delete_program_chunks(collection, program_id)
            add_chunks(collection, program_id, str(fp), chunks)
            indexed += 1
            _broadcast({"event": "progress", "file": fp.name, "current": i, "total": total})
        except Exception as exc:
            _broadcast({"event": "file_error", "file": fp.name, "detail": str(exc)})
    _broadcast({"event": "done", "indexed": indexed, "total": total})


def _broadcast(event: dict) -> None:
    """Put an event into every registered WebSocket client queue (thread-safe)."""
    for q in list(_progress_queues):
        q.put_nowait(event)
