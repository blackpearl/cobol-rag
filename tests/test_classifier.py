import pytest

from backend.retrieval.classifier import classify

# ── sql ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "How many MOVE statements does ACCTPAY have?",
    "What is the LOC for ACCTPAY?",
    "List all programs that call DATEVAL",
    "Which programs read VENDOR-FILE?",
    "Which tables does ACCTPAY update?",
    "Which modules are called by PAYROLL?",
    "What files does ACCTPAY write?",
    "What tables does BILSYS access?",
    "How many programs are in the workspace?",
    "What is the total LOC across all programs?",
    "Give me a count of CALL statements in ACCTPAY",
    "Number of linkage variables in ACCTPAY",
    "What programs call ERRHANDL?",
    "ACCTPAY move count",
])
def test_sql_queries(query):
    assert classify(query) == "sql"


# ── semantic ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "Explain the vendor processing logic in ACCTPAY",
    "What does the payment calculation do?",
    "How does ACCTPAY process invoices?",
    "Describe the error handling flow",
    "Show me how payments are written",
    "Walk me through the main logic of ACCTPAY",
    "I want to understand the linkage section",
    "What is the purpose of the CALCAMT call?",
    "Describe the browse logic for vendors",
    "How does the AT END condition work here?",
    "Walk through the database update flow",
    "What is the overall purpose of this program?",
])
def test_semantic_queries(query):
    assert classify(query) == "semantic"


# ── hybrid ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    "Which programs call DATEVAL and explain what they do with the result?",
    "List all programs that read VENDOR-FILE and describe their flow",
    "How many tables does ACCTPAY update and explain the update logic?",
    "Which modules are called and what is the purpose of each?",
    "Count the MOVE statements and explain what they move",
])
def test_hybrid_queries(query):
    assert classify(query) == "hybrid"


# ── default / edge cases ──────────────────────────────────────────────────────

def test_empty_query_defaults_to_semantic():
    assert classify("") == "semantic"


def test_unrecognized_query_defaults_to_semantic():
    assert classify("ACCTPAY") == "semantic"


def test_case_insensitive():
    assert classify("HOW MANY MOVE STATEMENTS?") == "sql"
    assert classify("EXPLAIN THE LOGIC") == "semantic"


def test_returns_literal_string():
    result = classify("anything")
    assert isinstance(result, str)
    assert result in ("sql", "semantic", "hybrid")
