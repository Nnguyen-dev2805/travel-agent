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


def test_failure_class_must_be_an_exception_class_identifier():
    """`failure_class` names an exception class, never a message.

    The field is logged verbatim, so anything accepted here reaches the log. The
    shape admits an identifier only: no spaces, no punctuation, at most 64
    characters.
    """
    assert _event(failure_class="ProviderTimeoutError").failure_class == (
        "ProviderTimeoutError"
    )
    assert _event(failure_class="_PrivateError").failure_class == "_PrivateError"
    assert _event(failure_class="a" * 64).failure_class == "a" * 64

    for rejected in (
        "",
        "not found",
        "Validation Failed",
        "has-dash",
        "1StartsWithDigit",
        "a" * 65,
        "RuntimeError\n",
        "user said: my passport number is X1234567",
    ):
        with pytest.raises(ObservabilityValidationError):
            _event(failure_class=rejected)


def test_reason_code_must_be_a_bounded_machine_code():
    """`reason_code` is a lower snake-case machine code, not a sentence."""
    assert _event(reason_code="provider_timeout").reason_code == "provider_timeout"
    assert _event(reason_code="a").reason_code == "a"
    assert _event(reason_code="a" * 64).reason_code == "a" * 64

    for rejected in (
        "",
        "Validation",
        "Validation Failed",
        "has-dash",
        "1bad",
        "a" * 65,
        "ok\n",
        "user said hello",
    ):
        with pytest.raises(ObservabilityValidationError):
            _event(reason_code=rejected)


def test_the_shape_rule_cannot_police_domain_literals():
    """Documented limitation: a snake-case domain outcome passes the shape.

    `conversation_not_found` is a legitimate *shape* but the wrong *label* for
    `failure_class`. The rule exists to keep content out, not to distinguish an
    exception class from a domain outcome — that distinction is made at the
    call sites, so a reader must not expect the validator to enforce it.
    """
    assert _event(failure_class="conversation_not_found").failure_class == (
        "conversation_not_found"
    )


def test_shape_rejection_does_not_echo_the_rejected_value():
    """A rejected value must not travel back out through the error message.

    The field is shape-checked precisely because it can carry content, so
    repeating the value in the exception would recreate the leak the rule closes.
    """
    secret = "user said: my passport number is X1234567"

    with pytest.raises(ObservabilityValidationError) as reason_error:
        _event(reason_code=secret)
    with pytest.raises(ObservabilityValidationError) as class_error:
        _event(failure_class=secret)

    assert secret not in str(reason_error.value)
    assert secret not in str(class_error.value)


def test_the_shape_rule_does_not_govern_readiness_reason_codes():
    """The rule is scoped to the `OperationalEvent` boundary, not to readiness.

    `ReadinessComponent.reason_code` shares `_require_text` with the event fields
    but is its own vocabulary. Pinning the boundary here is what stops a later
    refactor from moving the validator into the shared helper and silently
    constraining readiness.
    """
    component = ReadinessComponent(
        name="app",
        status=ReadinessStatus.READY,
        reason_code="Readiness Code",
    )

    assert component.reason_code == "Readiness Code"
