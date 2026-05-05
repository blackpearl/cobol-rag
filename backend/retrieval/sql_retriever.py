from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple


@dataclass
class SqlResult:
    rows: List[dict]
    sql: str


def retrieve(conn: sqlite3.Connection, query: str) -> SqlResult:
    """Map a natural-language SQL-class query to the SQLite schema and return rows.

    Patterns are matched in order; the first hit wins. Falls back to listing
    all programs when no pattern matches.
    """
    for pattern, handler in _DISPATCH:
        m = pattern.search(query)
        if m:
            return handler(conn, query, m)
    return _list_programs(conn, query, None)


# ── internal helpers ──────────────────────────────────────────────────────────

def _fetchall(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> List[dict]:
    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _entity(m: re.Match, group: int = 1) -> str:
    """Strip trailing punctuation and uppercase the captured identifier."""
    return re.sub(r"[?.,!;:]+$", "", m.group(group)).upper()


def _op_type(query: str) -> Optional[str]:
    """Infer an op_type filter from verb keywords (R / W / BR)."""
    q = query.lower()
    if any(w in q for w in ("write", "update", "insert", "delete", "modify")):
        return "W"
    if "browse" in q:
        return "BR"
    if any(w in q for w in ("read", "select", "fetch")):
        return "R"
    return None


def _op_clause(query: str, alias: str) -> Tuple[str, list]:
    op = _op_type(query)
    if op:
        return f"AND {alias}.op_type = ?", [op]
    return "", []


# ── query handlers ────────────────────────────────────────────────────────────

def _count_programs(conn, query, m) -> SqlResult:
    sql = "SELECT COUNT(*) AS count FROM programs"
    return SqlResult(rows=_fetchall(conn, sql), sql=sql)


def _program_metrics(conn, query, m) -> SqlResult:
    name = _entity(m)
    sql = (
        "SELECT name, loc, move_count, linkage_count, indexed_at "
        "FROM programs WHERE name = ?"
    )
    return SqlResult(rows=_fetchall(conn, sql, (name,)), sql=sql)


def _list_programs(conn, query, m) -> SqlResult:
    sql = (
        "SELECT name, path, loc, move_count, linkage_count "
        "FROM programs ORDER BY name"
    )
    return SqlResult(rows=_fetchall(conn, sql), sql=sql)


def _callers_of_module(conn, query, m) -> SqlResult:
    module = _entity(m)
    sql = (
        "SELECT p.name AS program, p.path "
        "FROM programs p JOIN modules mo ON mo.program_id = p.id "
        "WHERE mo.called_name = ?"
    )
    return SqlResult(rows=_fetchall(conn, sql, (module,)), sql=sql)


def _calls_from_program(conn, query, m) -> SqlResult:
    name = _entity(m)
    sql = (
        "SELECT mo.called_name "
        "FROM modules mo JOIN programs p ON mo.program_id = p.id "
        "WHERE p.name = ?"
    )
    return SqlResult(rows=_fetchall(conn, sql, (name,)), sql=sql)


def _files_of_program(conn, query, m) -> SqlResult:
    name = _entity(m)
    op_where, op_params = _op_clause(query, "f")
    sql = (
        f"SELECT f.file_name, f.op_type "
        f"FROM files_ref f JOIN programs p ON f.program_id = p.id "
        f"WHERE p.name = ? {op_where}"
    )
    return SqlResult(rows=_fetchall(conn, sql, (name, *op_params)), sql=sql)


def _programs_for_file(conn, query, m) -> SqlResult:
    file_name = _entity(m)
    op_where, op_params = _op_clause(query, "f")
    sql = (
        f"SELECT p.name AS program, f.op_type "
        f"FROM programs p JOIN files_ref f ON f.program_id = p.id "
        f"WHERE f.file_name = ? {op_where}"
    )
    return SqlResult(rows=_fetchall(conn, sql, (file_name, *op_params)), sql=sql)


def _tables_of_program(conn, query, m) -> SqlResult:
    name = _entity(m)
    op_where, op_params = _op_clause(query, "t")
    sql = (
        f"SELECT t.table_name, t.op_type "
        f"FROM tables_ref t JOIN programs p ON t.program_id = p.id "
        f"WHERE p.name = ? {op_where}"
    )
    return SqlResult(rows=_fetchall(conn, sql, (name, *op_params)), sql=sql)


def _programs_for_table(conn, query, m) -> SqlResult:
    table = _entity(m)
    op_where, op_params = _op_clause(query, "t")
    sql = (
        f"SELECT p.name AS program, t.op_type "
        f"FROM programs p JOIN tables_ref t ON t.program_id = p.id "
        f"WHERE t.table_name = ? {op_where}"
    )
    return SqlResult(rows=_fetchall(conn, sql, (table, *op_params)), sql=sql)


# ── dispatch table (first match wins) ─────────────────────────────────────────

_Handler = Callable[[sqlite3.Connection, str, Optional[re.Match]], SqlResult]
_DISPATCH: list[Tuple[re.Pattern, _Handler]] = [
    # counting
    (re.compile(r"how\s+many\s+programs", re.I), _count_programs),
    (re.compile(r"number\s+of\s+programs", re.I), _count_programs),
    # program-level scalar metrics
    (re.compile(r"\bloc\b\s+(?:for|of)\s+(\S+)", re.I), _program_metrics),
    (re.compile(r"lines?\s+of\s+code\s+(?:for|of)\s+(\S+)", re.I), _program_metrics),
    (re.compile(r"move[\s_-]count\s+(?:for|of)\s+(\S+)", re.I), _program_metrics),
    (re.compile(r"how\s+many\s+move\s+statements?\s+does\s+(\S+)", re.I), _program_metrics),
    # callers of a module
    (re.compile(r"which\s+programs?\s+call\s+(\S+)", re.I), _callers_of_module),
    (re.compile(r"what\s+programs?\s+call\s+(\S+)", re.I), _callers_of_module),
    # callees of a program
    (re.compile(r"what\s+(?:modules?|calls?)\s+does\s+(\S+)\s+(?:call|make)", re.I), _calls_from_program),
    (re.compile(r"which\s+modules?\s+(?:does\s+)?(\S+)\s+call", re.I), _calls_from_program),
    # file queries — program → files
    (re.compile(r"what\s+files?\s+does\s+(\S+)", re.I), _files_of_program),
    (re.compile(r"which\s+files?\s+does\s+(\S+)", re.I), _files_of_program),
    # file queries — file → programs (read/write verbs signal files)
    (re.compile(r"which\s+programs?\s+(?:read|write)\s+(\S+)", re.I), _programs_for_file),
    # table queries — program → tables
    (re.compile(r"what\s+tables?\s+does\s+(\S+)", re.I), _tables_of_program),
    (re.compile(r"which\s+tables?\s+does\s+(\S+)", re.I), _tables_of_program),
    # table queries — table → programs (access/update verbs signal tables)
    (re.compile(r"which\s+programs?\s+(?:access|update)\s+(\S+)", re.I), _programs_for_table),
    # listing
    (re.compile(r"list\s+(?:all\s+)?programs", re.I), _list_programs),
]
