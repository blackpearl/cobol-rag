from __future__ import annotations

import re
from typing import Literal

QueryType = Literal["sql", "semantic", "hybrid"]

# Signals that suggest structured-data retrieval (counts, lists, relationships).
_SQL_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bhow\s+many\b",
        r"\bcount\b",
        r"\blist\b",
        r"\btotal\b",
        r"\bnumber\s+of\b",
        r"\bloc\b",
        r"\blines?\s+of\s+code\b",
        r"\bmove[\s_-]count\b",
        r"\bcalled\s+by\b",
        r"\bwhich\s+programs?\b",
        r"\bwhich\s+files?\b",
        r"\bwhich\s+tables?\b",
        r"\bwhich\s+modules?\b",
        r"\bwhat\s+files?\b",
        r"\bwhat\s+tables?\b",
        r"\bwhat\s+programs?\b",
        r"\bwhat\s+modules?\b",
    ]
]

# Signals that suggest full-text / semantic retrieval (explanations, logic, behaviour).
_SEMANTIC_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bexplain\b",
        r"\bwhat\s+does\b",
        r"\bhow\s+does\b",
        r"\bdescribe\b",
        r"\bshow\s+me\b",
        r"\bunderstand\b",
        r"\bpurpose\b",
        r"\blogic\b",
        r"\bflow\b",
        r"\bworks?\b",
        r"\bimplementat\w*\b",
        r"\bwalk\s+(?:me\s+)?through\b",
    ]
]


def classify(query: str) -> QueryType:
    """Route a natural-language query to sql, semantic, or hybrid retrieval.

    Scores the query against two independent signal sets. If both fire the
    result is hybrid; if only the SQL set fires it is sql; otherwise semantic
    (the safer default for open-ended questions).
    """
    sql_hits = sum(1 for p in _SQL_PATTERNS if p.search(query))
    sem_hits = sum(1 for p in _SEMANTIC_PATTERNS if p.search(query))

    if sql_hits >= 1 and sem_hits >= 1:
        return "hybrid"
    if sql_hits >= 1:
        return "sql"
    return "semantic"
