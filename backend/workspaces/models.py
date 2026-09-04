"""Trip workspace value contracts for runtime milestone R3.

`TripWorkspace` is the primary product container per ADR 0002. This module owns
the workspace contract vocabulary defined by the approved R3 specification and
must remain storage-agnostic and route-agnostic: it depends on the Python
standard library only, and never on FastAPI, Pydantic, SQLite, RAG, Chroma, a
model provider, or the evaluation subsystem.

`owner_user_id` is a local development scope label supplied by the caller. It is
not authentication, authorization, a verified principal, or tenant isolation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

WORKSPACE_ID_PREFIX = "tw_"
TITLE_MAX_LENGTH = 120
DESTINATION_SCOPE_MAX_LENGTH = 160


class WorkspaceValidationError(ValueError):
    """A workspace contract rule was violated before any storage write."""


class PlanningStatus(str, Enum):
    """Planning lifecycle vocabulary from the approved R3 specification."""

    IDEA = "idea"
    PLANNING = "planning"
    BOOKED = "booked"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class RetentionState(str, Enum):
    """Retention vocabulary from the approved R3 specification.

    R3 creates records as `ACTIVE` only and implements no transition into the
    other states. Deletion and tombstoning semantics require a later approved
    design.
    """

    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETION_REQUESTED = "deletion_requested"
    DELETED = "deleted"


DEFAULT_PLANNING_STATUS = PlanningStatus.IDEA
DEFAULT_RETENTION_STATE = RetentionState.ACTIVE


def generate_workspace_id() -> str:
    """Return a new opaque workspace identifier using the governed prefix."""
    return f"{WORKSPACE_ID_PREFIX}{uuid.uuid4().hex}"


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def require_text(value: Any, field_name: str, max_length: int | None = None) -> str:
    """Strip and validate a required text field."""
    if not isinstance(value, str):
        raise WorkspaceValidationError(
            f"Workspace field '{field_name}' must be a string."
        )
    stripped = value.strip()
    if not stripped:
        raise WorkspaceValidationError(
            f"Workspace field '{field_name}' must not be empty."
        )
    if max_length is not None and len(stripped) > max_length:
        raise WorkspaceValidationError(
            f"Workspace field '{field_name}' must be at most {max_length} characters."
        )
    return stripped


def _normalize_optional_text(
    value: Any, field_name: str, max_length: int
) -> str | None:
    """Strip an optional text field, treating a blank value as absent."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise WorkspaceValidationError(
            f"Workspace field '{field_name}' must be a string or null."
        )
    stripped = value.strip()
    if not stripped:
        return None
    if len(stripped) > max_length:
        raise WorkspaceValidationError(
            f"Workspace field '{field_name}' must be at most {max_length} characters."
        )
    return stripped


def _coerce_planning_status(value: Any) -> PlanningStatus:
    """Resolve an absent, enum, or governed string planning status."""
    if value is None:
        return DEFAULT_PLANNING_STATUS
    if isinstance(value, PlanningStatus):
        return value
    if isinstance(value, str):
        try:
            return PlanningStatus(value)
        except ValueError as error:
            allowed = ", ".join(status.value for status in PlanningStatus)
            raise WorkspaceValidationError(
                f"Unknown planning_status '{value}'. Allowed values: {allowed}."
            ) from error
    raise WorkspaceValidationError(
        "Workspace field 'planning_status' must be a planning status value."
    )


def _coerce_retention_state(value: Any) -> RetentionState:
    """Resolve an absent, enum, or governed string retention state."""
    if value is None:
        return DEFAULT_RETENTION_STATE
    if isinstance(value, RetentionState):
        return value
    raise WorkspaceValidationError(
        "Workspace field 'retention_state' must be a RetentionState value."
    )


def _require_utc(value: Any, field_name: str) -> datetime:
    """Require a timezone-aware datetime and normalize it to UTC."""
    if not isinstance(value, datetime):
        raise WorkspaceValidationError(
            f"Workspace field '{field_name}' must be a datetime."
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise WorkspaceValidationError(
            f"Workspace field '{field_name}' must be timezone-aware UTC."
        )
    return value.astimezone(timezone.utc)


def _optional_date(value: Any, field_name: str) -> date | None:
    """Validate an optional calendar date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        raise WorkspaceValidationError(
            f"Workspace field '{field_name}' must be a date, not a datetime."
        )
    if not isinstance(value, date):
        raise WorkspaceValidationError(
            f"Workspace field '{field_name}' must be a date or null."
        )
    return value


@dataclass(frozen=True)
class DateWindow:
    """Optional planned travel window.

    Either bound may be absent. When both are present, `end_date` must not be
    earlier than `start_date`.
    """

    start_date: date | None = None
    end_date: date | None = None

    def __post_init__(self) -> None:
        start = _optional_date(self.start_date, "start_date")
        end = _optional_date(self.end_date, "end_date")
        if start is not None and end is not None and end < start:
            raise WorkspaceValidationError(
                "Workspace date window requires end_date to be on or after start_date."
            )
        object.__setattr__(self, "start_date", start)
        object.__setattr__(self, "end_date", end)


def _normalize_shared_fields(instance: Any) -> None:
    """Normalize and validate the fields shared by workspace value objects.

    `WorkspaceCreate` validates caller input; `TripWorkspace` validates the same
    fields again because it is also rehydrated from storage, where a row could
    violate the contract. Both call sites are required, so the rules live here
    once instead of being written twice.
    """
    object.__setattr__(
        instance, "owner_user_id", require_text(instance.owner_user_id, "owner_user_id")
    )
    object.__setattr__(
        instance, "title", require_text(instance.title, "title", TITLE_MAX_LENGTH)
    )
    object.__setattr__(
        instance,
        "destination_scope",
        _normalize_optional_text(
            instance.destination_scope,
            "destination_scope",
            DESTINATION_SCOPE_MAX_LENGTH,
        ),
    )
    if instance.date_window is not None and not isinstance(
        instance.date_window, DateWindow
    ):
        raise WorkspaceValidationError(
            "Workspace field 'date_window' must be a DateWindow or null."
        )
    object.__setattr__(
        instance, "planning_status", _coerce_planning_status(instance.planning_status)
    )


@dataclass(frozen=True)
class WorkspaceCreate:
    """Validated input for creating one trip workspace.

    This contract deliberately has no `workspace_id` field. Identity is
    generated by the workspace service, never accepted from caller input.
    """

    owner_user_id: str
    title: str
    destination_scope: str | None = None
    date_window: DateWindow | None = None
    planning_status: PlanningStatus | str | None = None

    def __post_init__(self) -> None:
        _normalize_shared_fields(self)


@dataclass(frozen=True)
class WorkspaceListFilter:
    """Validated owner scope label used to list workspaces."""

    owner_user_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "owner_user_id", require_text(self.owner_user_id, "owner_user_id")
        )


@dataclass(frozen=True)
class TripWorkspace:
    """One persisted trip workspace record.

    `retention_state` is declared last so it can carry its R3 default while the
    timestamp fields remain required. The field set, types, and defaults match
    the approved R3 specification.
    """

    workspace_id: str
    owner_user_id: str
    title: str
    destination_scope: str | None
    date_window: DateWindow | None
    planning_status: PlanningStatus
    created_at: datetime
    updated_at: datetime
    retention_state: RetentionState = field(default=DEFAULT_RETENTION_STATE)

    def __post_init__(self) -> None:
        workspace_id = require_text(self.workspace_id, "workspace_id")
        if not workspace_id.startswith(WORKSPACE_ID_PREFIX):
            raise WorkspaceValidationError(
                f"Workspace field 'workspace_id' must start with "
                f"'{WORKSPACE_ID_PREFIX}'."
            )
        object.__setattr__(self, "workspace_id", workspace_id)
        _normalize_shared_fields(self)
        object.__setattr__(
            self, "retention_state", _coerce_retention_state(self.retention_state)
        )
        object.__setattr__(
            self, "created_at", _require_utc(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", _require_utc(self.updated_at, "updated_at")
        )
