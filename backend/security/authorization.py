"""Owner/workspace authorization helpers for milestone R9.

Helpers decide from resolved owner labels and the principal only. A
missing resource and a foreign-owned resource raise the same
`CrossOwnerAccessError`, so routes map both to one not-found body that
never reveals existence across owners. Blank identifiers pass through
untouched so service input validation keeps owning `422` behavior.

Compatibility mode performs no check: the returned owner labels only
describe local scope, and compatibility traffic must never serve as
authenticated isolation evidence.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException

from backend.app.config import settings
from backend.security.models import (
    AuthMode,
    AuthenticatedPrincipal,
    CrossOwnerAccessError,
    OwnerForbiddenError,
)
from backend.workspaces.repository import WorkspaceRepositoryError
from backend.workspaces.sqlite_repository import SQLiteWorkspaceRepository

logger = logging.getLogger("travel_agent_security")

_STORAGE_ERROR_DETAIL = "Workspace storage is unavailable."


def get_workspace_repository() -> SQLiteWorkspaceRepository:
    """Construct the workspace repository for authorization lookups.

    Routes depend on this alongside their service so owner resolution
    reads the same database the service will use. Tests override it with
    a temporary database path.
    """
    try:
        return SQLiteWorkspaceRepository(db_path=settings.APP_DB_PATH)
    except WorkspaceRepositoryError as error:
        logger.error(
            "security.storage unavailable failure_class=%s", type(error).__name__
        )
        raise HTTPException(status_code=500, detail=_STORAGE_ERROR_DETAIL) from error


def _is_compat(principal: AuthenticatedPrincipal) -> bool:
    return principal.auth_mode is AuthMode.COMPATIBILITY


def _blank(value: object) -> bool:
    return not isinstance(value, str) or not value.strip()


def resolve_workspace_owner_id(workspace_id: str, workspaces) -> str:
    """Return the owning label, or deny missing ids without disclosure."""
    if _blank(workspace_id):
        return workspace_id
    workspace = workspaces.get(workspace_id)
    if workspace is None:
        raise CrossOwnerAccessError("The workspace does not exist in this owner scope.")
    return workspace.owner_user_id


def require_workspace_owner(
    workspace_id: str, workspaces, principal: AuthenticatedPrincipal
) -> str:
    """Require principal ownership of a workspace id.

    Returns the owner label for logging. Compatibility mode performs no
    repository read at all, so legacy behavior and test database
    isolation stay exactly as before; only auth mode resolves and
    compares the owner.
    """
    if _is_compat(principal) or _blank(workspace_id):
        return ""
    owner = resolve_workspace_owner_id(workspace_id, workspaces)
    if owner != principal.owner_user_id:
        raise CrossOwnerAccessError("The workspace does not exist in this owner scope.")
    return owner


def require_create_owner(body_owner_id: str, principal: AuthenticatedPrincipal) -> None:
    """Forbid creating under another owner's label in auth mode."""
    if _is_compat(principal) or _blank(body_owner_id):
        return
    cleaned = body_owner_id.strip() if isinstance(body_owner_id, str) else ""
    if cleaned != principal.owner_user_id:
        raise OwnerForbiddenError("The workspace owner does not match the principal.")


def scope_list_owner(
    requested_owner_id: Optional[str], principal: AuthenticatedPrincipal
) -> Optional[str]:
    """Resolve the owner scope a list query may read.

    Compatibility mode passes the caller label through unchanged. Auth
    mode scopes a blank label to the principal and forbids any other
    label, so one owner can never list another owner's scope.
    """
    if _is_compat(principal):
        return requested_owner_id
    cleaned = requested_owner_id.strip() if isinstance(requested_owner_id, str) else ""
    if not cleaned:
        return principal.owner_user_id
    if cleaned != principal.owner_user_id:
        raise OwnerForbiddenError("The list owner scope does not match the principal.")
    return principal.owner_user_id
