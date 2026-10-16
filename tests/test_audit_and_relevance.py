
"""Regression and quality audit tests for Company Brain.

Covers:
1. High-precision retrieval and source deduplication.
2. Server-side RBAC enforcement for confidential data.
3. Privilege escalation prevention.
4. Consistent authorization across endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def real_client():
    """TestClient using the live database and knowledge service."""
    return TestClient(app)


# Use authenticated development tokens instead of trusting X-User-Role alone.
TOKENS = {
    "employee": "dev-tok-employee-01",
    "manager": "dev-tok-manager-02",
    "hr": "dev-tok-hr-03",
    "finance": "dev-tok-finance-04",
    "executive": "dev-tok-executive-05",
    "admin": "dev-tok-admin-06",
}


def auth_headers(role):
    return {"Authorization": f"Bearer {TOKENS[role]}"}


def test_home_office_stipend_retrieval_and_deduplication(real_client):
    resp = real_client.post(
        "/ask",
        json={
            "question": "What is the home office setup stipend and internet allowance?",
            "max_sources": 4,
        },
        headers=auth_headers("employee"),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["confidence"] == "grounded"
    source_ids = [s["document_id"] for s in data["sources"]]
    assert "NEX-HR-002" in source_ids
    assert len(source_ids) == len(set(source_ids))
    assert "1,500" in data["answer"] or "stipend" in data["answer"].lower()


def test_sla_response_times_precision(real_client):
    resp = real_client.post(
        "/ask",
        json={
            "question": (
                "What are our customer support SLA response times "
                "for Sev-1 and Sev-2 incidents?"
            ),
            "max_sources": 4,
        },
        headers=auth_headers("employee"),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["confidence"] == "grounded"
    source_ids = [s["document_id"] for s in data["sources"]]
    assert "NEX-SUP-001" in source_ids
    assert "NEX-SEC-001" not in source_ids


def test_project_titan_status_role_filtering(real_client):
    question = "What is the current status of Project Titan?"

    emp_resp = real_client.post(
        "/ask",
        json={"question": question, "max_sources": 4},
        headers=auth_headers("employee"),
    )
    assert emp_resp.status_code == 200
    emp_data = emp_resp.json()
    assert emp_data["confidence"] == "insufficient_evidence"
    assert len(emp_data["sources"]) == 0
    assert "insufficient" in emp_data["answer"].lower()

    mgr_resp = real_client.post(
        "/ask",
        json={"question": question, "max_sources": 4},
        headers=auth_headers("manager"),
    )
    assert mgr_resp.status_code == 200
    mgr_data = mgr_resp.json()
    assert mgr_data["confidence"] == "grounded"
    assert "NEX-ENG-002" in [
        s["document_id"] for s in mgr_data["sources"]
    ]


def test_employee_cannot_access_ma_strategy(real_client):
    headers = auth_headers("employee")

    search_resp = real_client.post(
        "/search",
        json={
            "query": "M&A Target Strategy acquisition ApexTracing Falcon Wing",
            "limit": 5,
        },
        headers=headers,
    )
    assert search_resp.status_code == 200
    assert search_resp.json()["total_results"] == 0

    ask_resp = real_client.post(
        "/ask",
        json={
            "question": "What is our M&A Target Strategy and acquisition target?",
            "max_sources": 4,
        },
        headers=headers,
    )
    assert ask_resp.status_code == 200
    ask_data = ask_resp.json()
    assert ask_data["confidence"] == "insufficient_evidence"
    assert len(ask_data["sources"]) == 0
    assert "Falcon Wing" not in ask_data["answer"]
    assert "ApexTracing" not in ask_data["answer"]

    doc_resp = real_client.get(
        "/documents/NEX-EXE-001",
        headers=headers,
    )
    assert doc_resp.status_code == 403


def test_executive_can_access_ma_strategy(real_client):
    resp = real_client.post(
        "/ask",
        json={
            "question": "What is our M&A Target Strategy and acquisition target?",
            "max_sources": 4,
        },
        headers=auth_headers("executive"),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["confidence"] == "grounded"
    source_ids = [s["document_id"] for s in data["sources"]]
    assert "NEX-EXE-001" in source_ids
    assert (
        "Falcon Wing" in data["answer"]
        or "ApexTracing" in data["answer"]
    )


def test_employee_cannot_access_hr_or_finance_confidential(real_client):
    headers = auth_headers("employee")

    hr_search = real_client.post(
        "/search",
        json={
            "query": "Radford compensation equity bands L5 staff engineer salary",
            "limit": 5,
        },
        headers=headers,
    )
    assert hr_search.status_code == 200
    assert hr_search.json()["total_results"] == 0

    hr_doc = real_client.get(
        "/documents/NEX-HR-004",
        headers=headers,
    )
    assert hr_doc.status_code == 403

    fin_doc = real_client.get(
        "/documents/NEX-FIN-001",
        headers=headers,
    )
    assert fin_doc.status_code == 403


def test_privilege_escalation_prevention(real_client):
    # A role claim cannot override an authenticated employee token.
    resp = real_client.get(
        "/documents/NEX-EXE-001",
        headers={
            **auth_headers("employee"),
            "X-User-Role": "executive",
        },
    )
    assert resp.status_code == 403
    assert "Privilege escalation attempt" in resp.json()["detail"]

    # A valid executive token can access executive-classified documents.
    exec_resp = real_client.get(
        "/documents/NEX-EXE-001",
        headers=auth_headers("executive"),
    )
    assert exec_resp.status_code == 200
    assert exec_resp.json()["id"] == "NEX-EXE-001"


def test_role_header_alone_cannot_grant_elevated_access(real_client):
    # Forging an admin role header must not expose executive documents.
    resp = real_client.get(
        "/documents",
        headers={"X-User-Role": "admin"},
    )
    assert resp.status_code == 200
    visible_docs = {doc["id"] for doc in resp.json()}
    assert "NEX-EXE-001" not in visible_docs
    assert "NEX-FIN-001" not in visible_docs
    assert "NEX-HR-004" not in visible_docs


def test_user_id_header_alone_cannot_grant_elevated_access(real_client):
    # An identity header without authenticated credentials is untrusted.
    resp = real_client.get(
        "/documents",
        headers={"X-User-Id": "adm_tariq"},
    )
    assert resp.status_code == 200
    visible_docs = {doc["id"] for doc in resp.json()}
    assert "NEX-EXE-001" not in visible_docs


def test_unsupported_question_insufficient_evidence(real_client):
    resp = real_client.post(
        "/ask",
        json={
            "question": "Where is the subterranean Martian mining base located?",
            "max_sources": 4,
        },
        headers=auth_headers("employee"),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["confidence"] == "insufficient_evidence"
    assert len(data["sources"]) == 0
    assert "insufficient evidence" in data["answer"].lower()


def test_search_and_document_browser_consistent_authorization(real_client):
    """Verify document access follows the authenticated role's clearance."""
    confidential_documents = {
        "NEX-EXE-001": {"executive", "admin"},
        "NEX-FIN-001": {"finance", "executive", "admin"},
        "NEX-HR-004": {"hr", "executive", "admin"},
    }

    for role in TOKENS:
        headers = auth_headers(role)
        doc_resp = real_client.get("/documents", headers=headers)
        assert doc_resp.status_code == 200
        visible_docs = {doc["id"] for doc in doc_resp.json()}

        for document_id, authorized_roles in confidential_documents.items():
            if role in authorized_roles:
                assert document_id in visible_docs, (
                    f"{role} should see {document_id}"
                )
            else:
                assert document_id not in visible_docs, (
                    f"{role} must not see {document_id}"
                )
