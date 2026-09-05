"""Memory candidate and extraction-run value contracts for milestone R5.

These contracts are storage-agnostic and route-agnostic: this module depends
on the Python standard library only. Identifiers, timestamps, and policy
vocabulary are server-owned. Provenance existence (workspace, conversation,
message) is validated by the service layer against the R3/R4 repositories,
not here, so foreign identifiers are required non-empty text without a
prefix claim.

Field set, types, and defaults match the approved R5 specification.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Type, TypeVar

MEMORY_RUN_ID_PREFIX = "mer_"
MEMORY_CANDIDATE_ID_PREFIX = "mc_"
CANDIDATE_TEXT_MAX_LENGTH = 500
EVIDENCE_SUMMARY_MAX_LENGTH = 240


class MemoryValidationError(ValueError):
    """A memory contract rule was violated before any storage write."""


class MemoryRunStatus(str, Enum):
    """Extraction-run outcome vocabulary from the approved R5 specification."""

    COMPLETED = "completed"
    COMPLETED_WITH_REJECTIONS = "completed_with_rejections"
    FAILED = "failed"
    INVALID = "invalid"


class MemoryCandidateStatus(str, Enum):
    """Candidate policy-decision vocabulary.

    `ACCEPTED` means accepted into the R5 shadow candidate set for evaluation
    only, never promoted into answer-eligible memory.
    """

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_USER_ACTION = "needs_user_action"
    INVALID = "invalid"


class MemoryScope(str, Enum):
    """Proposed memory scope vocabulary from the approved R5 specification."""

    USER = "user"
    WORKSPACE = "workspace"
    CONVERSATION = "conversation"
    NONE = "none"


class MemoryType(str, Enum):
    """Proposed memory type vocabulary from the approved R5 specification."""

    PREFERENCE = "preference"
    CONSTRAINT = "constraint"
    PROFILE_FACT = "profile_fact"
    EPISODE = "episode"
    DECISION = "decision"
    CORRECTION = "correction"
    SAFETY_NOTE = "safety_note"
    NONE = "none"


class SensitivityLabel(str, Enum):
    """Candidate sensitivity vocabulary from the approved R5 specification."""

    NONE = "none"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    SECRET = "secret"
    UNSAFE = "unsafe"


class PolicyReason(str, Enum):
    """Governed policy reason vocabulary from the approved R5 specification."""

    SUPPORTED_PREFERENCE = "supported_preference"
    SUPPORTED_CONSTRAINT = "supported_constraint"
    SUPPORTED_PROFILE_FACT = "supported_profile_fact"
    SUPPORTED_TRIP_DECISION = "supported_trip_decision"
    EXPLICIT_CORRECTION = "explicit_correction"
    NO_MEMORY_SIGNAL = "no_memory_signal"
    AMBIGUOUS = "ambiguous"
    TRANSIENT = "transient"
    WRONG_SCOPE = "wrong_scope"
    LOW_CONFIDENCE = "low_confidence"
    SENSITIVE = "sensitive"
    SECRET_LIKE = "secret_like"
    UNSUPPORTED = "unsupported"
    SYSTEM_GENERATED = "system_generated"
    TRACE_EXCLUDED = "trace_excluded"


class MemoryExtractionTrigger(str, Enum):
    """How one shadow extraction run was started."""

    MANUAL = "manual"
    EVALUATION = "evaluation"


def generate_memory_run_id() -> str:
    """Return a new opaque extraction-run identifier with the governed prefix."""
    return f"{MEMORY_RUN_ID_PREFIX}{uuid.uuid4().hex}"


def generate_memory_candidate_id() -> str:
    """Return a new opaque candidate identifier with the governed prefix."""
    return f"{MEMORY_CANDIDATE_ID_PREFIX}{uuid.uuid4().hex}"


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def require_text(value: Any, field_name: str, max_length: int | None = None) -> str:
    """Strip and validate a required text field."""
    if not isinstance(value, str):
        raise MemoryValidationError(f"Memory field '{field_name}' must be a string.")
    stripped = value.strip()
    if not stripped:
        raise MemoryValidationError(f"Memory field '{field_name}' must not be empty.")
    if max_length is not None and len(stripped) > max_length:
        raise MemoryValidationError(
            f"Memory field '{field_name}' must be at most {max_length} characters."
        )
    return stripped


def normalize_text(value: Any, field_name: str, max_length: int | None = None) -> str:
    """Strip an optional text field without requiring content."""
    if not isinstance(value, str):
        raise MemoryValidationError(f"Memory field '{field_name}' must be a string.")
    stripped = value.strip()
    if max_length is not None and len(stripped) > max_length:
        raise MemoryValidationError(
            f"Memory field '{field_name}' must be at most {max_length} characters."
        )
    return stripped


def _require_identity(value: Any, field_name: str, prefix: str) -> str:
    """Validate a server-generated identifier and its governed prefix."""
    identity = require_text(value, field_name)
    if not identity.startswith(prefix):
        raise MemoryValidationError(
            f"Memory field '{field_name}' must start with '{prefix}'."
        )
    return identity


def _require_utc(value: Any, field_name: str) -> datetime:
    """Require a timezone-aware datetime and normalize it to UTC."""
    if not isinstance(value, datetime):
        raise MemoryValidationError(f"Memory field '{field_name}' must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise MemoryValidationError(
            f"Memory field '{field_name}' must be timezone-aware UTC."
        )
    return value.astimezone(timezone.utc)


def _require_sequence(value: Any, field_name: str) -> int:
    """Require a 1-based message position matching the R4 sequence contract."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise MemoryValidationError(f"Memory field '{field_name}' must be an integer.")
    if value < 1:
        raise MemoryValidationError(f"Memory field '{field_name}' must be at least 1.")
    return value


def _require_confidence(value: Any, field_name: str) -> float:
    """Require a finite confidence value inside the closed unit interval."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MemoryValidationError(f"Memory field '{field_name}' must be a number.")
    confidence = float(value)
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise MemoryValidationError(
            f"Memory field '{field_name}' must be inside [0.0, 1.0]."
        )
    return confidence


EnumT = TypeVar("EnumT", bound=Enum)


def _coerce_enum(value: Any, field_name: str, enum_cls: Type[EnumT]) -> EnumT:
    """Accept an enum member or its raw value; reject anything ungoverned."""
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except ValueError:
        allowed = sorted(item.value for item in enum_cls)
        raise MemoryValidationError(
            f"Memory field '{field_name}' must be one of {allowed}."
        ) from None


def _require_count(value: Any, field_name: str) -> int:
    """Require a non-negative run counter."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise MemoryValidationError(f"Memory field '{field_name}' must be an integer.")
    if value < 0:
        raise MemoryValidationError(
            f"Memory field '{field_name}' must not be negative."
        )
    return value


@dataclass(frozen=True)
class MemorySourceMessage:
    """The memory module's projection of one R4 conversation message.

    Role, source, and trace visibility are copied as plain text so extraction
    code does not import conversation models. Provenance existence is checked
    by the service layer; this contract only guarantees shape.
    """

    message_id: str
    conversation_id: str
    workspace_id: str
    sequence: int
    role: str
    source: str
    trace_visibility: str
    content: str
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "message_id", require_text(self.message_id, "message_id")
        )
        object.__setattr__(
            self,
            "conversation_id",
            require_text(self.conversation_id, "conversation_id"),
        )
        object.__setattr__(
            self, "workspace_id", require_text(self.workspace_id, "workspace_id")
        )
        object.__setattr__(
            self, "sequence", _require_sequence(self.sequence, "sequence")
        )
        object.__setattr__(self, "role", require_text(self.role, "role"))
        object.__setattr__(self, "source", require_text(self.source, "source"))
        object.__setattr__(
            self,
            "trace_visibility",
            require_text(self.trace_visibility, "trace_visibility"),
        )
        object.__setattr__(self, "content", require_text(self.content, "content"))
        object.__setattr__(
            self, "created_at", _require_utc(self.created_at, "created_at")
        )


@dataclass(frozen=True)
class MemoryCandidateDraft:
    """One raw extractor proposal before policy decides its status.

    `status` and `reason` are absent until `MemoryPolicy.evaluate` sets them.
    The extractor must never produce an `ACCEPTED` draft.
    """

    source_message_id: str
    conversation_id: str
    workspace_id: str
    source_sequence: int
    role: str
    source: str
    trace_visibility: str
    proposed_scope: MemoryScope
    proposed_type: MemoryType
    confidence: float
    sensitivity_label: SensitivityLabel
    text: str
    evidence_summary: str
    status: Optional[MemoryCandidateStatus] = field(default=None)
    reason: Optional[PolicyReason] = field(default=None)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_message_id",
            require_text(self.source_message_id, "source_message_id"),
        )
        object.__setattr__(
            self,
            "conversation_id",
            require_text(self.conversation_id, "conversation_id"),
        )
        object.__setattr__(
            self, "workspace_id", require_text(self.workspace_id, "workspace_id")
        )
        object.__setattr__(
            self,
            "source_sequence",
            _require_sequence(self.source_sequence, "source_sequence"),
        )
        object.__setattr__(self, "role", require_text(self.role, "role"))
        object.__setattr__(self, "source", require_text(self.source, "source"))
        object.__setattr__(
            self,
            "trace_visibility",
            require_text(self.trace_visibility, "trace_visibility"),
        )
        object.__setattr__(
            self,
            "proposed_scope",
            _coerce_enum(self.proposed_scope, "proposed_scope", MemoryScope),
        )
        object.__setattr__(
            self,
            "proposed_type",
            _coerce_enum(self.proposed_type, "proposed_type", MemoryType),
        )
        object.__setattr__(
            self,
            "confidence",
            _require_confidence(self.confidence, "confidence"),
        )
        object.__setattr__(
            self,
            "sensitivity_label",
            _coerce_enum(self.sensitivity_label, "sensitivity_label", SensitivityLabel),
        )
        object.__setattr__(
            self,
            "text",
            normalize_text(self.text, "text", CANDIDATE_TEXT_MAX_LENGTH),
        )
        object.__setattr__(
            self,
            "evidence_summary",
            normalize_text(
                self.evidence_summary,
                "evidence_summary",
                EVIDENCE_SUMMARY_MAX_LENGTH,
            ),
        )
        if self.status is not None:
            object.__setattr__(
                self,
                "status",
                _coerce_enum(self.status, "status", MemoryCandidateStatus),
            )
        if self.reason is not None:
            object.__setattr__(
                self, "reason", _coerce_enum(self.reason, "reason", PolicyReason)
            )


@dataclass(frozen=True)
class MemoryCandidate:
    """One persisted shadow memory candidate with its policy decision."""

    candidate_id: str
    run_id: str
    workspace_id: str
    conversation_id: str
    source_message_id: str
    source_sequence: int
    proposed_scope: MemoryScope
    proposed_type: MemoryType
    status: MemoryCandidateStatus
    confidence: float
    sensitivity_label: SensitivityLabel
    text: str
    evidence_summary: str
    reason: PolicyReason
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_id",
            _require_identity(
                self.candidate_id, "candidate_id", MEMORY_CANDIDATE_ID_PREFIX
            ),
        )
        object.__setattr__(self, "run_id", require_text(self.run_id, "run_id"))
        object.__setattr__(
            self, "workspace_id", require_text(self.workspace_id, "workspace_id")
        )
        object.__setattr__(
            self,
            "conversation_id",
            require_text(self.conversation_id, "conversation_id"),
        )
        object.__setattr__(
            self,
            "source_message_id",
            require_text(self.source_message_id, "source_message_id"),
        )
        object.__setattr__(
            self,
            "source_sequence",
            _require_sequence(self.source_sequence, "source_sequence"),
        )
        object.__setattr__(
            self,
            "proposed_scope",
            _coerce_enum(self.proposed_scope, "proposed_scope", MemoryScope),
        )
        object.__setattr__(
            self,
            "proposed_type",
            _coerce_enum(self.proposed_type, "proposed_type", MemoryType),
        )
        object.__setattr__(
            self,
            "status",
            _coerce_enum(self.status, "status", MemoryCandidateStatus),
        )
        object.__setattr__(
            self,
            "confidence",
            _require_confidence(self.confidence, "confidence"),
        )
        object.__setattr__(
            self,
            "sensitivity_label",
            _coerce_enum(self.sensitivity_label, "sensitivity_label", SensitivityLabel),
        )
        object.__setattr__(
            self,
            "text",
            normalize_text(self.text, "text", CANDIDATE_TEXT_MAX_LENGTH),
        )
        object.__setattr__(
            self,
            "evidence_summary",
            normalize_text(
                self.evidence_summary,
                "evidence_summary",
                EVIDENCE_SUMMARY_MAX_LENGTH,
            ),
        )
        object.__setattr__(
            self, "reason", _coerce_enum(self.reason, "reason", PolicyReason)
        )
        object.__setattr__(
            self, "created_at", _require_utc(self.created_at, "created_at")
        )


@dataclass(frozen=True)
class MemoryExtractionRun:
    """One shadow extraction execution with per-status candidate counts.

    For a finished run, `candidate_count` must equal the sum of the four
    status counters, including `invalid_count`.
    """

    run_id: str
    workspace_id: str
    conversation_id: str
    trigger: MemoryExtractionTrigger
    extractor_id: str
    policy_id: str
    status: MemoryRunStatus
    started_at: datetime
    finished_at: Optional[datetime]
    candidate_count: int
    accepted_count: int
    rejected_count: int
    needs_user_action_count: int
    invalid_count: int
    failure_reason: Optional[str] = field(default=None)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "run_id",
            _require_identity(self.run_id, "run_id", MEMORY_RUN_ID_PREFIX),
        )
        object.__setattr__(
            self, "workspace_id", require_text(self.workspace_id, "workspace_id")
        )
        object.__setattr__(
            self,
            "conversation_id",
            require_text(self.conversation_id, "conversation_id"),
        )
        object.__setattr__(
            self,
            "trigger",
            _coerce_enum(self.trigger, "trigger", MemoryExtractionTrigger),
        )
        object.__setattr__(
            self, "extractor_id", require_text(self.extractor_id, "extractor_id")
        )
        object.__setattr__(self, "policy_id", require_text(self.policy_id, "policy_id"))
        object.__setattr__(
            self, "status", _coerce_enum(self.status, "status", MemoryRunStatus)
        )
        object.__setattr__(
            self, "started_at", _require_utc(self.started_at, "started_at")
        )
        if self.finished_at is not None:
            object.__setattr__(
                self,
                "finished_at",
                _require_utc(self.finished_at, "finished_at"),
            )
        accepted = _require_count(self.accepted_count, "accepted_count")
        rejected = _require_count(self.rejected_count, "rejected_count")
        needs_action = _require_count(
            self.needs_user_action_count, "needs_user_action_count"
        )
        invalid = _require_count(self.invalid_count, "invalid_count")
        candidate_count = _require_count(self.candidate_count, "candidate_count")
        object.__setattr__(self, "accepted_count", accepted)
        object.__setattr__(self, "rejected_count", rejected)
        object.__setattr__(self, "needs_user_action_count", needs_action)
        object.__setattr__(self, "invalid_count", invalid)
        object.__setattr__(self, "candidate_count", candidate_count)
        if candidate_count != accepted + rejected + needs_action + invalid:
            raise MemoryValidationError(
                "Memory field 'candidate_count' must equal "
                "accepted_count + rejected_count + needs_user_action_count "
                "+ invalid_count."
            )
        if self.failure_reason is not None:
            object.__setattr__(
                self,
                "failure_reason",
                normalize_text(self.failure_reason, "failure_reason"),
            )


# ---------------------------------------------------------------------------
# Runtime milestone R6: answer-eligible memory records, promotion, retrieval,
# and selection traces.
#
# These contracts extend the module without changing any R5 candidate
# vocabulary. Two names below are R6-scoped decisions the approved spec
# leaves open: `MemorySelectionReason` carries exactly the two selection
# paths named by retrieval rule 9 (lexical score above zero, direct active
# correction), and `MemorySelectionTrace` is the persisted retrieval event
# the R6 storage module records.
# ---------------------------------------------------------------------------

MEMORY_RECORD_ID_PREFIX = "mem_"
MEMORY_PROMOTION_RUN_ID_PREFIX = "mpr_"
MEMORY_RETRIEVAL_TRACE_ID_PREFIX = "mtr_"
MEMORY_RECORD_TEXT_MAX_LENGTH = 500


class MemoryRecordScope(str, Enum):
    """Answer-eligible memory scope vocabulary from the approved R6 spec."""

    USER = "user"
    WORKSPACE = "workspace"
    CONVERSATION = "conversation"


class MemoryRecordType(str, Enum):
    """Answer-eligible memory type vocabulary from the approved R6 spec."""

    PREFERENCE = "preference"
    CONSTRAINT = "constraint"
    PROFILE_FACT = "profile_fact"
    EPISODE = "episode"
    DECISION = "decision"
    CORRECTION = "correction"


class MemoryRecordStatus(str, Enum):
    """Durable memory lifecycle vocabulary from the approved R6 spec."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    ARCHIVED = "archived"
    DELETION_REQUESTED = "deletion_requested"
    DELETED = "deleted"


class MemorySelectionReason(str, Enum):
    """Controlled per-turn selection reasons: the two retrieval rule 9 paths."""

    LEXICAL_MATCH = "lexical_match"
    ACTIVE_CORRECTION = "active_correction"


class MemorySelectionStatus(str, Enum):
    """Per-turn retrieval outcome vocabulary from the approved R6 spec."""

    SELECTED = "selected"
    NONE_SELECTED = "none_selected"
    SKIPPED = "skipped"


class PromotionSkipReason(str, Enum):
    """Governed promotion outcome vocabulary from the approved R6 spec."""

    PROMOTED = "promoted"
    NOT_ACCEPTED = "not_accepted"
    SCOPE_NOT_PROMOTABLE = "scope_not_promotable"
    TYPE_NOT_PROMOTABLE = "type_not_promotable"
    BELOW_MIN_CONFIDENCE = "below_min_confidence"
    SENSITIVITY_NOT_PROMOTABLE = "sensitivity_not_promotable"
    PROVENANCE_UNRESOLVED = "provenance_unresolved"
    REASON_NOT_PROMOTABLE = "reason_not_promotable"
    DUPLICATE_ACTIVE_RECORD = "duplicate_active_record"
    CORRECTION_SUPERSEDES_MULTIPLE = "correction_supersedes_multiple"


def generate_memory_record_id() -> str:
    """Return a new opaque memory record identifier with the governed prefix."""
    return f"{MEMORY_RECORD_ID_PREFIX}{uuid.uuid4().hex}"


def generate_memory_promotion_run_id() -> str:
    """Return a new opaque promotion run identifier with the governed prefix."""
    return f"{MEMORY_PROMOTION_RUN_ID_PREFIX}{uuid.uuid4().hex}"


def generate_memory_retrieval_trace_id() -> str:
    """Return a new opaque retrieval trace identifier with the governed prefix."""
    return f"{MEMORY_RETRIEVAL_TRACE_ID_PREFIX}{uuid.uuid4().hex}"


def _require_score(value: Any, field_name: str) -> float:
    """Require a finite, non-negative deterministic ranking score."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MemoryValidationError(f"Memory field '{field_name}' must be a number.")
    score = float(value)
    if not math.isfinite(score) or score < 0.0:
        raise MemoryValidationError(
            f"Memory field '{field_name}' must be finite and non-negative."
        )
    return score


@dataclass(frozen=True)
class MemoryRecord:
    """One answer-eligible durable memory record.

    Records are created only by promotion policy, never directly by the
    extractor. Sensitivity beyond `none` and `personal` is rejected at
    promotion time; the contract itself accepts the full label vocabulary so
    seeded evaluation fixtures can exercise lifecycle filtering.
    """

    memory_id: str
    source_candidate_id: str
    workspace_id: str
    conversation_id: str
    source_message_id: str
    source_sequence: int
    owner_user_id: str
    scope: MemoryRecordScope
    scope_id: str
    memory_type: MemoryRecordType
    status: MemoryRecordStatus
    text: str
    confidence: float
    sensitivity_label: SensitivityLabel
    supersedes_memory_id: str | None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "memory_id",
            _require_identity(self.memory_id, "memory_id", MEMORY_RECORD_ID_PREFIX),
        )
        object.__setattr__(
            self,
            "source_candidate_id",
            require_text(self.source_candidate_id, "source_candidate_id"),
        )
        object.__setattr__(
            self, "workspace_id", require_text(self.workspace_id, "workspace_id")
        )
        object.__setattr__(
            self,
            "conversation_id",
            require_text(self.conversation_id, "conversation_id"),
        )
        object.__setattr__(
            self,
            "source_message_id",
            require_text(self.source_message_id, "source_message_id"),
        )
        object.__setattr__(
            self,
            "source_sequence",
            _require_sequence(self.source_sequence, "source_sequence"),
        )
        object.__setattr__(
            self,
            "owner_user_id",
            require_text(self.owner_user_id, "owner_user_id"),
        )
        scope = _coerce_enum(self.scope, "scope", MemoryRecordScope)
        object.__setattr__(self, "scope", scope)
        scope_id = require_text(self.scope_id, "scope_id")
        expected_owner = {
            MemoryRecordScope.USER: self.owner_user_id,
            MemoryRecordScope.WORKSPACE: self.workspace_id,
            MemoryRecordScope.CONVERSATION: self.conversation_id,
        }[scope]
        if scope_id != expected_owner:
            raise MemoryValidationError(
                "Memory field 'scope_id' must be the owner label for "
                "'user' scope, the workspace id for 'workspace' scope, or "
                "the conversation id for 'conversation' scope."
            )
        object.__setattr__(self, "scope_id", scope_id)
        object.__setattr__(
            self,
            "memory_type",
            _coerce_enum(self.memory_type, "memory_type", MemoryRecordType),
        )
        object.__setattr__(
            self,
            "status",
            _coerce_enum(self.status, "status", MemoryRecordStatus),
        )
        object.__setattr__(
            self,
            "text",
            require_text(self.text, "text", MEMORY_RECORD_TEXT_MAX_LENGTH),
        )
        object.__setattr__(
            self,
            "confidence",
            _require_confidence(self.confidence, "confidence"),
        )
        object.__setattr__(
            self,
            "sensitivity_label",
            _coerce_enum(self.sensitivity_label, "sensitivity_label", SensitivityLabel),
        )
        if self.supersedes_memory_id is not None:
            object.__setattr__(
                self,
                "supersedes_memory_id",
                _require_identity(
                    self.supersedes_memory_id,
                    "supersedes_memory_id",
                    MEMORY_RECORD_ID_PREFIX,
                ),
            )
        object.__setattr__(
            self, "created_at", _require_utc(self.created_at, "created_at")
        )
        object.__setattr__(
            self, "updated_at", _require_utc(self.updated_at, "updated_at")
        )
        if self.expires_at is not None:
            object.__setattr__(
                self,
                "expires_at",
                _require_utc(self.expires_at, "expires_at"),
            )


@dataclass(frozen=True)
class PromotionSkipCount:
    """One governed promotion outcome with its candidate count."""

    reason: PromotionSkipReason
    count: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reason",
            _coerce_enum(self.reason, "reason", PromotionSkipReason),
        )
        object.__setattr__(self, "count", _require_count(self.count, "count"))


@dataclass(frozen=True)
class MemoryPromotionRun:
    """One persisted candidate-to-record promotion execution."""

    promotion_run_id: str
    workspace_id: str
    conversation_id: str | None
    source_candidate_count: int
    promoted_count: int
    skipped_count: int
    skip_reasons: tuple[PromotionSkipCount, ...]
    started_at: datetime
    finished_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "promotion_run_id",
            _require_identity(
                self.promotion_run_id,
                "promotion_run_id",
                MEMORY_PROMOTION_RUN_ID_PREFIX,
            ),
        )
        object.__setattr__(
            self, "workspace_id", require_text(self.workspace_id, "workspace_id")
        )
        if self.conversation_id is not None:
            object.__setattr__(
                self,
                "conversation_id",
                require_text(self.conversation_id, "conversation_id"),
            )
        source = _require_count(self.source_candidate_count, "source_candidate_count")
        promoted = _require_count(self.promoted_count, "promoted_count")
        skipped = _require_count(self.skipped_count, "skipped_count")
        object.__setattr__(self, "source_candidate_count", source)
        object.__setattr__(self, "promoted_count", promoted)
        object.__setattr__(self, "skipped_count", skipped)
        reasons = tuple(self.skip_reasons)
        for item in reasons:
            if not isinstance(item, PromotionSkipCount):
                raise MemoryValidationError(
                    "Memory field 'skip_reasons' must hold PromotionSkipCount entries."
                )
        object.__setattr__(self, "skip_reasons", reasons)
        if source != promoted + skipped:
            raise MemoryValidationError(
                "Memory field 'source_candidate_count' must equal "
                "promoted_count + skipped_count."
            )
        object.__setattr__(
            self, "started_at", _require_utc(self.started_at, "started_at")
        )
        object.__setattr__(
            self, "finished_at", _require_utc(self.finished_at, "finished_at")
        )


@dataclass(frozen=True)
class MemoryPromotionResult:
    """The outcome a promotion use case returns: the run plus created ids."""

    promotion_run_id: str
    workspace_id: str
    conversation_id: str | None
    source_candidate_count: int
    promoted_count: int
    skipped_count: int
    skip_reasons: tuple[PromotionSkipCount, ...]
    promoted_memory_ids: tuple[str, ...]
    started_at: datetime
    finished_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "promotion_run_id",
            _require_identity(
                self.promotion_run_id,
                "promotion_run_id",
                MEMORY_PROMOTION_RUN_ID_PREFIX,
            ),
        )
        object.__setattr__(
            self, "workspace_id", require_text(self.workspace_id, "workspace_id")
        )
        if self.conversation_id is not None:
            object.__setattr__(
                self,
                "conversation_id",
                require_text(self.conversation_id, "conversation_id"),
            )
        source = _require_count(self.source_candidate_count, "source_candidate_count")
        promoted = _require_count(self.promoted_count, "promoted_count")
        skipped = _require_count(self.skipped_count, "skipped_count")
        object.__setattr__(self, "source_candidate_count", source)
        object.__setattr__(self, "promoted_count", promoted)
        object.__setattr__(self, "skipped_count", skipped)
        reasons = tuple(self.skip_reasons)
        for item in reasons:
            if not isinstance(item, PromotionSkipCount):
                raise MemoryValidationError(
                    "Memory field 'skip_reasons' must hold PromotionSkipCount entries."
                )
        object.__setattr__(self, "skip_reasons", reasons)
        if source != promoted + skipped:
            raise MemoryValidationError(
                "Memory field 'source_candidate_count' must equal "
                "promoted_count + skipped_count."
            )
        promoted_ids = tuple(
            _require_identity(memory_id, "promoted_memory_ids", MEMORY_RECORD_ID_PREFIX)
            for memory_id in self.promoted_memory_ids
        )
        if len(promoted_ids) != promoted:
            raise MemoryValidationError(
                "Memory field 'promoted_memory_ids' must hold exactly "
                "promoted_count identifiers."
            )
        object.__setattr__(self, "promoted_memory_ids", promoted_ids)
        object.__setattr__(
            self, "started_at", _require_utc(self.started_at, "started_at")
        )
        object.__setattr__(
            self, "finished_at", _require_utc(self.finished_at, "finished_at")
        )


@dataclass(frozen=True)
class MemorySelection:
    """One memory record selected for a turn, with its controlled reason."""

    memory_id: str
    scope: MemoryRecordScope
    memory_type: MemoryRecordType
    reason: MemorySelectionReason
    score: float
    text: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "memory_id",
            _require_identity(self.memory_id, "memory_id", MEMORY_RECORD_ID_PREFIX),
        )
        object.__setattr__(
            self, "scope", _coerce_enum(self.scope, "scope", MemoryRecordScope)
        )
        object.__setattr__(
            self,
            "memory_type",
            _coerce_enum(self.memory_type, "memory_type", MemoryRecordType),
        )
        object.__setattr__(
            self,
            "reason",
            _coerce_enum(self.reason, "reason", MemorySelectionReason),
        )
        object.__setattr__(self, "score", _require_score(self.score, "score"))
        object.__setattr__(
            self,
            "text",
            require_text(self.text, "text", MEMORY_RECORD_TEXT_MAX_LENGTH),
        )


@dataclass(frozen=True)
class MemorySelectionTrace:
    """One persisted retrieval event: eligibility, selection, and gate state.

    `selected_ids` and `reasons` are aligned by index. No field carries
    message content, memory text beyond selected identifiers, or prompt
    fragments.
    """

    trace_id: str
    workspace_id: str
    conversation_id: str | None
    gate_enabled: bool
    status: MemorySelectionStatus
    selected_ids: tuple[str, ...]
    reasons: tuple[MemorySelectionReason, ...]
    eligible_count: int
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "trace_id",
            _require_identity(
                self.trace_id,
                "trace_id",
                MEMORY_RETRIEVAL_TRACE_ID_PREFIX,
            ),
        )
        object.__setattr__(
            self, "workspace_id", require_text(self.workspace_id, "workspace_id")
        )
        if self.conversation_id is not None:
            object.__setattr__(
                self,
                "conversation_id",
                require_text(self.conversation_id, "conversation_id"),
            )
        if not isinstance(self.gate_enabled, bool):
            raise MemoryValidationError(
                "Memory field 'gate_enabled' must be a boolean."
            )
        object.__setattr__(
            self,
            "status",
            _coerce_enum(self.status, "status", MemorySelectionStatus),
        )
        selected_ids = tuple(
            _require_identity(memory_id, "selected_ids", MEMORY_RECORD_ID_PREFIX)
            for memory_id in self.selected_ids
        )
        object.__setattr__(self, "selected_ids", selected_ids)
        reasons = tuple(
            _coerce_enum(reason, "reasons", MemorySelectionReason)
            for reason in self.reasons
        )
        object.__setattr__(self, "reasons", reasons)
        if len(selected_ids) != len(reasons):
            raise MemoryValidationError(
                "Memory fields 'selected_ids' and 'reasons' must align by index."
            )
        object.__setattr__(
            self,
            "eligible_count",
            _require_count(self.eligible_count, "eligible_count"),
        )
        object.__setattr__(
            self, "created_at", _require_utc(self.created_at, "created_at")
        )
