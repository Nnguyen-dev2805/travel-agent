"""Trip workspace module for runtime milestone R3.

This package owns workspace value contracts, the storage interface, the local
SQLite adapter, and workspace use cases. `TripWorkspace` is the primary product
container per ADR 0002; SQLite is a local development adapter behind the
repository boundary per ADR 0003.

R3 implements no authentication, authorization, collaboration, conversation
persistence, memory, planner state, itinerary versions, or deletion semantics.
`owner_user_id` is a local development scope label, not a verified principal.

Import from the submodules directly. This module re-exports only the names a
caller outside the package needs to construct the workspace stack.
"""

from backend.workspaces.models import (
    DateWindow,
    PlanningStatus,
    RetentionState,
    TripWorkspace,
    WorkspaceCreate,
    WorkspaceValidationError,
)
from backend.workspaces.repository import (
    WorkspaceRepository,
    WorkspaceRepositoryError,
)
from backend.workspaces.service import WorkspaceService
from backend.workspaces.sqlite_repository import SQLiteWorkspaceRepository

__all__ = [
    "DateWindow",
    "PlanningStatus",
    "RetentionState",
    "SQLiteWorkspaceRepository",
    "TripWorkspace",
    "WorkspaceCreate",
    "WorkspaceRepository",
    "WorkspaceRepositoryError",
    "WorkspaceService",
    "WorkspaceValidationError",
]
