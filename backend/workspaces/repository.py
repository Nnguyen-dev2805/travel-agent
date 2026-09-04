"""Workspace storage interface and repository error types for milestone R3.

Per ADR 0003, product code depends on this interface rather than on SQLite
details. Route handlers and the workspace service must not embed table DDL, SQL
statements, path creation, or connection management.
"""

from __future__ import annotations

from typing import Protocol

from backend.workspaces.models import TripWorkspace


class WorkspaceRepositoryError(Exception):
    """Base class for workspace storage failures."""


class WorkspaceAlreadyExistsError(WorkspaceRepositoryError):
    """A workspace with the same identity already exists in storage."""


class WorkspaceStorageError(WorkspaceRepositoryError):
    """Storage could not complete the requested workspace operation.

    Messages raised as this type are safe for a controlled HTTP 500 response.
    They must not carry local filesystem paths, full SQL text, credentials, or
    full user-entered workspace content.
    """


class WorkspaceRepository(Protocol):
    """Persistence boundary for trip workspace records."""

    def create(self, workspace: TripWorkspace) -> TripWorkspace:
        """Persist a new workspace and return the stored record.

        Raises:
            WorkspaceAlreadyExistsError: The workspace identity is already used.
            WorkspaceStorageError: Storage failed for another reason.
        """
        ...

    def get(self, workspace_id: str) -> TripWorkspace | None:
        """Return the stored workspace, or None when no record exists."""
        ...

    def list_by_owner(self, owner_user_id: str) -> tuple[TripWorkspace, ...]:
        """Return workspaces for one owner scope label in governed order.

        Ordering is `updated_at` descending, then `created_at` descending, then
        `workspace_id` ascending.
        """
        ...
