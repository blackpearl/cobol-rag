from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from backend.ingestion.struct_extractor import ProgramStruct

_DDL = """
CREATE TABLE IF NOT EXISTS programs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    path          TEXT    NOT NULL UNIQUE,
    loc           INTEGER NOT NULL,
    move_count    INTEGER NOT NULL,
    linkage_count INTEGER NOT NULL,
    indexed_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS modules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id  INTEGER NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    called_name TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS tables_ref (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id  INTEGER NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    table_name  TEXT    NOT NULL,
    op_type     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS files_ref (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id  INTEGER NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    file_name   TEXT    NOT NULL,
    op_type     TEXT    NOT NULL
);
"""


def get_db_path(config_path: Optional[Path] = None) -> Path:
    """Return the SQLite database path read from config.yaml."""
    if config_path is None:
        config_path = Path(__file__).parents[2] / "config.yaml"
    with config_path.open() as fh:
        cfg = yaml.safe_load(fh)
    return Path(cfg["db_path"])


def init_db(db_path: Path) -> sqlite3.Connection:
    """Create the database file, enable WAL + foreign keys, and apply the schema."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_DDL)
    return conn


def upsert_program(conn: sqlite3.Connection, struct: ProgramStruct) -> int:
    """Insert or update a program and fully replace its related rows.

    All four tables are written atomically. Returns the programs.id.
    """
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute(
            """
            INSERT INTO programs (name, path, loc, move_count, linkage_count, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                name          = excluded.name,
                loc           = excluded.loc,
                move_count    = excluded.move_count,
                linkage_count = excluded.linkage_count,
                indexed_at    = excluded.indexed_at
            """,
            (struct.program_id, struct.path, struct.loc,
             struct.move_count, struct.linkage_count, now),
        )
        program_id: int = conn.execute(
            "SELECT id FROM programs WHERE path = ?", (struct.path,)
        ).fetchone()[0]

        for table in ("modules", "tables_ref", "files_ref"):
            conn.execute(f"DELETE FROM {table} WHERE program_id = ?", (program_id,))

        conn.executemany(
            "INSERT INTO modules (program_id, called_name) VALUES (?, ?)",
            [(program_id, name) for name in struct.called_modules],
        )
        conn.executemany(
            "INSERT INTO tables_ref (program_id, table_name, op_type) VALUES (?, ?, ?)",
            [(program_id, ref["name"], ref["op_type"]) for ref in struct.table_refs],
        )
        conn.executemany(
            "INSERT INTO files_ref (program_id, file_name, op_type) VALUES (?, ?, ?)",
            [(program_id, op["name"], op["op_type"]) for op in struct.file_ops],
        )

    return program_id
