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


@pytest.mark.parametrize(
    "secret_key",
    [
        "access_token",
        "refresh_token",
        "session_id",
        "client_secret",
        "id_token",
        "x-api-key",
        "x_api_key",
        "xApiKey",
        "XApiKey",
        "XAPIKey",
        "X-API-KEY",
        "APIKey",
        "AccessToken",
        "ACCESS_TOKEN",
        "RefreshToken",
        "SessionId",
    ],
)
def test_one_secret_key_is_redacted_in_every_spelling(secret_key):
    """The same logical key must redact however the caller spelled it.

    A secret field name is a qualifier plus a secret noun, and callers write the
    pair as `x_api_key`, `x-api-key`, `xApiKey`, `XApiKey` or `XAPIKey`. Matching
    only some spellings is a privacy bypass with a hole shaped like a style
    choice — worse than no rule, because the rule looks like it works.

    `counters` is where this bites: it is the only open mapping in the payload, so
    it is the only place a caller-chosen key reaches the log.
    """
    cleaned = sanitize_event_fields({"counters": {secret_key: "NEVER_LOG_SENTINEL"}})

    assert cleaned["counters"] == {secret_key: "[REDACTED]"}


def test_key_normalization_does_not_redact_safe_diagnostic_keys():
    """Token equality, not substring matching, is what prevents over-redaction.

    A substring test on `auth` would redact `author`; whole-token comparison does
    not. The keys here are the ones the emission boundary actually carries, the
    counter sets the runtime emits, and the near-misses a widened rule would
    plausibly swallow. Split across two payloads because `counters` is bounded to
    16 entries.
    """
    runtime_keys = {
        "author": "someone",
        "method": "GET",
        "path": "/api/v1/chat",
        "status_code": 200,
        "writes": 2,
        "citations": 3,
        "memory_selected": 0,
        "persisted": True,
        "components": 6,
        "request_id": "rq_" + "a" * 32,
    }
    near_misses = {
        "authentication_mode": "bearer",
        "api_version": "v1",
        "secretary": "someone",
        "tokens_used": 4,
        "tokenizer": "bge-m3",
        "keynote": "opening",
        "monkey": "patch",
        "access_level": "read",
        "sessionization": "off",
    }

    assert sanitize_event_fields({"counters": runtime_keys})["counters"] == runtime_keys
    assert sanitize_event_fields({"counters": near_misses})["counters"] == near_misses


def test_only_secret_like_classification_is_normalized():
    """`message_id` is an identifier; `message` is content. Only one is narrowed.

    Normalizing the forbidden and content sets as well would redact every
    governed identifier whose last token appears in them — `message_id` would
    disappear from every event — so those two sets keep exact matching.
    """
    cleaned = sanitize_event_fields(
        {
            "message_id": "ms_probe",
            "counters": {"message": "NEVER_LOG_SENTINEL", "message_id": "ms_probe"},
        }
    )

    assert cleaned["message_id"] == "ms_probe"
    assert cleaned["counters"]["message"] == "[REDACTED]"
    assert cleaned["counters"]["message_id"] == "ms_probe"
