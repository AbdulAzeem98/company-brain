"""Tests for SQLite FTS5 search retrieval, snippets, and sanitization."""

from app.retrieval import sanitize_fts5_query


def test_sanitize_fts5_query():
    """Verify that query sanitization escapes special FTS5 operators and punctuation."""
    raw = "What is the CFO's budget for 2026? (M&A: 'Falcon Wing')"
    sanitized = sanitize_fts5_query(raw)
    assert "*" in sanitized
    assert ":" not in sanitized
    assert "(" not in sanitized
    assert ")" not in sanitized


def test_fts5_keyword_search(temp_environment):
    """Verify keyword retrieval returns expected document excerpts and BM25 scores."""
    retrieval = temp_environment["retrieval"]

    # Search with all classifications
    results = retrieval.search(
        query="laptop maintenance",
        allowed_classifications={"employee", "finance", "executive"},
        limit=5,
    )

    assert len(results) >= 1
    top_match = results[0]
    assert top_match.document_id == "NEX-TEST-001"
    assert "laptop" in top_match.excerpt.lower()
    assert top_match.score > 0


def test_retrieval_empty_on_no_match(temp_environment):
    """Verify search returns empty list when query terms do not match indexed content."""
    retrieval = temp_environment["retrieval"]

    results = retrieval.search(
        query="cryptocurrency bitcoin blockchain nonesuch",
        allowed_classifications={"employee", "finance", "executive"},
        limit=5,
    )
    assert len(results) == 0


def test_retrieval_classification_filtering(temp_environment):
    """Verify that retrieval strictly isolates documents based on allowed classifications."""
    retrieval = temp_environment["retrieval"]

    # Search term 'treasury' exists in NEX-TEST-002 (classification: finance)
    # When employee searches (clearance: employee only):
    employee_results = retrieval.search(
        query="treasury bills reserves",
        allowed_classifications={"employee"},
        limit=5,
    )
    assert len(employee_results) == 0

    # When finance searches (clearance: employee, finance):
    finance_results = retrieval.search(
        query="treasury bills reserves",
        allowed_classifications={"employee", "finance"},
        limit=5,
    )
    assert len(finance_results) >= 1
    assert finance_results[0].document_id == "NEX-TEST-002"
