
"""Integration tests for Company Brain FastAPI endpoints."""


def auth_headers(role):
    """Return a development bearer token for the requested role."""
    tokens = {
        "employee": "dev-tok-employee-01",
        "manager": "dev-tok-manager-02",
        "hr": "dev-tok-hr-03",
        "finance": "dev-tok-finance-04",
        "executive": "dev-tok-executive-05",
        "admin": "dev-tok-admin-06",
    }
    return {"Authorization": f"Bearer {tokens[role]}"}


def test_health_endpoint(client):
    """Test GET /health returns operational metrics."""
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert "Company Brain" in data["app"]
    assert data["documents_indexed"] == 3


def test_list_documents_rbac_filtering(client):
    """Test document listing filters according to the authenticated role."""
    resp_emp = client.get(
        "/documents",
        headers=auth_headers("employee"),
    )
    assert resp_emp.status_code == 200
    docs_emp = resp_emp.json()
    assert len(docs_emp) == 1
    assert docs_emp[0]["id"] == "NEX-TEST-001"

    resp_fin = client.get(
        "/documents",
        headers=auth_headers("finance"),
    )
    assert resp_fin.status_code == 200
    docs_fin = resp_fin.json()
    finance_ids = {doc["id"] for doc in docs_fin}

    assert len(docs_fin) == 2
    assert "NEX-TEST-001" in finance_ids
    assert "NEX-TEST-002" in finance_ids
    assert "NEX-TEST-003" not in finance_ids

    resp_exec = client.get(
        "/documents",
        headers=auth_headers("executive"),
    )
    assert resp_exec.status_code == 200
    docs_exec = resp_exec.json()
    executive_ids = {doc["id"] for doc in docs_exec}

    assert len(docs_exec) == 3
    assert {
        "NEX-TEST-001",
        "NEX-TEST-002",
        "NEX-TEST-003",
    } <= executive_ids


def test_get_document_endpoint_authorization(client):
    """Test authorized, forbidden, and nonexistent document access."""
    resp = client.get(
        "/documents/NEX-TEST-001",
        headers=auth_headers("employee"),
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == "NEX-TEST-001"

    unauthorized_resp = client.get(
        "/documents/NEX-TEST-002",
        headers=auth_headers("employee"),
    )
    assert unauthorized_resp.status_code == 403
    assert "Access denied" in unauthorized_resp.json()["detail"]

    missing_resp = client.get(
        "/documents/NEX-NONEXISTENT",
        headers=auth_headers("admin"),
    )
    assert missing_resp.status_code == 404


def test_search_endpoint(client):
    """Test search ranking and role-based filtering."""
    resp = client.post(
        "/search",
        json={"query": "office hours", "limit": 5},
        headers=auth_headers("employee"),
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["total_results"] >= 1
    assert data["role_applied"] == "employee"
    assert data["results"][0]["document_id"] == "NEX-TEST-001"

    finance_resp = client.post(
        "/search",
        json={"query": "treasury bills"},
        headers=auth_headers("employee"),
    )
    assert finance_resp.status_code == 200
    assert finance_resp.json()["total_results"] == 0


def test_ask_endpoint(client):
    """Test grounded answers and source citations."""
    resp = client.post(
        "/ask",
        json={
            "question": "What are the standard office hours?",
            "max_sources": 3,
        },
        headers=auth_headers("employee"),
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["confidence"] == "grounded"
    assert len(data["sources"]) >= 1
    assert data["sources"][0]["document_id"] == "NEX-TEST-001"
    assert "office hours" in data["answer"].lower()


def test_ask_endpoint_insufficient_evidence(client):
    """Test that unsupported questions receive an uncertainty response."""
    resp = client.post(
        "/ask",
        json={
            "question": "What is the secret recipe for Martian ice cream?",
            "max_sources": 3,
        },
        headers=auth_headers("employee"),
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["confidence"] == "insufficient_evidence"
    assert (
        "insufficient" in data["answer"].lower()
        or "no verified information" in data["answer"].lower()
    )


def test_sync_status_endpoint(client):
    """Only administrators can view synchronization status."""
    employee_resp = client.get(
        "/sync/status",
        headers=auth_headers("employee"),
    )
    assert employee_resp.status_code == 403

    admin_resp = client.get(
        "/sync/status",
        headers=auth_headers("admin"),
    )
    assert admin_resp.status_code == 200
    assert "is_syncing" in admin_resp.json()


def test_sync_requires_admin(client):
    """Only administrators can trigger synchronization."""
    employee_resp = client.post(
        "/sync",
        headers=auth_headers("employee"),
    )
    assert employee_resp.status_code == 403

    # An uncredentialed caller defaults to employee access.
    anonymous_resp = client.post("/sync")
    assert anonymous_resp.status_code == 403


def test_sync_rejects_forged_admin_role(client):
    """A role header alone must not authorize synchronization."""
    resp = client.post(
        "/sync",
        headers={"X-User-Role": "admin"},
    )
    assert resp.status_code == 403
