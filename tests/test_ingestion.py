"""Tests for document ingestion, parsing, hashing, and incremental synchronization."""

from pathlib import Path
from app.database import get_db_connection


def test_initial_sync(temp_environment):
    """Verify that initial sync loads documents, populates chunks and FTS indexes."""
    db_file = temp_environment["db_file"]
    with get_db_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM documents")
        assert cursor.fetchone()["count"] == 3

        cursor.execute("SELECT COUNT(*) as count FROM document_chunks")
        assert cursor.fetchone()["count"] >= 3

        cursor.execute("SELECT COUNT(*) as count FROM documents_fts")
        assert cursor.fetchone()["count"] >= 3


def test_incremental_sync_unchanged(temp_environment):
    """Verify that unchanged files are detected and skipped without duplicating records."""
    ingestion = temp_environment["ingestion"]
    db_file = temp_environment["db_file"]

    # Second sync without touching files
    result = ingestion.sync()
    assert result.status == "success"
    assert result.added == 0
    assert result.modified == 0
    assert result.deleted == 0
    assert result.unchanged == 3

    # Count in DB should remain unchanged
    with get_db_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM documents")
        assert cursor.fetchone()["count"] == 3


def test_incremental_sync_add_new_file(temp_environment):
    """Verify that adding a new document is detected and indexed incrementally."""
    docs_dir = temp_environment["docs_dir"]
    ingestion = temp_environment["ingestion"]
    db_file = temp_environment["db_file"]

    new_doc_content = """---
id: NEX-TEST-004
title: Emergency Disaster Procedures
category: Security
author: Tariq Mansoor
last_updated: 2026-03-01T00:00:00Z
version: 1.0
access_classification: employee
---

# Disaster Recovery
In case of power outage, secondary diesel generators will engage within 8 seconds.
"""
    (docs_dir / "04_disaster.md").write_text(new_doc_content, encoding="utf-8")

    result = ingestion.sync()
    assert result.status == "success"
    assert result.added == 1
    assert result.unchanged == 3
    assert result.total_documents == 4

    with get_db_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title FROM documents WHERE id = 'NEX-TEST-004'")
        row = cursor.fetchone()
        assert row is not None
        assert row["title"] == "Emergency Disaster Procedures"


def test_incremental_sync_modified_file(temp_environment):
    """Verify that modifying a file updates the database and refreshes chunks."""
    docs_dir = temp_environment["docs_dir"]
    ingestion = temp_environment["ingestion"]
    db_file = temp_environment["db_file"]

    # Modify handbook file
    handbook_file = docs_dir / "01_handbook.md"
    updated_content = """---
id: NEX-TEST-001
title: General Employee Handbook (Updated 2026)
category: Operations
author: Test Author
last_updated: 2026-03-01T00:00:00Z
version: 2.0
access_classification: employee
---

# General Employee Handbook (Updated 2026)

## Standard Office Hours
All employees now enjoy core flexible hours between 10am and 3pm.

## Brand New Equipment Benefit
Every team member receives a noise-canceling headset annually.
"""
    handbook_file.write_text(updated_content, encoding="utf-8")

    result = ingestion.sync()
    assert result.status == "success"
    assert result.modified == 1
    assert result.added == 0
    assert result.unchanged == 2

    with get_db_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title, version FROM documents WHERE id = 'NEX-TEST-001'")
        row = cursor.fetchone()
        assert row["title"] == "General Employee Handbook (Updated 2026)"
        assert row["version"] == "2.0"

        # Check FTS index for new term
        cursor.execute("SELECT * FROM documents_fts WHERE documents_fts MATCH 'headset'")
        assert cursor.fetchone() is not None


def test_incremental_sync_deleted_file(temp_environment):
    """Verify that deleting a markdown file removes it from documents and FTS index."""
    docs_dir = temp_environment["docs_dir"]
    ingestion = temp_environment["ingestion"]
    db_file = temp_environment["db_file"]

    # Delete board document
    board_file = docs_dir / "03_board.md"
    board_file.unlink()

    result = ingestion.sync()
    assert result.status == "success"
    assert result.deleted == 1
    assert result.total_documents == 2

    with get_db_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM documents WHERE id = 'NEX-TEST-003'")
        assert cursor.fetchone()["count"] == 0

        cursor.execute("SELECT COUNT(*) as count FROM document_chunks WHERE document_id = 'NEX-TEST-003'")
        assert cursor.fetchone()["count"] == 0

        cursor.execute("SELECT * FROM documents_fts WHERE documents_fts MATCH 'Series'")
        assert cursor.fetchone() is None


def test_corrupted_frontmatter_handling(temp_environment):
    """Verify that invalid markdown frontmatter records an error without halting sync."""
    docs_dir = temp_environment["docs_dir"]
    ingestion = temp_environment["ingestion"]

    corrupted_file = docs_dir / "bad_doc.md"
    corrupted_file.write_text(
        "---\nnot_yaml: [missing bracket\n---\nBroken file content",
        encoding="utf-8",
    )

    result = ingestion.sync()
    assert result.status == "partial_failure"
    assert len(result.errors) > 0
    assert any("bad_doc.md" in err for err in result.errors)
