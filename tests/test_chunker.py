from pathlib import Path

import pytest

from backend.ingestion.chunker import Chunk, chunk

FIXTURE = Path(__file__).parent / "fixtures" / "ACCTPAY.cbl"
TOTAL_LINES = sum(1 for _ in FIXTURE.read_text().splitlines())


def _make_cobol(tmp_path: Path, procedure_lines: int, extra_divisions: bool = True) -> Path:
    """Write a minimal COBOL file with a configurable-length PROCEDURE DIVISION."""
    body = [
        "      * minimal test fixture",
        "       IDENTIFICATION DIVISION.",
        "       PROGRAM-ID. TEST.",
        "",
    ]
    if extra_divisions:
        body += [
            "       ENVIRONMENT DIVISION.",
            "       CONFIGURATION SECTION.",
            "",
            "       DATA DIVISION.",
            "       WORKING-STORAGE SECTION.",
            "       01 WS-X PIC 9.",
            "",
        ]
    body += ["       PROCEDURE DIVISION."]
    body += [f"           MOVE {i} TO WS-X." for i in range(procedure_lines)]
    body += ["           STOP RUN."]
    p = tmp_path / "TEST.cbl"
    p.write_text("\n".join(body))
    return p


# ── ACCTPAY integration ──────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def acctpay_chunks():
    return chunk(FIXTURE)


def test_returns_chunk_instances(acctpay_chunks):
    assert all(isinstance(c, Chunk) for c in acctpay_chunks)


def test_acctpay_has_all_four_divisions(acctpay_chunks):
    divisions = {c.division for c in acctpay_chunks}
    assert divisions == {"IDENTIFICATION", "ENVIRONMENT", "DATA", "PROCEDURE"}


def test_line_ranges_are_1based(acctpay_chunks):
    assert all(c.start_line >= 1 for c in acctpay_chunks)


def test_line_ranges_are_valid(acctpay_chunks):
    assert all(c.start_line <= c.end_line for c in acctpay_chunks)


def test_line_ranges_within_file(acctpay_chunks):
    assert all(c.end_line <= TOTAL_LINES for c in acctpay_chunks)


def test_all_lines_covered(acctpay_chunks):
    """Every line in the file appears in at least one chunk."""
    covered: set[int] = set()
    for c in acctpay_chunks:
        covered.update(range(c.start_line, c.end_line + 1))
    assert covered == set(range(1, TOTAL_LINES + 1))


def test_chunk_text_is_non_empty(acctpay_chunks):
    assert all(c.text.strip() for c in acctpay_chunks)


def test_chunks_do_not_cross_division_boundary(acctpay_chunks):
    """Each chunk belongs to exactly one division (no mixed-division text)."""
    by_div: dict[str, list[Chunk]] = {}
    for c in acctpay_chunks:
        by_div.setdefault(c.division, []).append(c)
    # Ranges within a division must not overlap with another division's ranges
    div_ranges: dict[str, tuple[int, int]] = {
        div: (min(c.start_line for c in cs), max(c.end_line for c in cs))
        for div, cs in by_div.items()
    }
    divs = list(div_ranges.values())
    for i in range(len(divs)):
        for j in range(i + 1, len(divs)):
            lo1, hi1 = divs[i]
            lo2, hi2 = divs[j]
            # Ranges must not overlap
            assert hi1 < lo2 or hi2 < lo1


# ── Sliding window unit tests ─────────────────────────────────────────────────

def test_overlap_produces_shared_lines(tmp_path):
    p = _make_cobol(tmp_path, procedure_lines=30)
    chunks = chunk(p, chunk_size=10, overlap=3)
    proc = [c for c in chunks if c.division == "PROCEDURE"]
    assert len(proc) >= 2
    lines0 = proc[0].text.splitlines()
    lines1 = proc[1].text.splitlines()
    assert lines0[-3:] == lines1[:3]


def test_file_smaller_than_chunk_size_gives_one_chunk_per_division(tmp_path):
    p = _make_cobol(tmp_path, procedure_lines=5)
    chunks = chunk(p, chunk_size=100, overlap=10)
    proc = [c for c in chunks if c.division == "PROCEDURE"]
    assert len(proc) == 1


def test_zero_overlap_non_overlapping_windows(tmp_path):
    p = _make_cobol(tmp_path, procedure_lines=20)
    chunks = chunk(p, chunk_size=10, overlap=0)
    proc = [c for c in chunks if c.division == "PROCEDURE"]
    # With chunk_size=10 overlap=0, windows are fully disjoint
    for i in range(len(proc) - 1):
        assert proc[i].end_line < proc[i + 1].start_line


def test_no_divisions_in_file(tmp_path):
    p = tmp_path / "naked.cbl"
    p.write_text("* old-style file\n" * 5)
    chunks = chunk(p, chunk_size=3, overlap=1)
    assert all(c.division == "UNKNOWN" for c in chunks)


def test_empty_file(tmp_path):
    p = tmp_path / "empty.cbl"
    p.write_text("")
    assert chunk(p) == []


def test_chunk_size_one_no_infinite_loop(tmp_path):
    p = _make_cobol(tmp_path, procedure_lines=5)
    chunks = chunk(p, chunk_size=1, overlap=0)
    assert len(chunks) > 0
    assert all(c.start_line == c.end_line for c in chunks)
