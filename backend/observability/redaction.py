"""Safe-field validation and redaction for R8 operational evidence.

`sanitize_event_fields` is the dynamic boundary behind the static
`OperationalEvent` contract: it rejects forbidden content keys before
logging and redacts token-like, path-like, and content-like values. It
uses only the standard library and never imports product-domain modules.

Secret-like field names are normalized before classification, because a
caller writes the same field as `access_token`, `access-token`,
`accessToken` or `Access_Token` and an exact-match set missed every one of
them. Forbidden and content keys keep exact matching: normalizing those
would redact governed identifiers such as `message_id`.
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
        "passwd",
        "credential",
        "credentials",
        "github_token",
        "auth",
        "authorization",
        "session",
        "bearer",
        "jwt",
        "cookie",
        "dsn",
        "privatekey",
        "accesskey",
    }
)
"""Marker vocabulary for secret-bearing field names.

An entry matches a key in one of three ways: as a whole token (`access_token` →
`token`), as the join of two adjacent tokens (`x-api-key` → `apikey`), or as the
key's suffix (`XAPIKey` → `apikey`, after the splitter leaves the acronym run
intact). Longer entries such as `github_token` are kept as vocabulary even though
`token` already covers them.

The joined forms (`privatekey`, `accesskey`) exist because the token splitter
separates `private_key` into two tokens; the adjacent-pair test is what matches
them. This is a vocabulary, not a regex catalogue: a new secret name is one word
here, not a new pattern.

Entries containing a separator (`api_key`, `github_token`) can never match
directly: the splitter emits `[a-z0-9]` tokens only, so no token, join or
flattened key ever contains `_`. They are kept as vocabulary documentation, and
`token` is what actually matches the keys they name.
"""

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

_KEY_SEPARATOR_PATTERN = re.compile(r"[^a-z0-9]+")
_CAMEL_HUMP_PATTERN = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _key_tokens(key: str) -> list[str]:
    """Split a field name into lowercase alphanumeric tokens.

    Separators (`_`, `-`, `.`, whitespace) and camelCase humps both start a new
    token, so `access_token`, `access-token`, `accessToken` and `Access_Token`
    all yield `['access', 'token']`.

    An acronym run is left intact: `XAPIKey` yields `['xapikey']` and `XApiKey`
    yields `['xapi', 'key']`, because splitting `XAPI` into `X` + `API` is not
    decidable without a dictionary. `_is_secret_like_key` covers that shape with
    its suffix test rather than pretending this splitter resolved it.
    """
    humped = _CAMEL_HUMP_PATTERN.sub(" ", key)
    return [token for token in _KEY_SEPARATOR_PATTERN.split(humped.lower()) if token]


def _is_secret_like_key(key: str) -> bool:
    """Decide whether a field name is secret-bearing, whatever its value shape.

    Three tests, because no single one covers the spellings a caller may choose:

    1. **Token equality** — `access_token`, `authorization`. Whole tokens are
       compared rather than searched, which is what keeps `author` from matching
       `auth`.
    2. **Adjacent-token join** — `x-api-key` splits into `['x', 'api', 'key']` and
       matches `apikey` only once the last two are joined. This also catches a
       marker in the middle, as in `private_key_hash`.
    3. **Suffix** — the separator-stripped key ends with a marker. A secret field
       name is a qualifier plus a secret noun, and the noun comes last, so this is
       what makes `XApiKey`, `XAPIKey` and `X-API-KEY` equivalent to `x_api_key`
       once the splitter has left the acronym run intact. `author` still does not
       match `auth`, because there `auth` is a prefix rather than a suffix.
       The trade is deliberate and asymmetric: a word that merely *ends* in a
       marker does match, so `unauth` and `forbearer` redact. Over-redacting a
       contrived word costs a diagnostic; under-redacting a key costs a secret.
    """
    tokens = _key_tokens(key)
    if any(token in SECRET_LIKE_KEYS for token in tokens):
        return True
    if any(
        "".join(tokens[index : index + 2]) in SECRET_LIKE_KEYS
        for index in range(len(tokens) - 1)
    ):
        return True
    flattened = "".join(tokens)
    return any(flattened.endswith(marker) for marker in SECRET_LIKE_KEYS)

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
    if lowered in CONTENT_LIKE_KEYS or _is_secret_like_key(key):
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
    keys redact regardless of value shape, and their names are normalized
    first so a separator or camelCase spelling cannot slip past. Content-like
    and forbidden keys keep exact matching, or every governed identifier
    ending in such a token (`message_id`) would vanish. Other string values
    redact only when they match token-like or path-like patterns, so safe
    ids, reason codes, and counters survive unchanged.

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
