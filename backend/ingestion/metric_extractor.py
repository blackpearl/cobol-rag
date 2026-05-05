from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class ExtractedMetrics:
    loc: int
    move_count: int
    linkage_vars: List[str] = field(default_factory=list)
    called_modules: List[str] = field(default_factory=list)
    file_ops: List[dict] = field(default_factory=list)
    table_refs: List[dict] = field(default_factory=list)


_MOVE_RE = re.compile(r'^\s+MOVE\s', re.IGNORECASE)
_LINKAGE_RE = re.compile(r'\bLINKAGE\s+SECTION\b', re.IGNORECASE)
_NEXT_SECTION_RE = re.compile(r'^\s+\w[\w-]*\s+(?:SECTION|DIVISION)\b', re.IGNORECASE)
_LEVEL_01_RE = re.compile(r'^\s+01\s+([\w-]+)', re.IGNORECASE)
_CALL_RE = re.compile(r"CALL\s+['\"]([^'\"]+)['\"]", re.IGNORECASE)
_PROC_DIV_RE = re.compile(r'^\s+PROCEDURE\s+DIVISION\b', re.IGNORECASE)

_OPEN_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'OPEN\s+INPUT\s+([\w-]+)', re.IGNORECASE), 'R'),
    (re.compile(r'OPEN\s+OUTPUT\s+([\w-]+)', re.IGNORECASE), 'W'),
    (re.compile(r'OPEN\s+I-O\s+([\w-]+)', re.IGNORECASE), 'W'),
    (re.compile(r'OPEN\s+EXTEND\s+([\w-]+)', re.IGNORECASE), 'W'),
    (re.compile(r'\bSTART\s+([\w-]+)', re.IGNORECASE), 'BR'),
]

_SQL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'SELECT\b.*?\bFROM\s+(\w+)', re.IGNORECASE | re.DOTALL), 'R'),
    (re.compile(r'INSERT\s+INTO\s+(\w+)', re.IGNORECASE), 'W'),
    (re.compile(r'UPDATE\s+(\w+)\s+SET', re.IGNORECASE), 'W'),
    (re.compile(r'DELETE\s+FROM\s+(\w+)', re.IGNORECASE), 'W'),
]


def extract_metrics(file_path: Path) -> ExtractedMetrics:
    """Parse a single COBOL source file and return structural metrics."""
    text = file_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    return ExtractedMetrics(
        loc=_count_loc(lines),
        move_count=_count_moves(lines),
        linkage_vars=_extract_linkage_vars(lines),
        called_modules=_extract_called_modules(text),
        file_ops=_extract_file_ops(lines),
        table_refs=_extract_table_refs(text),
    )


def _count_loc(lines: List[str]) -> int:
    return sum(1 for line in lines if line.strip())


def _count_moves(lines: List[str]) -> int:
    return sum(1 for line in lines if _MOVE_RE.match(line))


def _extract_linkage_vars(lines: List[str]) -> List[str]:
    """Return 01-level variable names from LINKAGE SECTION."""
    in_linkage = False
    vars_: List[str] = []
    for line in lines:
        if _LINKAGE_RE.search(line):
            in_linkage = True
            continue
        if in_linkage:
            if _NEXT_SECTION_RE.match(line):
                break
            m = _LEVEL_01_RE.match(line)
            if m:
                vars_.append(m.group(1))
    return vars_


def _extract_called_modules(text: str) -> List[str]:
    """Return deduplicated list of CALL targets, preserving first-seen order."""
    seen: set[str] = set()
    result: List[str] = []
    for m in _CALL_RE.finditer(text):
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _extract_file_ops(lines: List[str]) -> List[dict]:
    """Return file operations from PROCEDURE DIVISION OPEN and START statements.

    op_type: R (OPEN INPUT), W (OPEN OUTPUT/I-O/EXTEND), BR (START).
    Deduplicated on (name, op_type); first occurrence wins.
    """
    proc_start = next(
        (i for i, line in enumerate(lines) if _PROC_DIV_RE.match(line)), None
    )
    if proc_start is None:
        return []

    seen: set[tuple[str, str]] = set()
    result: List[dict] = []
    for line in lines[proc_start:]:
        for pattern, op_type in _OPEN_PATTERNS:
            m = pattern.search(line)
            if m:
                name = m.group(1).rstrip('.')
                key = (name, op_type)
                if key not in seen:
                    seen.add(key)
                    result.append({'name': name, 'op_type': op_type})
    return result


def _extract_table_refs(text: str) -> List[dict]:
    """Return DB table references extracted from EXEC SQL ... END-EXEC blocks.

    op_type: R (SELECT), W (INSERT/UPDATE/DELETE).
    Deduplicated on (name, op_type); first occurrence wins.
    """
    blocks = re.split(r'EXEC\s+SQL', text, flags=re.IGNORECASE)
    seen: set[tuple[str, str]] = set()
    result: List[dict] = []

    for block in blocks[1:]:
        sql_raw, *_ = re.split(r'END-EXEC', block, maxsplit=1, flags=re.IGNORECASE)
        sql = ' '.join(sql_raw.split())  # collapse whitespace for multi-line SQL

        for pattern, op_type in _SQL_PATTERNS:
            m = pattern.search(sql)
            if m:
                name = m.group(1)
                key = (name, op_type)
                if key not in seen:
                    seen.add(key)
                    result.append({'name': name, 'op_type': op_type})
                break  # one statement type per block

    return result
