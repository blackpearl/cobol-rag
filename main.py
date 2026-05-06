from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.routers.ingest import router as ingest_router
from backend.routers.query import router as query_router
from backend.routers.workspaces import router as workspaces_router
from backend.storage.db import init_db
from backend.storage.vector_store import get_ollama_ef, init_collection

_CONFIG_PATH = Path(__file__).parent / "config.yaml"


def _load_config() -> dict:
    with _CONFIG_PATH.open() as fh:
        return yaml.safe_load(fh)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = _load_config()
    app.state.db = init_db(Path(cfg["db_path"]))
    ef = get_ollama_ef(
        url=cfg.get("ollama_url", "http://localhost:11434"),
        model=cfg.get("embed_model", "nomic-embed-text"),
    )
    app.state.collection = init_collection(Path(cfg["chroma_path"]), embedding_fn=ef)
    app.state.llm_model = cfg.get("llm_model", "llama3.2:8b")
    app.state.ollama_url = cfg.get("ollama_url", "http://localhost:11434")
    yield
    app.state.db.close()


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    application = FastAPI(title="COBOL RAG", version="0.1.0", lifespan=lifespan)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],  # Vite dev server
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(ingest_router)
    application.include_router(query_router)
    application.include_router(workspaces_router)

    # Static frontend — only mounted when built; absent during development and CI.
    frontend = Path(__file__).parent / "frontend" / "dist"
    if frontend.is_dir():
        application.mount(
            "/", StaticFiles(directory=str(frontend), html=True), name="frontend"
        )

    return application


app = create_app()
