"""Local privacy-safe observability for milestone R8.

This package owns request correlation, structured event contracts,
redaction, readiness probes, and operational evaluation. Low-level modules
here use only the standard library so product code can depend on them
without cycles; readiness and evaluation arrive in later R8 tasks.
"""

from backend.observability.models import (
    EVENT_ID_PREFIX,
    REQUEST_ID_PREFIX,
    EventComponent,
    EventName,
    EventResult,
    EventSeverity,
    ObservabilityValidationError,
    OperationalEvent,
    ReadinessComponent,
    ReadinessSnapshot,
    ReadinessStatus,
    generate_event_id,
    generate_request_id,
)
from backend.observability.context import (
    current_request_id,
    new_request_id,
    reset_request_id,
    set_request_id,
)
from backend.observability.events import emit_event
from backend.observability.redaction import (
    PATH_MARKER,
    REDACTED,
    sanitize_event_fields,
)

__all__ = [
    "EVENT_ID_PREFIX",
    "PATH_MARKER",
    "REDACTED",
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
    "current_request_id",
    "emit_event",
    "generate_event_id",
    "generate_request_id",
    "new_request_id",
    "reset_request_id",
    "sanitize_event_fields",
    "set_request_id",
]
