"""Structured JSON event logging for milestone R8.

`emit_event` is the single doorway from product code to operational logs:
it binds the current request id, validates the closed field vocabulary,
redacts before serialization, and writes one JSON record. Unknown fields
raise instead of logging, so a new payload shape is a deliberate contract
decision. This module never imports product-domain modules.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from backend.observability.context import current_request_id
from backend.observability.models import (
    EventComponent,
    EventName,
    EventResult,
    EventSeverity,
    ObservabilityValidationError,
    OperationalEvent,
    generate_event_id,
)
from backend.observability.redaction import sanitize_event_fields

logger = logging.getLogger("travel_agent_observability")

_EVENT_DATA_FIELDS = frozenset(
    {
        "request_id",
        "workspace_id",
        "conversation_id",
        "message_id",
        "memory_id",
        "itinerary_version_id",
        "decision_id",
        "operation_id",
        "failure_class",
        "reason_code",
        "duration_ms",
        "counters",
    }
)

_SEVERITY_BY_RESULT = {
    EventResult.SUCCESS: EventSeverity.INFO,
    EventResult.FAILURE: EventSeverity.ERROR,
    EventResult.DEGRADED: EventSeverity.WARNING,
    EventResult.SKIPPED: EventSeverity.INFO,
}

_LEVEL_BY_SEVERITY = {
    EventSeverity.INFO: logging.INFO,
    EventSeverity.WARNING: logging.WARNING,
    EventSeverity.ERROR: logging.ERROR,
}


def emit_event(
    event_name: EventName | str,
    component: EventComponent | str,
    result: EventResult | str,
    severity: EventSeverity | str | None = None,
    **fields: Any,
) -> OperationalEvent:
    """Validate, redact, and log one structured operational event.

    `request_id` defaults to the active request context. Every other
    keyword must name an `OperationalEvent` data field; anything else
    raises before anything is logged. Returns the validated event so
    callers and tests can inspect identifiers without parsing logs.
    """
    unknown = sorted(set(fields) - _EVENT_DATA_FIELDS)
    if unknown:
        raise ObservabilityValidationError(
            "Observability event fields are closed; unknown fields: "
            + ", ".join(unknown)
        )
    resolved_result = result if isinstance(result, EventResult) else EventResult(result)
    resolved_severity = (
        severity
        if isinstance(severity, EventSeverity)
        else (
            EventSeverity(severity)
            if severity is not None
            else _SEVERITY_BY_RESULT[resolved_result]
        )
    )
    payload_fields = dict(fields)
    if payload_fields.get("request_id") is None:
        context_id = current_request_id()
        if context_id is not None:
            payload_fields["request_id"] = context_id
    event = OperationalEvent(
        event_id=generate_event_id(),
        timestamp=datetime.now(timezone.utc),
        event_name=event_name,
        component=component,
        severity=resolved_severity,
        result=resolved_result,
        **payload_fields,  # type: ignore[arg-type]
    )
    record = {
        "event_id": event.event_id,
        "timestamp": event.timestamp.isoformat(),
        "event_name": event.event_name.value,
        "component": event.component.value,
        "severity": event.severity.value,
        "result": event.result.value,
        "request_id": event.request_id,
        "workspace_id": event.workspace_id,
        "conversation_id": event.conversation_id,
        "message_id": event.message_id,
        "memory_id": event.memory_id,
        "itinerary_version_id": event.itinerary_version_id,
        "decision_id": event.decision_id,
        "operation_id": event.operation_id,
        "failure_class": event.failure_class,
        "reason_code": event.reason_code,
        "duration_ms": event.duration_ms,
        "counters": event.counters,
    }
    logger.log(
        _LEVEL_BY_SEVERITY[event.severity],
        "%s",
        json.dumps(sanitize_event_fields(record), ensure_ascii=False),
    )
    return event
