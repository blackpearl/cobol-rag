from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

from backend.ingestion.metric_extractor import extract_metrics

_PROGRAM_ID_RE = re.compile(r'PROGRAM-ID\.\s*([\w-]+)', re.IGNORECASE)


@dataclass
class ProgramStruct:
    """Complete program profile ready for persistence across the four SQLite tables."""
    program_id: str        # programs.name
    path: str              # programs.path  (absolute)
    loc: int               # programs.loc
    move_count: int        # programs.move_count
    linkage_count: int     # programs.linkage_count
    called_modules: List[str]   # → modules table
    file_ops: List[dict]        # → files_ref table  {name, op_type}
    table_refs: List[dict]      # → tables_ref table {name, op_type}


def extract_struct(file_path: Path) -> ProgramStruct:
    """Build a complete program profile for a single COBOL source file."""
    metrics = extract_metrics(file_path)
    text = file_path.read_text(encoding="utf-8", errors="replace")
    m = _PROGRAM_ID_RE.search(text)
    program_id = m.group(1).upper() if m else file_path.stem.upper()
    return ProgramStruct(
        program_id=program_id,
        path=str(file_path.resolve()),
        loc=metrics.loc,
        move_count=metrics.move_count,
        linkage_count=len(metrics.linkage_vars),
        called_modules=metrics.called_modules,
        file_ops=metrics.file_ops,
        table_refs=metrics.table_refs,
    )
