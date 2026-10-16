"""Pytest fixtures for Company Brain test suite."""

import shutil
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.database import init_db
from app.ingestion import IngestionEngine
from app.main import app
from app.retrieval import SQLiteFTS5RetrievalEngine
from app.services.knowledge_service import KnowledgeService
from app.services.sync_service import SyncService


SAMPLE_EMPLOYEE_DOC = """---
id: NEX-TEST-001
title: General Employee Handbook
category: Operations
author: Test Author
last_updated: 2026-01-01T00:00:00Z
version: 1.0
access_classification: employee
---

# General Employee Handbook

## Standard Office Hours
All employees should adhere to standard operational hours between 9am and 5pm.

## Laptop Maintenance
Laptops are refreshed every three years by IT operations.
"""

SAMPLE_FINANCE_DOC = """---
id: NEX-TEST-002
title: Q1 Confidential Treasury & Capital Allocation Plan
category: Finance
author: Evelyn Reed
last_updated: 2026-01-01T00:00:00Z
version: 1.0
access_classification: finance
---

# Confidential Treasury Plan

## Liquid Reserves
Nexora maintains $38M in FDIC-insured treasury bills yielding 4.8% annual return.

## M&A Reserve Allocation
$15M is earmarked for strategic technology acquisition under project Falcon Wing.
"""

SAMPLE_EXECUTIVE_DOC = """---
id: NEX-TEST-003
title: Confidential Board Minutes & Valuation Strategy
category: Executive
author: Dr. Aris Thorne
last_updated: 2026-01-01T00:00:00Z
version: 1.0
access_classification: executive
---

# Board Minutes

## Confidential Valuation Strategy
Nexora target valuation for Series C is $450M based on 10x ARR multiple.
"""


@pytest.fixture
def temp_environment():
    """Create an isolated temporary environment with a fresh SQLite DB and markdown directory."""
    temp_dir = Path(tempfile.mkdtemp(prefix="company_brain_test_"))
    docs_dir = temp_dir / "docs"
    docs_dir.mkdir(parents=True)
    db_file = temp_dir / "test_brain.db"

    # Initialize SQLite database
    init_db(db_file)

    # Populate sample documents
    (docs_dir / "01_handbook.md").write_text(SAMPLE_EMPLOYEE_DOC, encoding="utf-8")
    (docs_dir / "02_treasury.md").write_text(SAMPLE_FINANCE_DOC, encoding="utf-8")
    (docs_dir / "03_board.md").write_text(SAMPLE_EXECUTIVE_DOC, encoding="utf-8")

    # Ingestion engine and sync
    ingestion = IngestionEngine(knowledge_dir=docs_dir, db_path=db_file)
    sync_result = ingestion.sync()
    assert sync_result.status == "success"

    retrieval = SQLiteFTS5RetrievalEngine(db_path=db_file)
    knowledge_service = KnowledgeService(retrieval_engine=retrieval)
    sync_service = SyncService(ingestion_engine=ingestion)

    yield {
        "temp_dir": temp_dir,
        "docs_dir": docs_dir,
        "db_file": db_file,
        "ingestion": ingestion,
        "retrieval": retrieval,
        "knowledge_service": knowledge_service,
        "sync_service": sync_service,
    }

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def client(temp_environment, monkeypatch):
    """FastAPI TestClient with isolated test database and knowledge service."""
    # Patch dependencies in app to use test environment
    monkeypatch.setattr("app.main.get_knowledge_service", lambda: temp_environment["knowledge_service"])
    monkeypatch.setattr("app.main.get_sync_service", lambda: temp_environment["sync_service"])
    return TestClient(app)
