"""Deterministic prohibited-content detection.

Runs before any candidate exists: secret, payment, and authentication
material is rejected and redacted up front, so no raw prohibited value
can reach a candidate, an embedding, or an index. Findings carry the
redacted text only, never the raw match. This module never logs and
depends on the Python standard library only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

DETECTOR_VERSION = "prohibited-detector-v2"
REDACTED_MARK = "[redacted]"


class ProhibitedKind(str, Enum):
    """Closed categories of content with no memory business purpose."""

    SECRET = "secret"
    PAYMENT = "payment"
    AUTH = "auth"


_SECRET_PATTERNS = (
    re.compile(r"sk-proj-[A-Za-z0-9_-]+"),
    re.compile(r"sk-(?:test|live)-[A-Za-z0-9]+"),
    re.compile(r"ghp_[A-Za-z0-9]+"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?:api[_-]?key|token|secret)\s*[:=]\s*\S+", re.IGNORECASE),
)

_PEM_BLOCK_PATTERN = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)
_PEM_BEGIN_PATTERN = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*", re.DOTALL)
_PEM_END_PATTERN = re.compile(
    r"^.*-----END [A-Z0-9 ]*PRIVATE KEY-----.*$", re.MULTILINE
)

_AUTH_PATTERNS = (
    _PEM_BLOCK_PATTERN,
    _PEM_BEGIN_PATTERN,
    _PEM_END_PATTERN,
    re.compile(r"(?:password|passwd|mật khẩu)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\botp\s*[:=]?\s*\d{6,8}\b", re.IGNORECASE),
    re.compile(r"recovery[_-]?code\s*[:=]?\s*\S+", re.IGNORECASE),
    re.compile(r"\bpin\s*[:=]\s*\d{4,8}", re.IGNORECASE),
)

_PAYMENT_PATTERNS = (
    re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{3,4}\b"),
    re.compile(r"\bcvv\s*[:=]?\s*\d{3,4}\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class ProhibitedFinding:
    """One detection outcome carrying redacted text only."""

    kind: ProhibitedKind | str
    redacted_text: str
    detector_version: str = DETECTOR_VERSION

    def __post_init__(self) -> None:
        if isinstance(self.kind, ProhibitedKind):
            pass
        elif isinstance(self.kind, str):
            try:
                object.__setattr__(self, "kind", ProhibitedKind(self.kind))
            except ValueError as error:
                allowed = ", ".join(member.value for member in ProhibitedKind)
                raise ValueError(
                    f"Unknown kind value. Allowed values: {allowed}."
                ) from error
        else:
            raise ValueError("Field 'kind' must be a ProhibitedKind value.")
        if not isinstance(self.redacted_text, str):
            raise ValueError("Field 'redacted_text' must be a string.")
        if (
            not isinstance(self.detector_version, str)
            or not self.detector_version.strip()
        ):
            raise ValueError("Field 'detector_version' must be a non-blank string.")


def _redact_all(text: str) -> str:
    redacted = text
    for group in (_SECRET_PATTERNS, _AUTH_PATTERNS, _PAYMENT_PATTERNS):
        for pattern in group:
            redacted = pattern.sub(REDACTED_MARK, redacted)
    return redacted


def detect_prohibited_content(text: Any) -> ProhibitedFinding | None:
    """Detect prohibited material and return a redacted finding, if any.

    Categories are checked in secret, authentication, then payment
    order; every match across all categories is redacted in the
    returned text. Non-string or blank input yields no finding.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    if any(pattern.search(text) for pattern in _SECRET_PATTERNS):
        kind = ProhibitedKind.SECRET
    elif any(pattern.search(text) for pattern in _AUTH_PATTERNS):
        kind = ProhibitedKind.AUTH
    elif any(pattern.search(text) for pattern in _PAYMENT_PATTERNS):
        kind = ProhibitedKind.PAYMENT
    else:
        return None
    return ProhibitedFinding(kind=kind, redacted_text=_redact_all(text))
