from pathlib import Path

import pytest

from backend.ingestion.metric_extractor import extract_metrics
from backend.ingestion.struct_extractor import ProgramStruct, extract_struct

FIXTURE = Path(__file__).parent / "fixtures" / "ACCTPAY.cbl"


@pytest.fixture(scope="module")
def struct() -> ProgramStruct:
    return extract_struct(FIXTURE)


@pytest.fixture(scope="module")
def metrics():
    return extract_metrics(FIXTURE)


def test_returns_program_struct(struct):
    assert isinstance(struct, ProgramStruct)


def test_program_id_extracted(struct):
    assert struct.program_id == "ACCTPAY"


def test_path_is_absolute_string(struct):
    p = Path(struct.path)
    assert p.is_absolute()
    assert p == FIXTURE.resolve()


def test_loc_matches_metric_extractor(struct, metrics):
    assert struct.loc == metrics.loc


def test_move_count_matches_metric_extractor(struct, metrics):
    assert struct.move_count == metrics.move_count


def test_linkage_count_is_len_of_linkage_vars(struct, metrics):
    assert struct.linkage_count == len(metrics.linkage_vars)
    assert struct.linkage_count == 2


def test_called_modules_match_metric_extractor(struct, metrics):
    assert struct.called_modules == metrics.called_modules
    assert struct.called_modules == ["DATEVAL", "DBCONN", "CALCAMT", "ERRHANDL"]


def test_file_ops_match_metric_extractor(struct, metrics):
    assert struct.file_ops == metrics.file_ops


def test_table_refs_match_metric_extractor(struct, metrics):
    assert struct.table_refs == metrics.table_refs


def test_fallback_program_id_uses_filename_stem(tmp_path):
    no_id = tmp_path / "MYPROG.cbl"
    no_id.write_text("       PROCEDURE DIVISION.\n           STOP RUN.\n")
    s = extract_struct(no_id)
    assert s.program_id == "MYPROG"


def test_program_id_uppercased(tmp_path):
    f = tmp_path / "lower.cbl"
    f.write_text("       IDENTIFICATION DIVISION.\n       PROGRAM-ID. myprogram.\n")
    assert extract_struct(f).program_id == "MYPROGRAM"
