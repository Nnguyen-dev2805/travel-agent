"""Planner domain contracts for milestone R7.

Planner state describes choices and itinerary snapshots for one trip
workspace: immutable itinerary versions, explicit trip decisions including
rejected options, and an append-only operation log. It never describes
durable user preferences or facts; that remains memory's contract.

Validation follows the workspace and conversation model style: frozen
dataclasses, governed id prefixes, stripped text with length limits, blank
optional text normalized to `None`, and UTC datetimes. This module never
touches storage, models, RAG, memory, or orchestration.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Sequence

ITINERARY_VERSION_ID_PREFIX = "itv_"
DECISION_ID_PREFIX = "td_"
OPERATION_ID_PREFIX = "po_"
MESSAGE_ID_PREFIX = "ms_"

_TITLE_MAX_LENGTH = 120
_SUMMARY_MAX_LENGTH = 1000
_LOCATION_MAX_LENGTH = 160
_NOTES_MAX_LENGTH = 500
_STATEMENT_MAX_LENGTH = 500
_RATIONALE_MAX_LENGTH = 1000
_INPUT_SUMMARY_MAX_LENGTH = 1000

_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class PlannerValidationError(Exception):
    """A planner domain value violates its governed contract."""


def generate_itinerary_version_id() -> str:
    """Return a new opaque itinerary version identifier."""
    return f"{ITINERARY_VERSION_ID_PREFIX}{uuid.uuid4().hex}"


def generate_decision_id() -> str:
    """Return a new opaque trip decision identifier."""
    return f"{DECISION_ID_PREFIX}{uuid.uuid4().hex}"


def generate_operation_id() -> str:
    """Return a new opaque planner operation identifier."""
    return f"{OPERATION_ID_PREFIX}{uuid.uuid4().hex}"


def require_text(value: Any, field_name: str, max_length: int | None = None) -> str:
    """Strip and validate a required text field."""
    if not isinstance(value, str):
        raise PlannerValidationError(f"Planner field '{field_name}' must be a string.")
    stripped = value.strip()
    if not stripped:
        raise PlannerValidationError(f"Planner field '{field_name}' must not be empty.")
    if max_length is not None and len(stripped) > max_length:
        raise PlannerValidationError(
            f"Planner field '{field_name}' must be at most {max_length} characters."
        )
    return stripped


def _normalize_optional_text(
    value: Any, field_name: str, max_length: int
) -> str | None:
    """Strip an optional text field, treating a blank value as absent."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise PlannerValidationError(
            f"Planner field '{field_name}' must be a string or null."
        )
    stripped = value.strip()
    if not stripped:
        return None
    if len(stripped) > max_length:
        raise PlannerValidationError(
            f"Planner field '{field_name}' must be at most {max_length} characters."
        )
    return stripped


def _require_identity(value: Any, field_name: str, prefix: str) -> str:
    """Validate a server-generated identifier and its governed prefix."""
    identity = require_text(value, field_name)
    if not identity.startswith(prefix):
        raise PlannerValidationError(
            f"Planner field '{field_name}' must start with '{prefix}'."
        )
    return identity


def _normalize_optional_identity(
    value: Any, field_name: str, prefix: str
) -> str | None:
    """Validate an optional identifier reference, blank means absent."""
    if value is None:
        return None
    return _require_identity(value, field_name, prefix)


def _coerce_enum(value: Any, field_name: str, enum_type: type[Enum]) -> Enum:
    """Resolve an enum member or governed string vocabulary value."""
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        try:
            return enum_type(value)
        except ValueError as error:
            allowed = ", ".join(member.value for member in enum_type)
            raise PlannerValidationError(
                f"Unknown {field_name} value. Allowed values: {allowed}."
            ) from error
    raise PlannerValidationError(
        f"Planner field '{field_name}' must be a {enum_type.__name__} value."
    )


def _require_utc(value: Any, field_name: str) -> datetime:
    """Require a timezone-aware datetime and normalize it to UTC."""
    if not isinstance(value, datetime):
        raise PlannerValidationError(
            f"Planner field '{field_name}' must be a datetime."
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise PlannerValidationError(
            f"Planner field '{field_name}' must be timezone-aware UTC."
        )
    return value.astimezone(timezone.utc)


def _require_positive_int(value: Any, field_name: str) -> int:
    """Require a positive plain integer.

    `bool` is rejected explicitly. It is a subclass of `int`, so `True`
    would otherwise pass as the value `1`.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise PlannerValidationError(
            f"Planner field '{field_name}' must be a positive integer."
        )
    if value < 1:
        raise PlannerValidationError(
            f"Planner field '{field_name}' must be a positive integer."
        )
    return value


def _normalize_time(value: Any, field_name: str) -> str | None:
    """Normalize an optional local `HH:MM` time string."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise PlannerValidationError(
            f"Planner field '{field_name}' must be a string or null."
        )
    stripped = value.strip()
    if not _TIME_PATTERN.match(stripped):
        raise PlannerValidationError(
            f"Planner field '{field_name}' must be a local 'HH:MM' string."
        )
    return stripped


class ItineraryStatus(str, Enum):
    """Governed itinerary version lifecycle from the approved R7 spec."""

    DRAFT = "draft"
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class ItineraryItemType(str, Enum):
    """Governed itinerary item vocabulary from the approved R7 spec."""

    ACTIVITY = "activity"
    LODGING = "lodging"
    TRANSPORT = "transport"
    MEAL = "meal"
    FREE_TIME = "free_time"
    NOTE = "note"


class DecisionType(str, Enum):
    """Governed trip decision vocabulary from the approved R7 spec."""

    PREFERENCE = "preference"
    CONSTRAINT = "constraint"
    BOOKING = "booking"
    REJECTION = "rejection"
    TRADEOFF = "tradeoff"
    OPEN_QUESTION = "open_question"


class DecisionStatus(str, Enum):
    """Governed decision lifecycle from the approved R7 spec."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CHANGED = "changed"
    SUPERSEDED = "superseded"


class PlannerOperationType(str, Enum):
    """Governed planner operation vocabulary from the approved R7 spec."""

    CREATE_ITINERARY = "create_itinerary"
    ACCEPT_ITINERARY = "accept_itinerary"
    ARCHIVE_ITINERARY = "archive_itinerary"
    RECORD_DECISION = "record_decision"
    UPDATE_DECISION_STATUS = "update_decision_status"
    SUPERSEDE_DECISION = "supersede_decision"


class PlannerOperationStatus(str, Enum):
    """Governed operation outcome vocabulary: only `applied` exists in R7."""

    APPLIED = "applied"


@dataclass(frozen=True)
class ItineraryItem:
    """One structured stop inside an itinerary version snapshot."""

    day_index: int
    position: int
    item_type: ItineraryItemType
    title: str
    location: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    notes: str | None = None
    source_decision_ids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "day_index", _require_positive_int(self.day_index, "day_index")
        )
        object.__setattr__(
            self, "position", _require_positive_int(self.position, "position")
        )
        object.__setattr__(
            self,
            "item_type",
            _coerce_enum(self.item_type, "item_type", ItineraryItemType),
        )
        object.__setattr__(
            self, "title", require_text(self.title, "title", _TITLE_MAX_LENGTH)
        )
        object.__setattr__(
            self,
            "location",
            _normalize_optional_text(self.location, "location", _LOCATION_MAX_LENGTH),
        )
        object.__setattr__(
            self, "start_time", _normalize_time(self.start_time, "start_time")
        )
        object.__setattr__(self, "end_time", _normalize_time(self.end_time, "end_time"))
        object.__setattr__(
            self,
            "notes",
            _normalize_optional_text(self.notes, "notes", _NOTES_MAX_LENGTH),
        )
        decisions = tuple(self.source_decision_ids)
        for decision_id in decisions:
            _require_identity(decision_id, "source_decision_ids", DECISION_ID_PREFIX)
        object.__setattr__(self, "source_decision_ids", decisions)


@dataclass(frozen=True)
class ItineraryVersion:
    """One immutable itinerary snapshot inside a workspace."""

    itinerary_version_id: str
    workspace_id: str
    version_number: int
    status: ItineraryStatus
    title: str | None = None
    summary: str | None = None
    items: tuple[ItineraryItem, ...] = field(default_factory=tuple)
    created_from_operation_id: str | None = None
    created_from_message_id: str | None = None
    created_at: datetime = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "itinerary_version_id",
            _require_identity(
                self.itinerary_version_id,
                "itinerary_version_id",
                ITINERARY_VERSION_ID_PREFIX,
            ),
        )
        object.__setattr__(
            self, "workspace_id", require_text(self.workspace_id, "workspace_id")
        )
        object.__setattr__(
            self,
            "version_number",
            _require_positive_int(self.version_number, "version_number"),
        )
        object.__setattr__(
            self, "status", _coerce_enum(self.status, "status", ItineraryStatus)
        )
        object.__setattr__(
            self,
            "title",
            _normalize_optional_text(self.title, "title", _TITLE_MAX_LENGTH),
        )
        object.__setattr__(
            self,
            "summary",
            _normalize_optional_text(self.summary, "summary", _SUMMARY_MAX_LENGTH),
        )
        items = tuple(self.items)
        for item in items:
            if not isinstance(item, ItineraryItem):
                raise PlannerValidationError(
                    "Planner field 'items' must hold ItineraryItem entries."
                )
        object.__setattr__(self, "items", items)
        object.__setattr__(
            self,
            "created_from_operation_id",
            _normalize_optional_identity(
                self.created_from_operation_id,
                "created_from_operation_id",
                OPERATION_ID_PREFIX,
            ),
        )
        object.__setattr__(
            self,
            "created_from_message_id",
            _normalize_optional_identity(
                self.created_from_message_id,
                "created_from_message_id",
                MESSAGE_ID_PREFIX,
            ),
        )
        object.__setattr__(
            self, "created_at", _require_utc(self.created_at, "created_at")
        )


@dataclass(frozen=True)
class TripDecision:
    """One explicit planning decision, including rejected options."""

    decision_id: str
    workspace_id: str
    decision_type: DecisionType
    status: DecisionStatus
    statement: str
    rationale: str | None = None
    source_message_id: str | None = None
    supersedes_decision_id: str | None = None
    created_at: datetime = field(default=None)  # type: ignore[assignment]
    updated_at: datetime = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decision_id",
            _require_identity(self.decision_id, "decision_id", DECISION_ID_PREFIX),
        )
        object.__setattr__(
            self, "workspace_id", require_text(self.workspace_id, "workspace_id")
        )
        object.__setattr__(
            self,
            "decision_type",
            _coerce_enum(self.decision_type, "decision_type", DecisionType),
        )
        object.__setattr__(
            self, "status", _coerce_enum(self.status, "status", DecisionStatus)
        )
        object.__setattr__(
            self,
            "statement",
            require_text(self.statement, "statement", _STATEMENT_MAX_LENGTH),
        )
        object.__setattr__(
            self,
            "rationale",
            _normalize_optional_text(
                self.rationale, "rationale", _RATIONALE_MAX_LENGTH
            ),
        )
        object.__setattr__(
            self,
            "source_message_id",
            _normalize_optional_identity(
                self.source_message_id, "source_message_id", MESSAGE_ID_PREFIX
            ),
        )
        object.__setattr__(
            self,
            "supersedes_decision_id",
            _normalize_optional_identity(
                self.supersedes_decision_id,
                "supersedes_decision_id",
                DECISION_ID_PREFIX,
            ),
        )
        created_at = _require_utc(self.created_at, "created_at")
        updated_at = _require_utc(self.updated_at, "updated_at")
        if updated_at < created_at:
            raise PlannerValidationError(
                "Planner field 'updated_at' must not be earlier than 'created_at'."
            )
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)


@dataclass(frozen=True)
class PlannerOperation:
    """One append-only record of a successful planner state change."""

    operation_id: str
    workspace_id: str
    conversation_id: str | None
    operation_type: PlannerOperationType
    status: PlannerOperationStatus
    input_summary: str | None = None
    result_itinerary_version_id: str | None = None
    result_decision_id: str | None = None
    source_message_id: str | None = None
    created_at: datetime = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operation_id",
            _require_identity(self.operation_id, "operation_id", OPERATION_ID_PREFIX),
        )
        object.__setattr__(
            self, "workspace_id", require_text(self.workspace_id, "workspace_id")
        )
        if self.conversation_id is not None:
            object.__setattr__(
                self,
                "conversation_id",
                require_text(self.conversation_id, "conversation_id"),
            )
        object.__setattr__(
            self,
            "operation_type",
            _coerce_enum(self.operation_type, "operation_type", PlannerOperationType),
        )
        object.__setattr__(
            self,
            "status",
            _coerce_enum(self.status, "status", PlannerOperationStatus),
        )
        object.__setattr__(
            self,
            "input_summary",
            _normalize_optional_text(
                self.input_summary, "input_summary", _INPUT_SUMMARY_MAX_LENGTH
            ),
        )
        object.__setattr__(
            self,
            "result_itinerary_version_id",
            _normalize_optional_identity(
                self.result_itinerary_version_id,
                "result_itinerary_version_id",
                ITINERARY_VERSION_ID_PREFIX,
            ),
        )
        object.__setattr__(
            self,
            "result_decision_id",
            _normalize_optional_identity(
                self.result_decision_id,
                "result_decision_id",
                DECISION_ID_PREFIX,
            ),
        )
        object.__setattr__(
            self,
            "source_message_id",
            _normalize_optional_identity(
                self.source_message_id, "source_message_id", MESSAGE_ID_PREFIX
            ),
        )
        object.__setattr__(
            self, "created_at", _require_utc(self.created_at, "created_at")
        )


__all__ = [
    "DECISION_ID_PREFIX",
    "ITINERARY_VERSION_ID_PREFIX",
    "MESSAGE_ID_PREFIX",
    "OPERATION_ID_PREFIX",
    "DecisionStatus",
    "DecisionType",
    "ItineraryItem",
    "ItineraryItemType",
    "ItineraryStatus",
    "ItineraryVersion",
    "PlannerOperation",
    "PlannerOperationStatus",
    "PlannerOperationType",
    "PlannerValidationError",
    "TripDecision",
    "generate_decision_id",
    "generate_itinerary_version_id",
    "generate_operation_id",
    "require_text",
]
