"""Workspace use cases for runtime milestone R3.

The service owns validation, identity generation, timestamping, and repository
calls. It depends on the workspace contracts and the repository interface only,
never on FastAPI, SQLite, RAG, Chroma, a model provider, or the evaluation
subsystem.
"""

from __future__ import annotations

from backend.workspaces.models import (
    TripWorkspace,
    WorkspaceCreate,
    WorkspaceListFilter,
    WorkspaceValidationError,
    generate_workspace_id,
    require_text,
    utc_now,
)
from backend.workspaces.repository import (
    WorkspaceAlreadyExistsError,
    WorkspaceRepository,
    WorkspaceStorageError,
)

MAX_IDENTITY_ATTEMPTS = 2
"""One initial attempt plus exactly one retry on a generated-identity collision."""


class WorkspaceService:
    """Create and inspect trip workspace records behind approved contracts."""

    def __init__(self, repository: WorkspaceRepository) -> None:
        self._repository = repository

    def create_workspace(self, workspace_input: WorkspaceCreate) -> TripWorkspace:
        """Create one workspace record.

        `WorkspaceCreate` has already normalized and validated its fields, so an
        invalid input raises before this method is reached and no storage write
        occurs.

        A generated-identity collision is retried exactly once with a fresh
        identity. A second collision raises `WorkspaceStorageError` rather than
        leaving a partial write or looping.

        Raises:
            WorkspaceValidationError: The input is not a `WorkspaceCreate`.
            WorkspaceStorageError: Identity generation collided twice, storage
                failed, or the identity attempt budget is not positive.
        """
        if not isinstance(workspace_input, WorkspaceCreate):
            raise WorkspaceValidationError(
                "create_workspace requires a WorkspaceCreate input."
            )

        moment = utc_now()

        for remaining in reversed(range(MAX_IDENTITY_ATTEMPTS)):
            candidate = TripWorkspace(
                workspace_id=generate_workspace_id(),
                owner_user_id=workspace_input.owner_user_id,
                title=workspace_input.title,
                destination_scope=workspace_input.destination_scope,
                date_window=workspace_input.date_window,
                planning_status=workspace_input.planning_status,
                created_at=moment,
                updated_at=moment,
            )
            try:
                return self._repository.create(candidate)
            except WorkspaceAlreadyExistsError:
                if remaining == 0:
                    raise WorkspaceStorageError(
                        "Could not allocate a unique workspace identity after "
                        f"{MAX_IDENTITY_ATTEMPTS} attempts."
                    ) from None

        raise WorkspaceStorageError(
            "Workspace creation made no storage attempt because the configured "
            "identity attempt budget is not positive."
        )

    def get_workspace(self, workspace_id: str) -> TripWorkspace | None:
        """Return one workspace by identifier, or None when no record exists.

        Raises:
            WorkspaceValidationError: The identifier is blank.
        """
        return self._repository.get(require_text(workspace_id, "workspace_id"))

    def list_workspaces(self, owner_user_id: str) -> tuple[TripWorkspace, ...]:
        """Return workspaces for one local development owner scope label.

        `owner_user_id` is a scope label, not authentication or authorization.
        Ordering is owned by the repository and is not mutated here.

        Raises:
            WorkspaceValidationError: The owner scope label is blank.
        """
        scope = WorkspaceListFilter(owner_user_id=owner_user_id)
        return tuple(self._repository.list_by_owner(scope.owner_user_id))
