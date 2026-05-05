import pytest

from backend.generation.context_builder import build_context

QUERY = "How does ACCTPAY process vendor payments?"

_SQL_ROWS = [
    {"program": "ACCTPAY", "loc": 140, "move_count": 9, "linkage_count": 2},
]

_SEM_CHUNKS = [
    {
        "text": "           CALL 'CALCAMT' USING WS-INV-AMT WS-DISCOUNT WS-NET-AMT\n"
                "           MOVE WS-NET-AMT TO WS-PMT-AMT",
        "metadata": {
            "program_id": 1,
            "file_path": "/src/ACCTPAY.cbl",
            "division": "PROCEDURE",
            "start_line": 100,
            "end_line": 115,
        },
        "distance": 0.12,
    },
    {
        "text": "       EXEC SQL\n"
                "           INSERT INTO PAYMENT_AUDIT ...\n"
                "       END-EXEC",
        "metadata": {
            "program_id": 1,
            "file_path": "/src/ACCTPAY.cbl",
            "division": "PROCEDURE",
            "start_line": 116,
            "end_line": 130,
        },
        "distance": 0.25,
    },
]


# ── return type & structure ───────────────────────────────────────────────────

def test_returns_string():
    assert isinstance(build_context(QUERY), str)


def test_query_present_in_output():
    out = build_context(QUERY)
    assert QUERY in out


def test_preamble_present():
    out = build_context(QUERY)
    assert "COBOL analyst" in out


# ── sql only ──────────────────────────────────────────────────────────────────

def test_sql_section_header_present():
    out = build_context(QUERY, sql_rows=_SQL_ROWS)
    assert "Structured Data" in out


def test_sql_values_present():
    out = build_context(QUERY, sql_rows=_SQL_ROWS)
    assert "ACCTPAY" in out
    assert "140" in out


def test_empty_sql_rows_skips_section():
    out = build_context(QUERY, sql_rows=[])
    assert "Structured Data" not in out


# ── sem chunks only ───────────────────────────────────────────────────────────

def test_chunk_section_header_present():
    out = build_context(QUERY, sem_chunks=_SEM_CHUNKS)
    assert "Relevant Code" in out


def test_chunk_text_present():
    out = build_context(QUERY, sem_chunks=_SEM_CHUNKS)
    assert "CALCAMT" in out


def test_chunk_metadata_in_header():
    out = build_context(QUERY, sem_chunks=_SEM_CHUNKS)
    assert "ACCTPAY.cbl" in out
    assert "PROCEDURE" in out
    assert "100" in out


def test_chunk_separator_present():
    out = build_context(QUERY, sem_chunks=_SEM_CHUNKS)
    assert "---" in out


def test_empty_sem_chunks_skips_section():
    out = build_context(QUERY, sem_chunks=[])
    assert "Relevant Code" not in out


# ── hybrid ────────────────────────────────────────────────────────────────────

def test_hybrid_contains_both_sections():
    out = build_context(QUERY, sql_rows=_SQL_ROWS, sem_chunks=_SEM_CHUNKS)
    assert "Structured Data" in out
    assert "Relevant Code" in out


def test_sql_appears_before_chunks():
    out = build_context(QUERY, sql_rows=_SQL_ROWS, sem_chunks=_SEM_CHUNKS)
    assert out.index("Structured Data") < out.index("Relevant Code")


# ── no context ────────────────────────────────────────────────────────────────

def test_no_context_still_returns_prompt():
    out = build_context(QUERY)
    assert len(out) > 0
    assert QUERY in out


# ── max_chars budget ──────────────────────────────────────────────────────────

def test_output_respects_max_chars():
    out = build_context(QUERY, sql_rows=_SQL_ROWS, sem_chunks=_SEM_CHUNKS, max_chars=200)
    assert len(out) <= 200


def test_tiny_budget_still_includes_query():
    # Even with very tight budget the fixed preamble+question block is included
    out = build_context(QUERY, sem_chunks=_SEM_CHUNKS, max_chars=500)
    assert QUERY in out


def test_large_chunk_truncated_to_budget():
    big_chunk = [
        {
            "text": "X" * 5000,
            "metadata": {
                "program_id": 1,
                "file_path": "/src/FOO.cbl",
                "division": "DATA",
                "start_line": 1,
                "end_line": 100,
            },
            "distance": 0.1,
        }
    ]
    out = build_context(QUERY, sem_chunks=big_chunk, max_chars=800)
    assert len(out) <= 800


def test_second_chunk_omitted_when_budget_exhausted():
    big_chunk = {
        "text": "A" * 3000,
        "metadata": {
            "program_id": 1,
            "file_path": "/src/FOO.cbl",
            "division": "DATA",
            "start_line": 1,
            "end_line": 50,
        },
        "distance": 0.1,
    }
    sentinel_chunk = {
        "text": "SENTINEL_TEXT",
        "metadata": {
            "program_id": 1,
            "file_path": "/src/BAR.cbl",
            "division": "DATA",
            "start_line": 51,
            "end_line": 60,
        },
        "distance": 0.5,
    }
    out = build_context(QUERY, sem_chunks=[big_chunk, sentinel_chunk], max_chars=1000)
    assert "SENTINEL_TEXT" not in out
    assert len(out) <= 1000
