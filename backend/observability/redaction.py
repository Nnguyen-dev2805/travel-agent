"""Safe-field validation and redaction for R8 operational evidence.

`sanitize_event_fields` is the dynamic boundary behind the static
`OperationalEvent` contract: it rejects forbidden content keys before
logging and redacts token-like, path-like, and content-like values. It
uses only the standard library and never imports product-domain modules.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

from backend.observability.models import (
    ObservabilityValidationError,
    require_counters,
)

REDACTED = "[REDACTED]"
PATH_MARKER = "[PATH]"

FORBIDDEN_KEYS = frozenset(
    {
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
    }
)
"""Content keys that must never reach logs or reports, in any letter case."""

SECRET_LIKE_KEYS = frozenset(
    {
        "token",
        "api_key",
        "apikey",
        "secret",
        "password",
        "credential",
        "credentials",
        "github_token",
        "auth",
        "authorization",
    }
)
"""Key names whose values are secrets regardless of shape."""

CONTENT_LIKE_KEYS = frozenset(
    {
        "text",
        "statement",
        "summary",
        "description",
        "body",
        "answer",
        "response",
        "output",
        "input",
    }
)
"""Key names that carry free-form content rather than identifiers."""

_TOKEN_PATTERNS = (
    re.compile(r"gh[pousr]_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9\-_]+"),
    re.compile(r"xox[bpas]-[A-Za-z0-9\-_]+"),
    re.compile(r"AKIA[0-9A-Z]+"),
    re.compile(r"-----BEGIN [A-Z ]+-----"),
)

_PATH_PATTERN = re.compile(r"^(~?/[^ \n]*|[A-Za-z]:\\[^ \n]*)")

_SENSITIVE_ROOTS = (
    "/tmp/",
    "/var/",
    "/etc/",
    "/home/",
    "/Users/",
    "/data/",
    "/app/",
    "/srv/",
    "/opt/",
    "/root/",
    "~/",
)


def _looks_like_token(value: str) -> bool:
    return any(pattern.search(value) for pattern in _TOKEN_PATTERNS)


def _looks_like_path(value: str) -> bool:
    """Decide whether a string is a filesystem path rather than a route.

    Route paths such as `/api/v1/chat` are governed diagnostic evidence
    and must survive; they carry identifiers, never file locations. A
    filesystem path almost always names a file (a dot in the last
    segment), a sensitive root, or a Windows drive, so only those shapes
    redact.
    """
    text = value.strip()
    if "://" in text:
        return False
    if re.match(r"^[A-Za-z]:\\", text):
        return True
    if _PATH_PATTERN.match(text) is None:
        return False
    last = text.rsplit("/", 1)[-1]
    if "." in last:
        return True
    return text.startswith(_SENSITIVE_ROOTS)


def _redact_scalar(key: str, value: Any) -> Any:
    lowered = key.lower()
    if lowered in FORBIDDEN_KEYS:
        return REDACTED
    if lowered in SECRET_LIKE_KEYS or lowered in CONTENT_LIKE_KEYS:
        return REDACTED
    if not isinstance(value, str):
        return value
    if _looks_like_token(value):
        return REDACTED
    if _looks_like_path(value):
        return PATH_MARKER
    return value


def sanitize_event_fields(fields: Mapping[str, object]) -> dict[str, object]:
    """Validate and redact one event payload mapping.

    Forbidden content keys raise before anything is logged. Secret-like
    and content-like keys redact regardless of value shape, while other
    string values redact only when they match token-like or path-like
    patterns, so safe ids, reason codes, and counters survive unchanged.

    The `counters` mapping is validated and then redacted entry by entry
    with the same key rules: a forbidden nested key redacts instead of
    raising, because emission must never break the request it observes.
    The result holds plain JSON-serializable data only.

    Raises:
        ObservabilityValidationError: A forbidden key is present, or the
            payload holds non-scalar values that could smuggle content.
    """
    if not isinstance(fields, Mapping):
        raise ObservabilityValidationError(
            "Observability event fields must be a mapping."
        )
    cleaned: dict[str, object] = {}
    for key, value in fields.items():
        if not isinstance(key, str) or not key.strip():
            raise ObservabilityValidationError(
                "Observability event field names must be non-empty strings."
            )
        if key.lower() in FORBIDDEN_KEYS:
            raise ObservabilityValidationError(
                f"Observability event field '{key}' must never be logged."
            )
        if key == "counters":
            validated = require_counters(value, "counters")
            cleaned[key] = {
                entry_key: _redact_scalar(entry_key, entry_value)
                for entry_key, entry_value in validated.items()
            }
            continue
        if isinstance(value, Mapping) or (isinstance(value, (list, tuple, set))):
            raise ObservabilityValidationError(
                f"Observability event field '{key}' must be a scalar value."
            )
        cleaned[key] = _redact_scalar(key, value)
    json.dumps(cleaned)
    return cleaned
