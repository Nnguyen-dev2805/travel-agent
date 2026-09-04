"""Deterministic rule-based memory extraction for milestone R5.

The extractor is a pure text-to-draft function over governed fixture
phrases. It copies provenance and trace fields from the source message,
proposes scope, type, confidence, and sensitivity, and never assigns a
policy status: every draft leaves `status` and `reason` absent for
`MemoryPolicy` to decide. No model call, no storage, no network.

Two properties are load-bearing for memory safety:

1. **Redaction happens once at the source.** Secret-like spans are replaced
   before any draft is built, and a message that contains one marks every
   draft it produces as secret-sensitive. A co-occurring preference or
   constraint therefore cannot smuggle the raw secret into an accepted
   candidate under a clean label.
2. **Evidence summaries carry no message content.** Each draft's summary
   names the fired rule and its governed marker (a fixed vocabulary phrase,
   never user content), or the fixed secret placeholder. Full candidate text
   is redacted; summaries never echo the message.

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
    MemoryValidationError,
    SensitivityLabel,
)

EXTRACTOR_ID = "rule-based-v1"

SECRET_PATTERNS = (
    re.compile(r"sk-(?:test|live)-[A-Za-z0-9]+", re.IGNORECASE),
    re.compile(
        r"(?:api[_ ]?key|password|mật khẩu|token)\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
)
"""Secret-like shapes the extractor, policy tests, and evaluation gates share.

Evaluation detectors scan persisted candidate content with these patterns
instead of trusting the sensitivity label, so a mislabeled draft cannot
blind the hard gate.
"""

_SECRET_REDACTED = "[redacted]"
_SECRET_EVIDENCE = "secret-like pattern redacted"
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
_HEDGED_MARKERS = ("có lẽ", "chưa chắc", "không chắc", "maybe", "probably")
_CHAT_LOCAL_MARKERS = (
    "trong chat này",
    "trong cuộc trò chuyện này",
    "just this chat",
    "chỉ trong chat này",
)
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


def _first_hit(text: str, markers: Sequence[str]) -> str:
    """Return the first governed marker present in the text."""
    for marker in markers:
        if marker in text:
            return marker
    raise MemoryValidationError("No governed marker fired for this draft.")


def _redact_all(text: str) -> str:
    """Replace every secret-like span with a fixed placeholder."""
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(_SECRET_REDACTED, redacted)
    return redacted


def _contains_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


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
        secret_hit = _contains_secret(normalized)
        redacted = _redact_all(normalized)
        lowered = redacted.lower()
        # A secret anywhere in the message taints every draft from it, so a
        # co-occurring signal cannot launder the raw value under a clean
        # label. All downstream matching runs on redacted text.
        override = SensitivityLabel.SECRET if secret_hit else None
        drafts = [
            draft
            for draft in (
                self._secret_draft(message, redacted, secret_hit),
                self._correction_draft(message, redacted, lowered, override),
                self._constraint_draft(message, redacted, lowered, override),
                self._profile_draft(message, redacted, lowered, override),
                self._preference_draft(message, redacted, lowered, override),
                self._episode_draft(message, redacted, lowered, override),
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
        self, message: MemorySourceMessage, redacted: str, secret_hit: bool
    ) -> MemoryCandidateDraft | None:
        if not secret_hit:
            return None
        return self._base(
            message,
            redacted,
            _SECRET_EVIDENCE,
            MemoryScope.USER,
            MemoryType.PROFILE_FACT,
            0.95,
            SensitivityLabel.SECRET,
        )

    def _correction_draft(
        self,
        message: MemorySourceMessage,
        redacted: str,
        lowered: str,
        override: SensitivityLabel | None,
    ) -> MemoryCandidateDraft | None:
        if not _mentions(lowered, _CORRECTION_MARKERS):
            return None
        return self._base(
            message,
            redacted,
            f"signal=correction:{_first_hit(lowered, _CORRECTION_MARKERS)}",
            MemoryScope.USER,
            MemoryType.CORRECTION,
            0.85,
            override or SensitivityLabel.NONE,
        )

    def _constraint_draft(
        self,
        message: MemorySourceMessage,
        redacted: str,
        lowered: str,
        override: SensitivityLabel | None,
    ) -> MemoryCandidateDraft | None:
        if not _mentions(lowered, _CONSTRAINT_MARKERS):
            return None
        return self._base(
            message,
            redacted,
            f"signal=constraint:{_first_hit(lowered, _CONSTRAINT_MARKERS)}",
            MemoryScope.WORKSPACE,
            MemoryType.CONSTRAINT,
            0.85,
            override or SensitivityLabel.NONE,
        )

    def _profile_draft(
        self,
        message: MemorySourceMessage,
        redacted: str,
        lowered: str,
        override: SensitivityLabel | None,
    ) -> MemoryCandidateDraft | None:
        if not _mentions(lowered, _PROFILE_MARKERS):
            return None
        return self._base(
            message,
            redacted,
            f"signal=profile_fact:{_first_hit(lowered, _PROFILE_MARKERS)}",
            MemoryScope.USER,
            MemoryType.PROFILE_FACT,
            0.8,
            override or SensitivityLabel.PERSONAL,
        )

    def _preference_draft(
        self,
        message: MemorySourceMessage,
        redacted: str,
        lowered: str,
        override: SensitivityLabel | None,
    ) -> MemoryCandidateDraft | None:
        if not _mentions(lowered, _PREFERENCE_MARKERS):
            return None
        sensitivity = (
            SensitivityLabel.PERSONAL
            if _mentions(lowered, _PERSONAL_MARKERS)
            else SensitivityLabel.NONE
        )
        # Hedged wording cannot clear the acceptance bar, so the policy marks
        # it ambiguous. A chat-local framing proposes conversation scope, so
        # the policy marks it wrong-scope for durable user memory.
        hedged = _mentions(lowered, _HEDGED_MARKERS)
        chat_local = _mentions(lowered, _CHAT_LOCAL_MARKERS)
        return self._base(
            message,
            redacted,
            f"signal=preference:{_first_hit(lowered, _PREFERENCE_MARKERS)}",
            MemoryScope.CONVERSATION if chat_local else MemoryScope.USER,
            MemoryType.PREFERENCE,
            0.6 if hedged else 0.8,
            override or sensitivity,
        )

    def _episode_draft(
        self,
        message: MemorySourceMessage,
        redacted: str,
        lowered: str,
        override: SensitivityLabel | None,
    ) -> MemoryCandidateDraft | None:
        if not _mentions(lowered, _EPISODE_MARKERS):
            return None
        return self._base(
            message,
            redacted,
            f"signal=episode:{_first_hit(lowered, _EPISODE_MARKERS)}",
            MemoryScope.CONVERSATION,
            MemoryType.EPISODE,
            0.75,
            override or SensitivityLabel.NONE,
        )
