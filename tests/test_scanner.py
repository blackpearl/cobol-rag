from pathlib import Path

import pytest

from backend.ingestion.scanner import scan


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    return path


def test_finds_all_cobol_extensions(tmp_path):
    _touch(tmp_path / "prog.cbl")
    _touch(tmp_path / "mod.cob")
    _touch(tmp_path / "copy.cpy")
    assert {p.name for p in scan(tmp_path)} == {"prog.cbl", "mod.cob", "copy.cpy"}


def test_excludes_non_cobol_files(tmp_path):
    _touch(tmp_path / "prog.cbl")
    _touch(tmp_path / "readme.txt")
    _touch(tmp_path / "main.py")
    assert all(p.suffix in {".cbl", ".cob", ".cpy"} for p in scan(tmp_path))


def test_recurses_into_subdirectories(tmp_path):
    _touch(tmp_path / "top.cbl")
    _touch(tmp_path / "sub" / "nested.cob")
    _touch(tmp_path / "sub" / "deep" / "copy.cpy")
    assert len(scan(tmp_path)) == 3


def test_result_is_sorted(tmp_path):
    _touch(tmp_path / "z_last.cbl")
    _touch(tmp_path / "a_first.cbl")
    _touch(tmp_path / "m_middle.cbl")
    paths = scan(tmp_path)
    assert paths == sorted(paths)


def test_case_insensitive_extension(tmp_path):
    _touch(tmp_path / "PROG.CBL")
    _touch(tmp_path / "MOD.COB")
    _touch(tmp_path / "COPY.CPY")
    assert len(scan(tmp_path)) == 3


def test_skips_hidden_dirs(tmp_path):
    _touch(tmp_path / ".git" / "hook.cbl")
    _touch(tmp_path / ".venv" / "dummy.cbl")
    _touch(tmp_path / "real.cbl")
    assert scan(tmp_path) == [tmp_path / "real.cbl"]


def test_empty_directory_returns_empty_list(tmp_path):
    assert scan(tmp_path) == []


def test_returns_path_objects(tmp_path):
    _touch(tmp_path / "prog.cbl")
    assert all(isinstance(p, Path) for p in scan(tmp_path))
