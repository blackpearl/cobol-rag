import sqlite3
from pathlib import Path

import pytest

from backend.ingestion.struct_extractor import ProgramStruct, extract_struct
from backend.storage.db import get_db_path, init_db, upsert_program

FIXTURE = Path(__file__).parent / "fixtures" / "ACCTPAY.cbl"


@pytest.fixture()
def db(tmp_path):
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def acctpay_struct():
    return extract_struct(FIXTURE)


# ── init_db ──────────────────────────────────────────────────────────────────

def test_init_db_creates_all_tables(db):
    tables = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"programs", "modules", "tables_ref", "files_ref"} <= tables


def test_init_db_enables_foreign_keys(db):
    result = db.execute("PRAGMA foreign_keys").fetchone()[0]
    assert result == 1


def test_init_db_wal_mode(db):
    mode = db.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"


# ── upsert_program ────────────────────────────────────────────────────────────

def test_upsert_returns_integer(db, acctpay_struct):
    pid = upsert_program(db, acctpay_struct)
    assert isinstance(pid, int) and pid > 0


def test_upsert_programs_row(db, acctpay_struct):
    upsert_program(db, acctpay_struct)
    row = db.execute("SELECT name, loc, move_count, linkage_count FROM programs").fetchone()
    assert row[0] == acctpay_struct.program_id
    assert row[1] == acctpay_struct.loc
    assert row[2] == acctpay_struct.move_count
    assert row[3] == acctpay_struct.linkage_count


def test_upsert_modules_rows(db, acctpay_struct):
    pid = upsert_program(db, acctpay_struct)
    rows = db.execute(
        "SELECT called_name FROM modules WHERE program_id = ? ORDER BY id", (pid,)
    ).fetchall()
    assert [r[0] for r in rows] == acctpay_struct.called_modules


def test_upsert_tables_ref_rows(db, acctpay_struct):
    pid = upsert_program(db, acctpay_struct)
    rows = db.execute(
        "SELECT table_name, op_type FROM tables_ref WHERE program_id = ? ORDER BY id", (pid,)
    ).fetchall()
    assert [{"name": r[0], "op_type": r[1]} for r in rows] == acctpay_struct.table_refs


def test_upsert_files_ref_rows(db, acctpay_struct):
    pid = upsert_program(db, acctpay_struct)
    rows = db.execute(
        "SELECT file_name, op_type FROM files_ref WHERE program_id = ? ORDER BY id", (pid,)
    ).fetchall()
    assert [{"name": r[0], "op_type": r[1]} for r in rows] == acctpay_struct.file_ops


def test_upsert_is_idempotent(db, acctpay_struct):
    """Calling upsert twice must not create duplicate rows."""
    pid1 = upsert_program(db, acctpay_struct)
    pid2 = upsert_program(db, acctpay_struct)
    assert pid1 == pid2
    assert db.execute("SELECT COUNT(*) FROM programs").fetchone()[0] == 1
    assert db.execute(
        "SELECT COUNT(*) FROM modules WHERE program_id = ?", (pid1,)
    ).fetchone()[0] == len(acctpay_struct.called_modules)


def test_upsert_replaces_stale_data(db, acctpay_struct):
    """Re-indexing a program replaces, not appends, related rows."""
    pid = upsert_program(db, acctpay_struct)
    modified = ProgramStruct(
        program_id=acctpay_struct.program_id,
        path=acctpay_struct.path,
        loc=acctpay_struct.loc,
        move_count=acctpay_struct.move_count,
        linkage_count=acctpay_struct.linkage_count,
        called_modules=["NEWMOD"],
        file_ops=[],
        table_refs=[],
    )
    upsert_program(db, modified)
    rows = db.execute(
        "SELECT called_name FROM modules WHERE program_id = ?", (pid,)
    ).fetchall()
    assert rows == [("NEWMOD",)]


def test_upsert_empty_lists(db):
    """Programs with no calls/ops/refs must insert without error."""
    s = ProgramStruct(
        program_id="BARE",
        path="/tmp/BARE.cbl",
        loc=10,
        move_count=1,
        linkage_count=0,
        called_modules=[],
        file_ops=[],
        table_refs=[],
    )
    pid = upsert_program(db, s)
    assert isinstance(pid, int)
    assert db.execute(
        "SELECT COUNT(*) FROM modules WHERE program_id = ?", (pid,)
    ).fetchone()[0] == 0


# ── get_db_path ───────────────────────────────────────────────────────────────

def test_get_db_path_reads_config(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("db_path: data/test.db\n")
    assert get_db_path(cfg) == Path("data/test.db")
