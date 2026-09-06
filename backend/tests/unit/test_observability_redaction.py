"""Unit tests for R8 redaction and unsafe-field rejection.

Tests pin the forbidden key set and token-like, path-like, and
content-like redaction. No test uses real secrets, real user data, or the
network.
"""

import pytest

from backend.observability.models import ObservabilityValidationError
from backend.observability.redaction import sanitize_event_fields


def test_github_token_like_values_redact():
    cleaned = sanitize_event_fields(
        {"model": "gpt-4o-mini", "credential": "ghp_NEVER_LOG_TOKEN_VALUE"}
    )

    assert cleaned["model"] == "gpt-4o-mini"
    assert cleaned["credential"] == "[REDACTED]"


def test_secret_like_keys_redact_regardless_of_value():
    cleaned = sanitize_event_fields(
        {"github_token": "present", "api_key": "present", "password": "x"}
    )

    assert cleaned == {
        "github_token": "[REDACTED]",
        "api_key": "[REDACTED]",
        "password": "[REDACTED]",
    }


def test_absolute_paths_redact_as_path():
    cleaned = sanitize_event_fields({"db": "/Users/example/project/data/app.sqlite3"})

    assert cleaned["db"] == "[PATH]"


def test_forbidden_content_keys_are_rejected():
    for key in (
        "message",
        "prompt",
        "reply",
        "content",
        "candidate_text",
        "itinerary_text",
        "decision_statement",
        "provider_response",
        "stack_trace",
        "raw_exception",
    ):
        with pytest.raises(ObservabilityValidationError):
            sanitize_event_fields({key: "NEVER_LOG_CONTENT_SENTINEL"})


def test_content_like_keys_redact():
    cleaned = sanitize_event_fields(
        {"statement": "NEVER_LOG_DECISION_SENTINEL", "answer": "some text"}
    )

    assert cleaned["statement"] == "[REDACTED]"
    assert cleaned["answer"] == "[REDACTED]"


def test_counters_redact_forbidden_secret_and_path_values():
    cleaned = sanitize_event_fields(
        {
            "counters": {
                "message": "SECRET_USER_TEXT",
                "token": "ghp_REALTOKENVALUE123",
                "path": "/Users/me/secret/app.sqlite3",
            }
        }
    )

    assert cleaned["counters"] == {
        "message": "[REDACTED]",
        "token": "[REDACTED]",
        "path": "[PATH]",
    }


def test_counters_keep_route_paths_and_diagnostic_scalars():
    cleaned = sanitize_event_fields(
        {
            "counters": {
                "method": "GET",
                "path": "/api/v1/chat",
                "status_code": 200,
                "writes": 2,
            }
        }
    )

    assert cleaned["counters"] == {
        "method": "GET",
        "path": "/api/v1/chat",
        "status_code": 200,
        "writes": 2,
    }


def test_safe_ids_reason_and_counters_survive():
    fields = {
        "request_id": "rq_" + "a" * 32,
        "workspace_id": "tw_probe",
        "reason_code": "credential_missing",
        "failure_class": "PlannerStorageError",
        "duration_ms": 3,
        "counters": {"writes": 2},
    }

    assert sanitize_event_fields(fields) == fields


def test_result_is_json_serializable_plain_data():
    cleaned = sanitize_event_fields({"counters": {"writes": 2}, "duration_ms": 1.5})

    import json

    assert json.loads(json.dumps(cleaned)) == cleaned
