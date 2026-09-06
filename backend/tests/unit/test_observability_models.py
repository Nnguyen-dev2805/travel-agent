"""Unit tests for R8 observability contracts.

Tests pin id formats, severity/result/readiness vocabularies, duration and
counter bounds. No test touches a database, a model provider, Chroma, or
the network.
"""

from datetime import datetime, timezone

import pytest

from backend.observability.models import (
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

MOMENT = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)


def _event(**overrides):
    payload = {
        "event_id": generate_event_id(),
        "timestamp": MOMENT,
        "event_name": EventName.API_REQUEST_COMPLETED,
        "component": EventComponent.API,
        "severity": EventSeverity.INFO,
        "result": EventResult.SUCCESS,
    }
    payload.update(overrides)
    return OperationalEvent(**payload)


def test_request_ids_use_rq_prefix_with_32_hex():
    request_id = generate_request_id()

    assert request_id.startswith("rq_")
    assert len(request_id) == 3 + 32
    int(request_id[3:], 16)
    assert len({generate_request_id() for _ in range(10)}) == 10


def test_event_ids_use_ev_prefix_with_32_hex():
    event_id = generate_event_id()

    assert event_id.startswith("ev_")
    assert len(event_id) == 3 + 32
    int(event_id[3:], 16)


def test_event_severity_vocabulary():
    assert {item.value for item in EventSeverity} == {"info", "warning", "error"}
    assert _event(severity="error").severity is EventSeverity.ERROR
    with pytest.raises(ObservabilityValidationError):
        _event(severity="critical")


def test_event_result_vocabulary():
    assert {item.value for item in EventResult} == {
        "success",
        "failure",
        "degraded",
        "skipped",
    }
    assert _event(result="degraded").result is EventResult.DEGRADED
    with pytest.raises(ObservabilityValidationError):
        _event(result="unknown-outcome")


def test_event_name_and_component_vocabularies():
    assert _event(event_name="chat.turn.completed").event_name is (
        EventName.CHAT_TURN_COMPLETED
    )
    with pytest.raises(ObservabilityValidationError):
        _event(event_name="chat.turn.feels-good")
    assert _event(component="planner").component is EventComponent.PLANNER
    with pytest.raises(ObservabilityValidationError):
        _event(component="telemetry-vendor")


def test_event_timestamps_must_be_timezone_aware_utc():
    assert _event().timestamp.tzinfo is not None
    with pytest.raises(ObservabilityValidationError):
        _event(timestamp=datetime(2026, 9, 5, 12, 0, 0))


def test_duration_ms_cannot_be_negative():
    assert _event(duration_ms=12.5).duration_ms == 12.5
    assert _event(duration_ms=None).duration_ms is None
    with pytest.raises(ObservabilityValidationError):
        _event(duration_ms=-1)
    with pytest.raises(ObservabilityValidationError):
        _event(duration_ms=True)


def test_counters_accept_only_bounded_scalars():
    event = _event(counters={"accepted": 2, "ratio": 0.5, "flag": True})
    assert event.counters == {"accepted": 2, "ratio": 0.5, "flag": True}
    with pytest.raises(ObservabilityValidationError):
        _event(counters={"nested": {"a": 1}})
    with pytest.raises(ObservabilityValidationError):
        _event(counters={"items": [1, 2]})
    with pytest.raises(ObservabilityValidationError):
        _event(counters={f"k{i}": i for i in range(17)})


def test_request_id_must_carry_governed_prefix():
    assert _event(request_id=generate_request_id()).request_id.startswith("rq_")
    with pytest.raises(ObservabilityValidationError):
        _event(request_id="caller-supplied-id")


def test_readiness_status_vocabulary():
    assert {item.value for item in ReadinessStatus} == {
        "ready",
        "degraded",
        "not_ready",
        "unknown",
    }


def test_readiness_snapshot_holds_safe_components():
    snapshot = ReadinessSnapshot(
        status=ReadinessStatus.DEGRADED,
        checked_at=MOMENT,
        components=(
            ReadinessComponent(
                name="model_provider",
                status=ReadinessStatus.NOT_READY,
                reason_code="credential_missing",
                details={"model": "gpt-4o-mini"},
            ),
        ),
    )

    assert snapshot.status is ReadinessStatus.DEGRADED
    assert snapshot.components[0].reason_code == "credential_missing"
    with pytest.raises(ObservabilityValidationError):
        ReadinessComponent(
            name="model_provider",
            status="maybe",
            reason_code="credential_missing",
            details={},
        )
