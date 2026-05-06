from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


class ProgramSummary(BaseModel):
    id: int
    name: str
    path: str
    loc: int
    move_count: int
    linkage_count: int
    indexed_at: str


class TableRef(BaseModel):
    table_name: str
    op_type: str


class FileRef(BaseModel):
    file_name: str
    op_type: str


class ProgramDetail(ProgramSummary):
    modules: List[str]
    tables_ref: List[TableRef]
    files_ref: List[FileRef]


class WorkspacesResponse(BaseModel):
    programs: List[ProgramSummary]


@router.get("/api/workspaces", response_model=WorkspacesResponse)
async def list_workspaces(request: Request) -> WorkspacesResponse:
    """Return a summary of every indexed program ordered by name."""
    conn = request.app.state.db
    rows = conn.execute(
        "SELECT id, name, path, loc, move_count, linkage_count, indexed_at "
        "FROM programs ORDER BY name"
    ).fetchall()
    programs = [
        ProgramSummary(
            id=r[0], name=r[1], path=r[2], loc=r[3],
            move_count=r[4], linkage_count=r[5], indexed_at=r[6],
        )
        for r in rows
    ]
    return WorkspacesResponse(programs=programs)


@router.get("/api/programs/{program_id}", response_model=ProgramDetail)
async def get_program(program_id: int, request: Request) -> ProgramDetail:
    """Return full detail for a single program including related rows."""
    conn = request.app.state.db
    row = conn.execute(
        "SELECT id, name, path, loc, move_count, linkage_count, indexed_at "
        "FROM programs WHERE id = ?",
        (program_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Program {program_id} not found")

    modules = [
        r[0]
        for r in conn.execute(
            "SELECT called_name FROM modules WHERE program_id = ? ORDER BY called_name",
            (program_id,),
        ).fetchall()
    ]
    tables_ref = [
        TableRef(table_name=r[0], op_type=r[1])
        for r in conn.execute(
            "SELECT table_name, op_type FROM tables_ref WHERE program_id = ? ORDER BY table_name",
            (program_id,),
        ).fetchall()
    ]
    files_ref = [
        FileRef(file_name=r[0], op_type=r[1])
        for r in conn.execute(
            "SELECT file_name, op_type FROM files_ref WHERE program_id = ? ORDER BY file_name",
            (program_id,),
        ).fetchall()
    ]

    return ProgramDetail(
        id=row[0], name=row[1], path=row[2], loc=row[3],
        move_count=row[4], linkage_count=row[5], indexed_at=row[6],
        modules=modules,
        tables_ref=tables_ref,
        files_ref=files_ref,
    )
