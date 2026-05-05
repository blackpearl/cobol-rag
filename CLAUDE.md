# COBOL RAG Analysis System

## Architecture overview
RAG system for querying COBOL codebases using natural language.
Full architecture documented in /docs/architecture.md (reference this).

## Stack
- Backend: Python 3.11, FastAPI, uvicorn (single process serves frontend too)
- Frontend: React 18 + Vite + TypeScript
- LLM: Ollama → llama3.2:8b (local only, no cloud calls ever)
- Embeddings: Ollama → nomic-embed-text
- Vector store: ChromaDB (persisted to ./data/chroma/)
- Structured store: SQLite (./data/cobol_rag.db)
- API patterns: REST (JSON), SSE for LLM streaming, WebSocket for ingest progress

## Module map
ingestion/scanner.py       → recursive .cbl/.cob/.cpy discovery
ingestion/metric_extractor.py → LOC, MOVE count, linkage vars, called modules, file ops
ingestion/struct_extractor.py → CALL targets, EXEC SQL table refs, op types
ingestion/chunker.py       → division-aware chunking with sliding window
storage/db.py              → SQLite schema + write helpers
storage/vector_store.py    → ChromaDB wrapper (embed + retrieve)
retrieval/classifier.py    → route query: sql | semantic | hybrid
retrieval/sql_retriever.py → structured SQL query builder
retrieval/sem_retriever.py → top-k vector search + MMR rerank
generation/context_builder.py → merge SQL rows + chunks into prompt
generation/llm.py          → Ollama streaming wrapper
routers/ingest.py          → POST /api/ingest + WS /ws/ingest-progress
routers/query.py           → SSE GET /api/query/stream
routers/workspaces.py      → GET /api/workspaces, /api/programs/{id}
main.py                    → FastAPI app, mounts frontend/dist at "/"

## SQLite schema (4 tables)
programs(id, name, path, loc, move_count, linkage_count, indexed_at)
modules(id, program_id, called_name)
tables_ref(id, program_id, table_name, op_type)   -- op_type: R|W|BR
files_ref(id, program_id, file_name, op_type)     -- op_type: R|W

## Coding rules
- Type hints on all Python functions, docstrings on public methods
- Never hardcode folder paths — always read from config.yaml
- FastAPI endpoints return JSON; streaming via SSE (text/event-stream)
- WebSocket for ingest progress only
- COBOL chunks must respect division boundaries before applying sliding window
- Do NOT mock core logic in tests — use real .cbl fixture files in tests/fixtures/

## Do NOT
- Make any outbound network calls (all local)
- Add authentication in this prototype
- Install any paid or cloud-only libraries