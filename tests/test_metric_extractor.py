import re
from pathlib import Path

import pytest

from backend.ingestion.metric_extractor import ExtractedMetrics, extract_metrics

FIXTURE = Path(__file__).parent / "fixtures" / "ACCTPAY.cbl"


@pytest.fixture(scope="module")
def metrics() -> ExtractedMetrics:
    return extract_metrics(FIXTURE)


def test_loc_counts_nonblank_lines(metrics):
    expected = sum(1 for line in FIXTURE.read_text().splitlines() if line.strip())
    assert metrics.loc == expected


def test_move_count(metrics):
    assert metrics.move_count == 9


def test_linkage_vars(metrics):
    assert metrics.linkage_vars == ["LS-PROCESS-PARAMS", "LS-RETURN-CODE"]


def test_called_modules(metrics):
    assert metrics.called_modules == ["DATEVAL", "DBCONN", "CALCAMT", "ERRHANDL"]


def test_file_ops(metrics):
    assert metrics.file_ops == [
        {"name": "VENDOR-FILE",  "op_type": "R"},
        {"name": "INVOICE-FILE", "op_type": "R"},
        {"name": "PAYMENT-FILE", "op_type": "W"},
        {"name": "REPORT-FILE",  "op_type": "W"},
        {"name": "VENDOR-FILE",  "op_type": "BR"},
    ]


def test_file_ops_no_duplicates(metrics):
    seen: set[tuple[str, str]] = set()
    for op in metrics.file_ops:
        key = (op["name"], op["op_type"])
        assert key not in seen, f"Duplicate file op: {key}"
        seen.add(key)


def test_table_refs(metrics):
    assert metrics.table_refs == [
        {"name": "VENDOR_MASTER",  "op_type": "R"},
        {"name": "INVOICE_HDR",    "op_type": "R"},
        {"name": "PAYMENT_AUDIT",  "op_type": "W"},
        {"name": "INVOICE_HDR",    "op_type": "W"},
        {"name": "TEMP_INVOICES",  "op_type": "W"},
    ]


def test_table_refs_no_duplicates(metrics):
    seen: set[tuple[str, str]] = set()
    for ref in metrics.table_refs:
        key = (ref["name"], ref["op_type"])
        assert key not in seen, f"Duplicate table ref: {key}"
        seen.add(key)


def test_returns_extracted_metrics_type(metrics):
    assert isinstance(metrics, ExtractedMetrics)


def test_move_regex_excludes_data_division():
    """Regression: MOVE-prefixed variable names in DATA DIVISION must not be counted."""
    move_re = re.compile(r'^\s+MOVE\s', re.IGNORECASE)
    data_lines = [
        "           05 MOVE-COUNTER       PIC 9(6).",
        "       01 MOVE-PARAMS.",
    ]
    assert all(not move_re.match(line) for line in data_lines)
