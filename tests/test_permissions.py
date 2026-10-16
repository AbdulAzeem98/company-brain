"""Tests for Role-Based Access Control (RBAC) and unauthorized access prevention."""

import pytest
from fastapi import HTTPException
from app.permissions import (
    UserRole,
    get_allowed_classifications_for_role,
    is_role_authorized,
    normalize_role,
)


def test_role_normalization_and_clearance():
    """Verify role normalization and clearance sets."""
    assert normalize_role("EMPLOYEE") == UserRole.EMPLOYEE
    assert normalize_role(" finance ") == UserRole.FINANCE
    assert normalize_role(None) == UserRole.EMPLOYEE

    # Invalid role raises 400
    with pytest.raises(HTTPException) as exc:
        normalize_role("super_hacker")
    assert exc.value.status_code == 400

    # Clearance mapping tests
    employee_clearance = get_allowed_classifications_for_role(UserRole.EMPLOYEE)
    assert employee_clearance == {"employee"}

    manager_clearance = get_allowed_classifications_for_role(UserRole.MANAGER)
    assert manager_clearance == {"employee", "manager"}

    hr_clearance = get_allowed_classifications_for_role(UserRole.HR)
    assert hr_clearance == {"employee", "hr"}

    finance_clearance = get_allowed_classifications_for_role(UserRole.FINANCE)
    assert finance_clearance == {"employee", "finance"}

    executive_clearance = get_allowed_classifications_for_role(UserRole.EXECUTIVE)
    assert executive_clearance == {"employee", "manager", "hr", "finance", "executive"}

    admin_clearance = get_allowed_classifications_for_role(UserRole.ADMIN)
    assert admin_clearance == {"employee", "manager", "hr", "finance", "executive", "admin"}


def test_is_role_authorized_predicate():
    """Verify authorization checks against document classification."""
    assert is_role_authorized("employee", "employee") is True
    assert is_role_authorized("employee", "finance") is False
    assert is_role_authorized("employee", "executive") is False

    assert is_role_authorized("finance", "employee") is True
    assert is_role_authorized("finance", "finance") is True
    assert is_role_authorized("finance", "executive") is False

    assert is_role_authorized("admin", "executive") is True
    assert is_role_authorized("admin", "admin") is True


def test_unauthorized_document_access_raises_403(temp_environment):
    """Verify server rejects unauthorized access attempts to documents with 403 Forbidden."""
    knowledge_service = temp_environment["knowledge_service"]

    # 1. Employee accessing employee doc (OK)
    doc = knowledge_service.get_document("NEX-TEST-001", role="employee")
    assert doc.id == "NEX-TEST-001"

    # 2. Employee attempting to access confidential finance document -> 403 Forbidden
    with pytest.raises(HTTPException) as exc1:
        knowledge_service.get_document("NEX-TEST-002", role="employee")
    assert exc1.value.status_code == 403
    assert "Access denied" in exc1.value.detail

    # 3. Employee attempting to access executive board minutes -> 403 Forbidden
    with pytest.raises(HTTPException) as exc2:
        knowledge_service.get_document("NEX-TEST-003", role="employee")
    assert exc2.value.status_code == 403

    # 4. Finance user attempting to access executive doc -> 403 Forbidden
    with pytest.raises(HTTPException) as exc3:
        knowledge_service.get_document("NEX-TEST-003", role="finance")
    assert exc3.value.status_code == 403

    # 5. Executive accessing executive doc -> 200 OK
    exec_doc = knowledge_service.get_document("NEX-TEST-003", role="executive")
    assert exec_doc.id == "NEX-TEST-003"

    # 6. Admin accessing finance doc -> 200 OK
    admin_doc = knowledge_service.get_document("NEX-TEST-002", role="admin")
    assert admin_doc.id == "NEX-TEST-002"


def test_nonexistent_document_raises_404(temp_environment):
    """Verify accessing non-existent document returns 404 Not Found."""
    knowledge_service = temp_environment["knowledge_service"]

    with pytest.raises(HTTPException) as exc:
        knowledge_service.get_document("NEX-DOES-NOT-EXIST", role="admin")
    assert exc.value.status_code == 404
