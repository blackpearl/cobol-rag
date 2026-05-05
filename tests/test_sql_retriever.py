from pathlib import Path

import pytest

from backend.ingestion.struct_extractor import extract_struct
from backend.retrieval.sql_retriever import SqlResult, retrieve
from backend.storage.db import init_db, upsert_program

FIXTURE = Path(__file__).parent / "fixtures" / "ACCTPAY.cbl"


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    c = init_db(db_path)
    struct = extract_struct(FIXTURE)
    upsert_program(c, struct)
    return c


# ── return type ───────────────────────────────────────────────────────────────

def test_returns_sql_result(conn):
    result = retrieve(conn, "list all programs")
    assert isinstance(result, SqlResult)
    assert isinstance(result.rows, list)
    assert isinstance(result.sql, str)


# ── counting ──────────────────────────────────────────────────────────────────

def test_count_programs(conn):
    result = retrieve(conn, "How many programs are in the workspace?")
    assert result.rows[0]["count"] == 1


def test_count_programs_variant(conn):
    result = retrieve(conn, "Number of programs indexed")
    assert result.rows[0]["count"] == 1


# ── program metrics ───────────────────────────────────────────────────────────

def test_program_metrics_loc(conn):
    result = retrieve(conn, "What is the LOC for ACCTPAY?")
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row["name"] == "ACCTPAY"
    assert isinstance(row["loc"], int) and row["loc"] > 0


def test_program_metrics_move_count(conn):
    result = retrieve(conn, "How many MOVE statements does ACCTPAY have?")
    assert result.rows[0]["move_count"] == 9


def test_program_metrics_unknown_program(conn):
    result = retrieve(conn, "LOC for NOSUCHPROG")
    assert result.rows == []


# ── callers of a module ───────────────────────────────────────────────────────

def test_callers_of_module(conn):
    result = retrieve(conn, "Which programs call DATEVAL?")
    names = [r["program"] for r in result.rows]
    assert "ACCTPAY" in names


def test_callers_of_module_what_variant(conn):
    result = retrieve(conn, "What programs call ERRHANDL?")
    assert any(r["program"] == "ACCTPAY" for r in result.rows)


def test_callers_of_unknown_module(conn):
    result = retrieve(conn, "Which programs call NOMOD?")
    assert result.rows == []


# ── callees of a program ──────────────────────────────────────────────────────

def test_calls_from_program(conn):
    result = retrieve(conn, "What modules does ACCTPAY call?")
    called = [r["called_name"] for r in result.rows]
    assert set(called) == {"DATEVAL", "DBCONN", "CALCAMT", "ERRHANDL"}


def test_calls_from_program_which_variant(conn):
    result = retrieve(conn, "Which modules does ACCTPAY call?")
    assert len(result.rows) == 4


# ── file queries ──────────────────────────────────────────────────────────────

def test_files_of_program(conn):
    result = retrieve(conn, "What files does ACCTPAY read?")
    assert len(result.rows) > 0
    assert all("file_name" in r for r in result.rows)


def test_files_of_program_op_filter(conn):
    result = retrieve(conn, "What files does ACCTPAY read?")
    # op_type filter "read" → R
    assert all(r["op_type"] == "R" for r in result.rows)


def test_programs_that_read_file(conn):
    result = retrieve(conn, "Which programs read VENDOR-FILE?")
    assert any(r["program"] == "ACCTPAY" for r in result.rows)


def test_programs_that_write_file(conn):
    result = retrieve(conn, "Which programs write PAYMENT-FILE?")
    assert any(r["program"] == "ACCTPAY" for r in result.rows)


# ── table queries ─────────────────────────────────────────────────────────────

def test_tables_of_program(conn):
    result = retrieve(conn, "What tables does ACCTPAY access?")
    table_names = [r["table_name"] for r in result.rows]
    assert "VENDOR_MASTER" in table_names
    assert "INVOICE_HDR" in table_names


def test_tables_of_program_update_filter(conn):
    result = retrieve(conn, "Which tables does ACCTPAY update?")
    assert all(r["op_type"] == "W" for r in result.rows)
    table_names = [r["table_name"] for r in result.rows]
    assert "INVOICE_HDR" in table_names


def test_programs_that_access_table(conn):
    result = retrieve(conn, "Which programs access VENDOR_MASTER?")
    assert any(r["program"] == "ACCTPAY" for r in result.rows)


def test_programs_that_update_table(conn):
    result = retrieve(conn, "Which programs update INVOICE_HDR?")
    assert any(r["program"] == "ACCTPAY" for r in result.rows)


# ── listing / fallback ────────────────────────────────────────────────────────

def test_list_programs(conn):
    result = retrieve(conn, "List all programs")
    assert len(result.rows) == 1
    assert result.rows[0]["name"] == "ACCTPAY"


def test_fallback_returns_program_list(conn):
    result = retrieve(conn, "show everything")
    assert len(result.rows) >= 1
    assert "name" in result.rows[0]


# ── sql field ─────────────────────────────────────────────────────────────────

def test_sql_field_is_non_empty_string(conn):
    result = retrieve(conn, "Which programs call DATEVAL?")
    assert result.sql.strip().upper().startswith("SELECT")
