"""Unit tests for the R8 structured event logger.

Tests assert one JSON log record per emission, unsafe-key rejection, and
failure-class logging without raw exception text. No test touches a
database, a model provider, Chroma, or the network.
"""

import json
import logging
from pathlib import Path

import pytest

from backend.observability import events
from backend.observability.context import reset_request_id, set_request_id
from backend.observability.models import (
    EventComponent,
    EventName,
    EventResult,
    EventSeverity,
    ObservabilityValidationError,
)


@pytest.fixture
def request_scope():
    token = set_request_id("rq_" + "b" * 32)
    yield "rq_" + "b" * 32
    reset_request_id(token)


def test_emit_event_writes_one_json_record(caplog, request_scope):
    with caplog.at_level(logging.INFO, logger="travel_agent_observability"):
        event = events.emit_event(
            EventName.CHAT_TURN_COMPLETED,
            EventComponent.CHAT,
            EventResult.SUCCESS,
            conversation_id="cv_probe",
            duration_ms=12,
            counters={"persisted": 2},
        )

    assert len(caplog.records) == 1
    payload = json.loads(caplog.records[0].message)
    assert payload["event_name"] == "chat.turn.completed"
    assert payload["component"] == "chat"
    assert payload["severity"] == "info"
    assert payload["result"] == "success"
    assert payload["request_id"] == request_scope
    assert payload["conversation_id"] == "cv_probe"
    assert payload["event_id"].startswith("ev_")
    assert payload["counters"] == {"persisted": 2}
    assert event.event_id == payload["event_id"]


def test_emit_event_rejects_unsafe_keys_before_logging(caplog):
    with caplog.at_level(logging.INFO, logger="travel_agent_observability"):
        with pytest.raises(ObservabilityValidationError):
            events.emit_event(
                EventName.CHAT_TURN_COMPLETED,
                EventComponent.CHAT,
                EventResult.SUCCESS,
                prompt="NEVER_LOG_PROMPT_SENTINEL",
            )

    assert caplog.records == []


def test_emit_event_records_failure_class_without_raw_text(caplog):
    with caplog.at_level(logging.INFO, logger="travel_agent_observability"):
        events.emit_event(
            EventName.MODEL_CALL_FAILED,
            EventComponent.MODEL_PROVIDER,
            EventResult.FAILURE,
            failure_class="ProviderTimeoutError",
            reason_code="provider_timeout",
        )

    payload = json.loads(caplog.records[0].message)
    assert payload["severity"] == "error"
    assert payload["failure_class"] == "ProviderTimeoutError"
    assert "Traceback" not in caplog.text
    assert "NEVER_LOG" not in caplog.text


def test_emit_event_rejects_unknown_fields(caplog):
    with caplog.at_level(logging.INFO, logger="travel_agent_observability"):
        with pytest.raises(ObservabilityValidationError):
            events.emit_event(
                EventName.API_REQUEST_COMPLETED,
                EventComponent.API,
                EventResult.SUCCESS,
                user_message="NEVER_LOG_USER_MESSAGE",
            )

    assert caplog.records == []


def test_explicit_request_id_wins_over_context(caplog):
    with caplog.at_level(logging.INFO, logger="travel_agent_observability"):
        events.emit_event(
            EventName.OPS_READINESS_COMPLETED,
            EventComponent.OPS,
            EventResult.SUCCESS,
            request_id="rq_" + "c" * 32,
        )

    payload = json.loads(caplog.records[0].message)
    assert payload["request_id"] == "rq_" + "c" * 32


def test_emit_event_rejects_content_bearing_codes_before_logging(caplog):
    """A rejected code must leave no record behind and must not be echoed back.

    The boundary validates at construction, before `logger.log`, so a rejected
    value neither reaches the log nor travels out through the exception — which
    matters because the value is rejected precisely for being able to carry
    content.
    """
    secret = "user said: my passport number is X1234567"

    with caplog.at_level(logging.INFO, logger="travel_agent_observability"):
        with pytest.raises(ObservabilityValidationError) as class_error:
            events.emit_event(
                EventName.MODEL_CALL_FAILED,
                EventComponent.MODEL_PROVIDER,
                EventResult.FAILURE,
                failure_class=secret,
            )
        with pytest.raises(ObservabilityValidationError) as reason_error:
            events.emit_event(
                EventName.MODEL_CALL_FAILED,
                EventComponent.MODEL_PROVIDER,
                EventResult.FAILURE,
                reason_code=secret,
            )

    assert caplog.records == []
    assert secret not in str(class_error.value)
    assert secret not in str(reason_error.value)


@pytest.mark.parametrize(
    ("code_field", "value"),
    [
        ("failure_class", "RuntimeError"),
        ("failure_class", "ValueError"),
        ("failure_class", "TimeoutError"),
        ("reason_code", "ok"),
        ("reason_code", "http_client_error"),
        ("reason_code", "http_server_error"),
        ("reason_code", "unhandled_exception"),
        ("reason_code", "validation_error"),
        ("reason_code", "generation_failed"),
        ("reason_code", "ready"),
        ("reason_code", "degraded"),
        ("reason_code", "not_ready"),
        ("reason_code", "unknown"),
    ],
)
def test_emit_event_accepts_every_governed_code_the_runtime_emits(
    caplog, code_field, value
):
    """The new shapes must not narrow a value the runtime already emits.

    Parametrized over the values the production call sites actually pass — the
    API request tail, the model-call failures, the RAG generation failure and
    every readiness status — so a shape that is too tight fails here rather than
    in production.
    """
    with caplog.at_level(logging.INFO, logger="travel_agent_observability"):
        events.emit_event(
            EventName.API_REQUEST_COMPLETED,
            EventComponent.API,
            EventResult.SUCCESS,
            **{code_field: value},
        )

    payload = json.loads(caplog.records[0].message)
    assert payload[code_field] == value


def test_api_routes_label_a_domain_outcome_as_reason_code():
    """A domain outcome is not an exception class, and the label must say so.

    The `OperationalEvent` boundary cannot police this — `conversation_not_found`
    satisfies both shapes — so the call sites are the only control. Pinned
    statically, the way the readiness probe pins its own source, because a live
    assertion would need a database to reach these error paths.
    """
    route_dir = Path(events.__file__).resolve().parent.parent / "app" / "api"
    offenders: list[str] = []
    for path in sorted(route_dir.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for outcome in ("validation", "not_found", "conversation_not_found"):
            if f"failure_class={outcome}" in source:
                offenders.append(f"{path.name}: failure_class={outcome}")

    assert not offenders, offenders


def test_a_secret_keyed_counter_is_redacted_end_to_end(caplog):
    """Pin the leak at the doorway, where it actually happened.

    Top-level fields are bounded by the closed allowlist, which raises on
    anything unexpected; `counters` is an open mapping, so it is the only place a
    caller-chosen key reaches the log.
    """
    with caplog.at_level(logging.INFO, logger="travel_agent_observability"):
        events.emit_event(
            EventName.CHAT_TURN_COMPLETED,
            EventComponent.CHAT,
            EventResult.SUCCESS,
            counters={"access_token": "NEVER_LOG_SENTINEL"},
        )

    payload = json.loads(caplog.records[0].message)
    assert payload["counters"] == {"access_token": "[REDACTED]"}
    assert "NEVER_LOG_SENTINEL" not in caplog.text
