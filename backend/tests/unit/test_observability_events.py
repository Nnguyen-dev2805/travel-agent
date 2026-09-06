"""Unit tests for the R8 structured event logger.

Tests assert one JSON log record per emission, unsafe-key rejection, and
failure-class logging without raw exception text. No test touches a
database, a model provider, Chroma, or the network.
"""

import json
import logging

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
