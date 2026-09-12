"""Observability domain contracts for milestone R8.

Events, readiness snapshots, and their vocabularies live here. This module
uses only the standard library: it must not import RAG, memory, planner,
workspace, conversation, orchestration, or route modules, so product code
can depend on it without creating cycles.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

REQUEST_ID_PREFIX = "rq_"
EVENT_ID_PREFIX = "ev_"

MAX_COUNTERS = 16
MAX_COUNTER_STRING_LENGTH = 200


class ObservabilityValidationError(Exception):
    """An observability value violates its governed contract."""


def generate_request_id() -> str:
    """Return a new server-generated request correlation identifier."""
    return f"{REQUEST_ID_PREFIX}{uuid.uuid4().hex}"


def generate_event_id() -> str:
    """Return a new server-generated operational event identifier."""
    return f"{EVENT_ID_PREFIX}{uuid.uuid4().hex}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EventSeverity(str, Enum):
    """Governed event severity vocabulary."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class EventResult(str, Enum):
    """Governed event outcome vocabulary."""

    SUCCESS = "success"
    FAILURE = "failure"
    DEGRADED = "degraded"
    SKIPPED = "skipped"


class EventName(str, Enum):
    """Governed operational event names.

    The set is closed on purpose: stable names let a future operator map
    local events to production tracing, so adding a name is a deliberate
    contract change rather than a call-site invention.
    """

    API_REQUEST_COMPLETED = "api.request.completed"
    CHAT_REQUEST_ACCEPTED = "chat.request.accepted"
    CHAT_TURN_COMPLETED = "chat.turn.completed"
    RAG_RETRIEVAL_COMPLETED = "rag.retrieval.completed"
    MODEL_CALL_COMPLETED = "model.call.completed"
    MODEL_CALL_FAILED = "model.call.failed"
    MEMORY_RETRIEVAL_COMPLETED = "memory.retrieval.completed"
    MEMORY_EXTRACTION_COMPLETED = "memory.extraction.completed"
    PLANNER_OPERATION_APPLIED = "planner.operation.applied"
    STORAGE_SCHEMA_FAILED = "storage.schema.failed"
    OPS_READINESS_COMPLETED = "ops.readiness.completed"


class EventComponent(str, Enum):
    """Governed event component vocabulary."""

    API = "api"
    CHAT = "chat"
    RAG = "rag"
    MODEL_PROVIDER = "model_provider"
    STORAGE = "storage"
    WORKSPACE = "workspace"
    CONVERSATION = "conversation"
    MEMORY = "memory"
    PLANNER = "planner"
    OPS = "ops"


class ReadinessStatus(str, Enum):
    """Governed readiness state vocabulary."""

    READY = "ready"
    DEGRADED = "degraded"
    NOT_READY = "not_ready"
    UNKNOWN = "unknown"


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ObservabilityValidationError(
            f"Observability field '{field_name}' must be a non-empty string."
        )
    return value


def _require_identity(value: Any, field_name: str, prefix: str) -> str:
    identity = _require_text(value, field_name)
    if not identity.startswith(prefix):
        raise ObservabilityValidationError(
            f"Observability field '{field_name}' must start with '{prefix}'."
        )
    return identity


def _normalize_optional_identity(
    value: Any, field_name: str, prefix: str
) -> str | None:
    if value is None:
        return None
    return _require_identity(value, field_name, prefix)


def _coerce_enum(value: Any, field_name: str, enum_type: type[Enum]) -> Enum:
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        try:
            return enum_type(value)
        except ValueError as error:
            allowed = ", ".join(member.value for member in enum_type)
            raise ObservabilityValidationError(
                f"Unknown {field_name} value. Allowed values: {allowed}."
            ) from error
    raise ObservabilityValidationError(
        f"Observability field '{field_name}' must be a {enum_type.__name__} value."
    )


def _require_utc(value: Any, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ObservabilityValidationError(
            f"Observability field '{field_name}' must be a datetime."
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise ObservabilityValidationError(
            f"Observability field '{field_name}' must be timezone-aware UTC."
        )
    return value.astimezone(timezone.utc)


def _require_duration(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ObservabilityValidationError(
            f"Observability field '{field_name}' must be a non-negative number."
        )
    if value < 0:
        raise ObservabilityValidationError(
            f"Observability field '{field_name}' must be a non-negative number."
        )
    return value


def require_counters(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ObservabilityValidationError(
            f"Observability field '{field_name}' must be a mapping."
        )
    if len(value) > MAX_COUNTERS:
        raise ObservabilityValidationError(
            f"Observability field '{field_name}' must hold at most "
            f"{MAX_COUNTERS} entries."
        )
    cleaned: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ObservabilityValidationError(
                f"Observability field '{field_name}' keys must be non-empty strings."
            )
        if isinstance(item, bool):
            cleaned[key] = item
        elif isinstance(item, (int, float)):
            cleaned[key] = item
        elif isinstance(item, str):
            if len(item) > MAX_COUNTER_STRING_LENGTH:
                raise ObservabilityValidationError(
                    f"Observability field '{field_name}' string values must "
                    f"be at most {MAX_COUNTER_STRING_LENGTH} characters."
                )
            cleaned[key] = item
        else:
            raise ObservabilityValidationError(
                f"Observability field '{field_name}' values must be bounded scalars."
            )
    return cleaned


@dataclass(frozen=True)
class OperationalEvent:
    """One structured privacy-safe operational event.

    Only governed safe fields exist: identifiers, controlled reason codes,
    durations, and bounded counters. Raw content never reaches this type;
    `sanitize_event_fields` guards the dynamic boundary instead.
    """

    event_id: str
    timestamp: datetime
    event_name: EventName
    component: EventComponent
    severity: EventSeverity
    result: EventResult
    request_id: str | None = None
    workspace_id: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    memory_id: str | None = None
    itinerary_version_id: str | None = None
    decision_id: str | None = None
    operation_id: str | None = None
    failure_class: str | None = None
    reason_code: str | None = None
    duration_ms: float | None = None
    counters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "event_id",
            _require_identity(self.event_id, "event_id", EVENT_ID_PREFIX),
        )
        object.__setattr__(self, "timestamp", _require_utc(self.timestamp, "timestamp"))
        object.__setattr__(
            self,
            "event_name",
            _coerce_enum(self.event_name, "event_name", EventName),
        )
        object.__setattr__(
            self,
            "component",
            _coerce_enum(self.component, "component", EventComponent),
        )
        object.__setattr__(
            self,
            "severity",
            _coerce_enum(self.severity, "severity", EventSeverity),
        )
        object.__setattr__(
            self, "result", _coerce_enum(self.result, "result", EventResult)
        )
        object.__setattr__(
            self,
            "request_id",
            _normalize_optional_identity(
                self.request_id, "request_id", REQUEST_ID_PREFIX
            ),
        )
        object.__setattr__(
            self,
            "workspace_id",
            _normalize_optional_identity(self.workspace_id, "workspace_id", "tw_"),
        )
        object.__setattr__(
            self,
            "conversation_id",
            _normalize_optional_identity(
                self.conversation_id, "conversation_id", "cv_"
            ),
        )
        object.__setattr__(
            self,
            "message_id",
            _normalize_optional_identity(self.message_id, "message_id", "ms_"),
        )
        object.__setattr__(
            self,
            "memory_id",
            _normalize_optional_identity(self.memory_id, "memory_id", "mem_"),
        )
        object.__setattr__(
            self,
            "itinerary_version_id",
            _normalize_optional_identity(
                self.itinerary_version_id,
                "itinerary_version_id",
                "itv_",
            ),
        )
        object.__setattr__(
            self,
            "decision_id",
            _normalize_optional_identity(self.decision_id, "decision_id", "td_"),
        )
        object.__setattr__(
            self,
            "operation_id",
            _normalize_optional_identity(self.operation_id, "operation_id", "po_"),
        )
        if self.failure_class is not None:
            object.__setattr__(
                self,
                "failure_class",
                _require_text(self.failure_class, "failure_class"),
            )
        if self.reason_code is not None:
            object.__setattr__(
                self,
                "reason_code",
                _require_text(self.reason_code, "reason_code"),
            )
        object.__setattr__(
            self,
            "duration_ms",
            _require_duration(self.duration_ms, "duration_ms"),
        )
        object.__setattr__(
            self, "counters", require_counters(self.counters, "counters")
        )


@dataclass(frozen=True)
class ReadinessComponent:
    """One inspected dependency with a controlled reason code.

    `critical` decides whether this component may drive the *aggregate* status, and
    therefore the HTTP status a load balancer reads. It is `True` by default,
    because a dependency that is silent about its own importance should be treated
    as one the instance cannot serve without.

    A background subsystem sets it `False`: it is still reported, with its own
    status and reason code, but a stalled background worker must not remove a
    perfectly healthy chat instance from rotation.
    """

    name: str
    status: ReadinessStatus
    reason_code: str
    details: Mapping[str, Any] = field(default_factory=dict)
    critical: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _require_text(self.name, "name"))
        object.__setattr__(
            self, "status", _coerce_enum(self.status, "status", ReadinessStatus)
        )
        object.__setattr__(
            self,
            "reason_code",
            _require_text(self.reason_code, "reason_code"),
        )
        object.__setattr__(self, "details", require_counters(self.details, "details"))

    def to_dict(self) -> dict[str, Any]:
        """Render the component as plain JSON-serializable data."""
        return {
            "name": self.name,
            "status": self.status.value,
            "reason_code": self.reason_code,
            "details": dict(self.details),
            "critical": self.critical,
        }


@dataclass(frozen=True)
class ReadinessSnapshot:
    """One on-demand readiness computation over local metadata."""

    status: ReadinessStatus
    checked_at: datetime
    components: tuple[ReadinessComponent, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "status", _coerce_enum(self.status, "status", ReadinessStatus)
        )
        object.__setattr__(
            self, "checked_at", _require_utc(self.checked_at, "checked_at")
        )
        components = tuple(self.components)
        for component in components:
            if not isinstance(component, ReadinessComponent):
                raise ObservabilityValidationError(
                    "Observability field 'components' must hold "
                    "ReadinessComponent entries."
                )
        object.__setattr__(self, "components", components)

    def to_dict(self) -> dict[str, Any]:
        """Render the snapshot as plain JSON-serializable data."""
        return {
            "status": self.status.value,
            "checked_at": self.checked_at.isoformat(),
            "components": [item.to_dict() for item in self.components],
        }


__all__ = [
    "EVENT_ID_PREFIX",
    "MAX_COUNTERS",
    "MAX_COUNTER_STRING_LENGTH",
    "REQUEST_ID_PREFIX",
    "EventComponent",
    "EventName",
    "EventResult",
    "EventSeverity",
    "ObservabilityValidationError",
    "OperationalEvent",
    "ReadinessComponent",
    "ReadinessSnapshot",
    "ReadinessStatus",
    "generate_event_id",
    "generate_request_id",
    "require_counters",
]
