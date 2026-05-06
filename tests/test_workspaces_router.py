"""Tests for routers/workspaces.py.

Uses a real tmp-path SQLite DB seeded with ACCTPAY.cbl via extract_struct +
upsert_program — no mocking of core logic.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.ingestion.struct_extractor import extract_struct
from backend.routers.workspaces import router
from backend.storage.db import init_db, upsert_program

FIXTURE = Path(__file__).parent / "fixtures" / "ACCTPAY.cbl"


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def _db(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    conn = init_db(db_path)
    struct = extract_struct(FIXTURE)
    upsert_program(conn, struct)
    return conn


@pytest.fixture(scope="module")
def client(_db):
    app = FastAPI()
    app.include_router(router)
    app.state.db = _db
    return TestClient(app)


@pytest.fixture()
def empty_client(tmp_path):
    app = FastAPI()
    app.include_router(router)
    app.state.db = init_db(tmp_path / "empty.db")
    return TestClient(app)


# ── GET /api/workspaces ───────────────────────────────────────────────────────

def test_list_workspaces_returns_200(client):
    resp = client.get("/api/workspaces")
    assert resp.status_code == 200


def test_list_workspaces_empty_db_returns_empty_list(empty_client):
    resp = empty_client.get("/api/workspaces")
    assert resp.status_code == 200
    assert resp.json()["programs"] == []


def test_list_workspaces_contains_programs_key(client):
    assert "programs" in client.get("/api/workspaces").json()


def test_list_workspaces_has_one_program(client):
    resp = client.get("/api/workspaces")
    assert len(resp.json()["programs"]) == 1


def test_list_workspaces_program_name_is_acctpay(client):
    resp = client.get("/api/workspaces")
    assert resp.json()["programs"][0]["name"] == "ACCTPAY"


def test_list_workspaces_summary_has_required_fields(client):
    prog = client.get("/api/workspaces").json()["programs"][0]
    for field in ("id", "name", "path", "loc", "move_count", "linkage_count", "indexed_at"):
        assert field in prog, f"missing field: {field}"


def test_list_workspaces_loc_is_positive(client):
    prog = client.get("/api/workspaces").json()["programs"][0]
    assert prog["loc"] > 0


def test_list_workspaces_path_ends_with_cbl(client):
    prog = client.get("/api/workspaces").json()["programs"][0]
    assert prog["path"].endswith(".cbl")


def test_list_workspaces_indexed_at_is_string(client):
    prog = client.get("/api/workspaces").json()["programs"][0]
    assert isinstance(prog["indexed_at"], str) and len(prog["indexed_at"]) > 0


# ── GET /api/programs/{id} ────────────────────────────────────────────────────

def _program_id(client) -> int:
    return client.get("/api/workspaces").json()["programs"][0]["id"]


def test_get_program_returns_200(client):
    pid = _program_id(client)
    assert client.get(f"/api/programs/{pid}").status_code == 200


def test_get_program_unknown_id_returns_404(client):
    assert client.get("/api/programs/99999").status_code == 404


def test_get_program_404_detail_mentions_id(client):
    resp = client.get("/api/programs/99999")
    assert "99999" in resp.json()["detail"]


def test_get_program_has_detail_fields(client):
    pid = _program_id(client)
    detail = client.get(f"/api/programs/{pid}").json()
    for field in ("id", "name", "path", "loc", "move_count", "linkage_count",
                  "indexed_at", "modules", "tables_ref", "files_ref"):
        assert field in detail, f"missing field: {field}"


def test_get_program_name_matches_summary(client):
    pid = _program_id(client)
    detail = client.get(f"/api/programs/{pid}").json()
    assert detail["name"] == "ACCTPAY"


def test_get_program_modules_is_list_of_strings(client):
    pid = _program_id(client)
    modules = client.get(f"/api/programs/{pid}").json()["modules"]
    assert isinstance(modules, list)
    assert all(isinstance(m, str) for m in modules)


def test_get_program_modules_nonempty(client):
    pid = _program_id(client)
    modules = client.get(f"/api/programs/{pid}").json()["modules"]
    assert len(modules) > 0


def test_get_program_modules_contains_known_calls(client):
    pid = _program_id(client)
    modules = client.get(f"/api/programs/{pid}").json()["modules"]
    assert "CALCAMT" in modules


def test_get_program_tables_ref_nonempty(client):
    pid = _program_id(client)
    tables = client.get(f"/api/programs/{pid}").json()["tables_ref"]
    assert len(tables) > 0


def test_get_program_tables_ref_has_op_type(client):
    pid = _program_id(client)
    tables = client.get(f"/api/programs/{pid}").json()["tables_ref"]
    assert all("op_type" in t for t in tables)
    assert all(t["op_type"] in ("R", "W", "BR") for t in tables)


def test_get_program_tables_ref_contains_vendor_master(client):
    pid = _program_id(client)
    tables = client.get(f"/api/programs/{pid}").json()["tables_ref"]
    names = [t["table_name"] for t in tables]
    assert "VENDOR_MASTER" in names


def test_get_program_files_ref_nonempty(client):
    pid = _program_id(client)
    files = client.get(f"/api/programs/{pid}").json()["files_ref"]
    assert len(files) > 0


def test_get_program_files_ref_has_op_type(client):
    pid = _program_id(client)
    files = client.get(f"/api/programs/{pid}").json()["files_ref"]
    assert all("op_type" in f for f in files)
    assert all(f["op_type"] in ("R", "W", "BR") for f in files)


def test_get_program_id_matches_requested(client):
    pid = _program_id(client)
    detail = client.get(f"/api/programs/{pid}").json()
    assert detail["id"] == pid


def test_get_program_move_count_matches_workspaces(client):
    summary = client.get("/api/workspaces").json()["programs"][0]
    pid = summary["id"]
    detail = client.get(f"/api/programs/{pid}").json()
    assert detail["move_count"] == summary["move_count"]
