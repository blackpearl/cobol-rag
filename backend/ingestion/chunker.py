from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple


@dataclass
class Chunk:
    text: str
    division: str    # IDENTIFICATION | ENVIRONMENT | DATA | PROCEDURE | UNKNOWN
    start_line: int  # 1-based, inclusive
    end_line: int    # 1-based, inclusive


_DIV_RE = re.compile(
    r'^\s+(IDENTIFICATION|ENVIRONMENT|DATA|PROCEDURE)\s+DIVISION\b',
    re.IGNORECASE,
)


def chunk(
    file_path: Path,
    chunk_size: int = 40,
    overlap: int = 10,
) -> List[Chunk]:
    """Split a COBOL source file into division-bounded sliding-window chunks."""
    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    result: List[Chunk] = []
    for start_idx, end_idx, div_name in _split_into_divisions(lines):
        div_lines = lines[start_idx : end_idx + 1]
        for window, w_start, w_end in _windows(div_lines, start_idx, chunk_size, overlap):
            result.append(Chunk(
                text="\n".join(window),
                division=div_name,
                start_line=w_start,
                end_line=w_end,
            ))
    return result


def _split_into_divisions(lines: List[str]) -> List[Tuple[int, int, str]]:
    """
    Return (start_idx, end_idx, division_name) for each COBOL division block.
    Lines before the first IDENTIFICATION DIVISION are prepended to it.
    """
    div_positions: List[Tuple[int, str]] = [
        (i, m.group(1).upper())
        for i, line in enumerate(lines)
        if (m := _DIV_RE.match(line))
    ]
    if not div_positions:
        return [(0, max(0, len(lines) - 1), "UNKNOWN")]

    blocks: List[Tuple[int, int, str]] = []
    for j, (start, name) in enumerate(div_positions):
        actual_start = 0 if j == 0 else start
        end = div_positions[j + 1][0] - 1 if j < len(div_positions) - 1 else len(lines) - 1
        blocks.append((actual_start, end, name))
    return blocks


def _windows(
    lines: List[str],
    offset: int,
    chunk_size: int,
    overlap: int,
) -> List[Tuple[List[str], int, int]]:
    """Sliding window over lines. Returns (window_lines, start_1based, end_1based)."""
    step = max(1, chunk_size - overlap)
    result = []
    for i in range(0, len(lines), step):
        window = lines[i : i + chunk_size]
        if window:
            result.append((window, offset + i + 1, offset + i + len(window)))
    return result
