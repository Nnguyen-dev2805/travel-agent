"""Deterministic rule-based memory extraction for milestone R5.

The extractor is a pure text-to-draft function over governed fixture
phrases. It copies provenance and trace fields from the source message,
proposes scope, type, confidence, and sensitivity, and redacts secret-like
spans before they can reach a persisted candidate. It never assigns a
policy status: every draft leaves `status` and `reason` absent for
`MemoryPolicy` to decide. No model call, no storage, no network.

R5 uses this extractor because the milestone measures contracts, policy,
and evaluation harnessing, not model quality. A model-backed extractor
requires a separate approved design.
"""

from __future__ import annotations

import re
from typing import Protocol, Sequence, runtime_checkable

from backend.memory.models import (
    CANDIDATE_TEXT_MAX_LENGTH,
    EVIDENCE_SUMMARY_MAX_LENGTH,
    MemoryCandidateDraft,
    MemoryScope,
    MemorySourceMessage,
    MemoryType,
    SensitivityLabel,
)

EXTRACTOR_ID = "rule-based-v1"

_SECRET_PATTERNS = (
    re.compile(r"sk-(?:test|live)-[A-Za-z0-9]+", re.IGNORECASE),
    re.compile(
        r"(?:api[_ ]?key|password|mật khẩu|token)\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
)
_CORRECTION_MARKERS = ("thực ra", "sửa lại", "không phải", "actually", "correction")
_CONSTRAINT_MARKERS = (
    "ngân sách",
    "budget",
    "tối đa",
    "phải về trước",
    "deadline",
    "chỉ đi được",
)
_PROFILE_MARKERS = ("tôi tên là", "tôi sống ở", "my name is", "sinh năm")
_PREFERENCE_MARKERS = ("ăn chay", "thích", "prefer", "không thích", "dị ứng", "ghét")
_EPISODE_MARKERS = ("hôm nay tôi", "vừa mới", "today i")
_PERSONAL_MARKERS = ("dị ứng",) + _PROFILE_MARKERS


@runtime_checkable
class MemoryExtractor(Protocol):
    """Propose raw memory candidate drafts from eligible source messages."""

    def extract(
        self, messages: Sequence[MemorySourceMessage]
    ) -> tuple[MemoryCandidateDraft, ...]:
        """Return one draft per detected signal, or one `none` draft."""
        ...


def _mentions(text: str, markers: Sequence[str]) -> bool:
    return any(marker in text for marker in markers)


def _redact(text: str) -> str:
    """Replace secret-like spans with a fixed placeholder."""
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[redacted]", redacted)
    return redacted


def _normalize(message_content: str) -> str:
    return " ".join(message_content.split())


class RuleBasedMemoryExtractor:
    """Deterministic extractor over governed Vietnamese fixture phrases."""

    extractor_id = EXTRACTOR_ID

    def extract(
        self, messages: Sequence[MemorySourceMessage]
    ) -> tuple[MemoryCandidateDraft, ...]:
        """Extract drafts from each message, preserving input order."""
        drafts: list[MemoryCandidateDraft] = []
        for message in messages:
            drafts.extend(self._extract_one(message))
        return tuple(drafts)

    def _extract_one(self, message: MemorySourceMessage) -> list[MemoryCandidateDraft]:
        normalized = _normalize(message.content)
        lowered = normalized.lower()
        drafts = [
            draft
            for draft in (
                self._secret_draft(message, normalized),
                self._correction_draft(message, normalized, lowered),
                self._constraint_draft(message, normalized, lowered),
                self._profile_draft(message, normalized, lowered),
                self._preference_draft(message, normalized, lowered),
                self._episode_draft(message, normalized, lowered),
            )
            if draft is not None
        ]
        if drafts:
            return drafts
        return [
            MemoryCandidateDraft(
                source_message_id=message.message_id,
                conversation_id=message.conversation_id,
                workspace_id=message.workspace_id,
                source_sequence=message.sequence,
                role=message.role,
                source=message.source,
                trace_visibility=message.trace_visibility,
                proposed_scope=MemoryScope.NONE,
                proposed_type=MemoryType.NONE,
                confidence=1.0,
                sensitivity_label=SensitivityLabel.NONE,
                text="",
                evidence_summary="",
            )
        ]

    def _base(
        self,
        message: MemorySourceMessage,
        text: str,
        evidence: str,
        scope: MemoryScope,
        candidate_type: MemoryType,
        confidence: float,
        sensitivity: SensitivityLabel,
    ) -> MemoryCandidateDraft:
        return MemoryCandidateDraft(
            source_message_id=message.message_id,
            conversation_id=message.conversation_id,
            workspace_id=message.workspace_id,
            source_sequence=message.sequence,
            role=message.role,
            source=message.source,
            trace_visibility=message.trace_visibility,
            proposed_scope=scope,
            proposed_type=candidate_type,
            confidence=confidence,
            sensitivity_label=sensitivity,
            text=text[:CANDIDATE_TEXT_MAX_LENGTH],
            evidence_summary=evidence[:EVIDENCE_SUMMARY_MAX_LENGTH],
        )

    def _secret_draft(
        self, message: MemorySourceMessage, normalized: str
    ) -> MemoryCandidateDraft | None:
        if not any(pattern.search(normalized) for pattern in _SECRET_PATTERNS):
            return None
        redacted = _redact(normalized)
        return self._base(
            message,
            redacted,
            "secret-like pattern redacted",
            MemoryScope.USER,
            MemoryType.PROFILE_FACT,
            0.95,
            SensitivityLabel.SECRET,
        )

    def _correction_draft(
        self, message: MemorySourceMessage, normalized: str, lowered: str
    ) -> MemoryCandidateDraft | None:
        if not _mentions(lowered, _CORRECTION_MARKERS):
            return None
        return self._base(
            message,
            normalized,
            normalized,
            MemoryScope.USER,
            MemoryType.CORRECTION,
            0.85,
            SensitivityLabel.NONE,
        )

    def _constraint_draft(
        self, message: MemorySourceMessage, normalized: str, lowered: str
    ) -> MemoryCandidateDraft | None:
        if not _mentions(lowered, _CONSTRAINT_MARKERS):
            return None
        return self._base(
            message,
            normalized,
            normalized,
            MemoryScope.WORKSPACE,
            MemoryType.CONSTRAINT,
            0.85,
            SensitivityLabel.NONE,
        )

    def _profile_draft(
        self, message: MemorySourceMessage, normalized: str, lowered: str
    ) -> MemoryCandidateDraft | None:
        if not _mentions(lowered, _PROFILE_MARKERS):
            return None
        return self._base(
            message,
            normalized,
            normalized,
            MemoryScope.USER,
            MemoryType.PROFILE_FACT,
            0.8,
            SensitivityLabel.PERSONAL,
        )

    def _preference_draft(
        self, message: MemorySourceMessage, normalized: str, lowered: str
    ) -> MemoryCandidateDraft | None:
        if not _mentions(lowered, _PREFERENCE_MARKERS):
            return None
        sensitivity = (
            SensitivityLabel.PERSONAL
            if _mentions(lowered, _PERSONAL_MARKERS)
            else SensitivityLabel.NONE
        )
        return self._base(
            message,
            normalized,
            normalized,
            MemoryScope.USER,
            MemoryType.PREFERENCE,
            0.8,
            sensitivity,
        )

    def _episode_draft(
        self, message: MemorySourceMessage, normalized: str, lowered: str
    ) -> MemoryCandidateDraft | None:
        if not _mentions(lowered, _EPISODE_MARKERS):
            return None
        return self._base(
            message,
            normalized,
            normalized,
            MemoryScope.CONVERSATION,
            MemoryType.EPISODE,
            0.75,
            SensitivityLabel.NONE,
        )
