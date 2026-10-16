"""SQLite database management with FTS5 full-text search initialization."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from app.config import get_settings


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- Core metadata and full text storage for company documents
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    author TEXT NOT NULL,
    last_updated TEXT NOT NULL,
    version TEXT NOT NULL,
    access_classification TEXT NOT NULL,
    file_path TEXT UNIQUE NOT NULL,
    file_hash TEXT NOT NULL,
    raw_content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Chunked content for modular retrieval & fine-grained context windows
CREATE TABLE IF NOT EXISTS document_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    heading TEXT,
    content TEXT NOT NULL
);

-- Full-Text Search (FTS5) Virtual Table for keyword-based retrieval
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    chunk_id UNINDEXED,
    document_id UNINDEXED,
    title,
    category,
    heading,
    content,
    tokenize='porter unicode61'
);

-- Sync audit log for incremental synchronization operations
CREATE TABLE IF NOT EXISTS sync_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    status TEXT NOT NULL,
    added INTEGER DEFAULT 0,
    modified INTEGER DEFAULT 0,
    deleted INTEGER DEFAULT 0,
    unchanged INTEGER DEFAULT 0,
    total_documents INTEGER DEFAULT 0,
    errors TEXT
);

CREATE INDEX IF NOT EXISTS idx_docs_classification ON documents(access_classification);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON document_chunks(document_id);
"""


def init_db(db_path: Path | None = None) -> None:
    """Initialize the SQLite database with required tables and FTS5 indexes."""
    if db_path is None:
        db_path = get_settings().DATABASE_PATH

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def get_db_connection(db_path: Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager yielding a SQLite connection configured with Row factory."""
    if db_path is None:
        db_path = get_settings().DATABASE_PATH

    conn = sqlite3.connect(str(db_path), timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
    finally:
        conn.close()
