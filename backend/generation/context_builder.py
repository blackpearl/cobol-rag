from __future__ import annotations

from pathlib import Path
from typing import List, Optional


_PREAMBLE = (
    "You are an expert COBOL analyst. "
    "Answer the user's question using only the context provided below. "
    "If the context is insufficient, say so explicitly.\n\n"
)
_CHUNK_SEP = "\n---\n"


def build_context(
    query: str,
    sql_rows: Optional[List[dict]] = None,
    sem_chunks: Optional[List[dict]] = None,
    max_chars: int = 12_000,
) -> str:
    """Assemble an LLM prompt from SQL result rows and semantic code chunks.

    Sections are filled in order: preamble → question → SQL data → code chunks.
    Each section consumes from the character budget; once exhausted, later
    content is truncated rather than omitted entirely.
    """
    question_block = f"## Question\n{query.strip()}\n\n"
    fixed = _PREAMBLE + question_block
    budget = max_chars - len(fixed)

    sql_block = _format_sql(sql_rows) if sql_rows else ""
    if sql_block:
        if len(sql_block) <= budget:
            budget -= len(sql_block)
        else:
            sql_block = sql_block[:budget]
            budget = 0

    chunk_block = ""
    if sem_chunks and budget > 0:
        chunk_block = _format_chunks(sem_chunks, budget)

    return (fixed + sql_block + chunk_block)[:max_chars]


# ── section formatters ────────────────────────────────────────────────────────

def _format_sql(rows: List[dict]) -> str:
    """Render SQL result rows as a readable key-value table."""
    if not rows:
        return ""
    lines = ["## Structured Data\n"]
    for row in rows:
        lines.append("  " + " | ".join(f"{k}: {v}" for k, v in row.items()))
    lines.append("\n\n")
    return "\n".join(lines)


def _format_chunks(chunks: List[dict], budget: int) -> str:
    """Render semantic chunks with metadata headers, truncating to budget chars."""
    header = "## Relevant Code\n"
    remaining = budget - len(header)
    if remaining <= 0:
        return ""

    parts = [header]
    for chunk in chunks:
        if remaining <= 0:
            break
        block = _format_one_chunk(chunk)
        if len(block) > remaining:
            parts.append(block[:remaining])
            remaining = 0
        else:
            parts.append(block)
            remaining -= len(block)

    return "".join(parts)


def _format_one_chunk(chunk: dict) -> str:
    meta = chunk.get("metadata", {})
    division = meta.get("division", "?")
    start = meta.get("start_line", "?")
    end = meta.get("end_line", "?")
    raw_path = meta.get("file_path", "")
    filename = Path(raw_path).name if raw_path else "unknown"
    header = f"[{filename} | {division} | lines {start}–{end}]\n"
    return header + chunk.get("text", "") + _CHUNK_SEP
