
"""
Role-Based Access Control (RBAC) and Security Authorization for Company Brain.

Development authentication uses predefined bearer tokens.
Client-supplied identity and role headers cannot independently grant access.

IMPORTANT:
This is a local development authentication mechanism, not production-ready
authentication. Replace it with verified OAuth2/OIDC or signed JWT validation
before deployment.
"""

from enum import Enum
from typing import Optional, Set

from fastapi import Header, HTTPException, status
from pydantic import BaseModel


class UserRole(str, Enum):
    EMPLOYEE = "employee"
    MANAGER = "manager"
    HR = "hr"
    FINANCE = "finance"
    EXECUTIVE = "executive"
    ADMIN = "admin"


# Classifications each role is permitted to access.
ROLE_CLEARANCE_MAP: dict[UserRole, Set[str]] = {
    UserRole.EMPLOYEE: {"employee"},
    UserRole.MANAGER: {"employee", "manager"},
    UserRole.HR: {"employee", "hr"},
    UserRole.FINANCE: {"employee", "finance"},
    UserRole.EXECUTIVE: {
        "employee",
        "manager",
        "hr",
        "finance",
        "executive",
    },
    UserRole.ADMIN: {
        "employee",
        "manager",
        "hr",
        "finance",
        "executive",
        "admin",
    },
}


class DevUserProfile(BaseModel):
    user_id: str
    display_name: str
    role: UserRole
    dev_token: str


# Local development identities and credentials.
# Never use these hardcoded credentials in production.
DEV_USERS: dict[str, DevUserProfile] = {
    "emp_alex": DevUserProfile(
        user_id="emp_alex",
        display_name="Alex Morgan",
        role=UserRole.EMPLOYEE,
        dev_token="dev-tok-employee-01",
    ),
    "mgr_maya": DevUserProfile(
        user_id="mgr_maya",
        display_name="Maya Chen",
        role=UserRole.MANAGER,
        dev_token="dev-tok-manager-02",
    ),
    "hr_elena": DevUserProfile(
        user_id="hr_elena",
        display_name="Elena Rodriguez",
        role=UserRole.HR,
        dev_token="dev-tok-hr-03",
    ),
    "fin_evelyn": DevUserProfile(
        user_id="fin_evelyn",
        display_name="Evelyn Carter",
        role=UserRole.FINANCE,
        dev_token="dev-tok-finance-04",
    ),
    "exec_aris": DevUserProfile(
        user_id="exec_aris",
        display_name="Aris Bennett",
        role=UserRole.EXECUTIVE,
        dev_token="dev-tok-executive-05",
    ),
    "adm_tariq": DevUserProfile(
        user_id="adm_tariq",
        display_name="Tariq Hassan",
        role=UserRole.ADMIN,
        dev_token="dev-tok-admin-06",
    ),
}


# Token lookup is the source of truth for the authenticated role.
DEV_TOKEN_MAP: dict[str, UserRole] = {
    user.dev_token: user.role
    for user in DEV_USERS.values()
}


def normalize_role(role_name: Optional[str]) -> UserRole:
    """Convert a role string into a valid UserRole."""
    if not role_name:
        return UserRole.EMPLOYEE

    normalized = role_name.strip().lower()

    try:
        return UserRole(normalized)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {role_name}",
        )


def get_allowed_classifications_for_role(
    role: UserRole | str,
) -> Set[str]:
    """Return the document classifications visible to a role."""
    if isinstance(role, str):
        role = normalize_role(role)

    return ROLE_CLEARANCE_MAP.get(role, {"employee"})


def is_role_authorized(
    role: UserRole | str,
    document_classification: Optional[str],
) -> bool:
    """Check whether a role can access a document classification."""
    if isinstance(role, str):
        role = normalize_role(role)

    if not document_classification:
        return False

    classification = document_classification.strip().lower()

    return classification in get_allowed_classifications_for_role(role)


def get_current_role(
    x_user_id: Optional[str] = Header(None),
    x_user_role: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
) -> str:
    """
    Resolve the caller's role from a recognized development bearer token.

    Security behavior:
    - X-User-Role alone never grants elevated privileges.
    - X-User-Id alone never authenticates a caller.
    - A recognized bearer token determines the caller's role.
    - A conflicting X-User-Role claim is rejected.
    - An invalid supplied bearer token is rejected.
    - Requests without credentials receive employee-level access.
    """
    token: Optional[str] = None

    if authorization:
        scheme, separator, credentials = authorization.partition(" ")

        if (
            not separator
            or scheme.lower() != "bearer"
            or not credentials.strip()
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = credentials.strip()

    if token is not None:
        assigned_role = DEV_TOKEN_MAP.get(token)

        if assigned_role is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or unrecognized bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Do not allow a client to override its token's assigned role.
        if x_user_role:
            claimed_role = normalize_role(x_user_role)

            if claimed_role != assigned_role:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Privilege escalation attempt: requested role "
                        "does not match the authenticated user's assigned role."
                    ),
                )

        # The user ID header is not used to establish identity.
        return assigned_role.value

    # Headers supplied by an unauthenticated client are not trusted.
    # No token means employee-level access, regardless of claimed identity.
    return UserRole.EMPLOYEE.value
