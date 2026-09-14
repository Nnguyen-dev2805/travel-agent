"""Immutable semantic-memory write contracts.

Pure domain types for the versioned write path: evidence, candidate,
decision, assertion identity, version, relation, operation, and change
set. This module depends on the Python standard library only.

Identity derives from owner, scope, key, subject, and condition.
Display text is localized presentation and never defines identity, so
one Vietnamese and one English paraphrase of a normalized value share
one assertion identity.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

EVIDENCE_ID_PREFIX = "mev_"
CANDIDATE_ID_PREFIX = "mc_"
DECISION_ID_PREFIX = "mdc_"
VERSION_ID_PREFIX = "mem_"

#: The governed in-process shape of one normalized semantic value.
#:
#: A `single` key holds one `str`; a `set` key holds a non-empty, sorted,
#: deduplicated tuple whose members all belong to the registry entry. The
#: representation is declared rather than inferred from delimiters, so no reader
#: ever has to guess whether `"a|b"` is one value or two (`plan v0.11`).
NormalizedSemanticValue = str | tuple[str, ...]

#: The first generation of a new assertion. A forget advances it.
INITIAL_SUPPRESSION_GENERATION = 1


class ExplicitIntentError(ValueError):
    """A non-explicit actor reached the explicit set-replacement channel.

    This is a domain-validation error, not a persistence outcome: the resolver
    raises it before a unit of work exists. Keeping it here prevents the pure
    resolver from importing the UoW package just to name a validation failure.
    """


class Authority(str, Enum):
    """Where a semantic observation comes from, strongest first."""

    EXPLICIT_SAVE = "explicit_save"
    EXPLICIT_STATEMENT = "explicit_statement"
    REPEATED_INFERENCE = "repeated_inference"


AUTHORITY_RANK = {
    Authority.EXPLICIT_SAVE: 3,
    Authority.EXPLICIT_STATEMENT: 2,
    Authority.REPEATED_INFERENCE: 1,
}
"""Higher rank wins when two observations disagree."""


class SensitivityBand(str, Enum):
    """Ordered sensitivity bands; escalation may only move upward."""

    ORDINARY_PERSONAL = "ordinary_personal"
    CONTEXTUALLY_SENSITIVE = "contextually_sensitive"
    RESTRICTED = "restricted"
    PROHIBITED_SECRET = "prohibited_secret"


SENSITIVITY_RANK = {
    SensitivityBand.ORDINARY_PERSONAL: 0,
    SensitivityBand.CONTEXTUALLY_SENSITIVE: 1,
    SensitivityBand.RESTRICTED: 2,
    SensitivityBand.PROHIBITED_SECRET: 3,
}


class MemoryScope(str, Enum):
    """Scopes a governed Memory assertion may live in."""

    USER = "user"
    CONVERSATION = "conversation"


class Cardinality(str, Enum):
    """How many current values one assertion identity may hold."""

    SINGLE = "single"
    SET = "set"


class RetentionMode(str, Enum):
    """What must remain true for a Memory version to stay eligible.

    Persisted at write time and immutable for that version. It answers a
    different question from `expires_at` (temporal validity) and from
    `suppression_generation` (which forget era), and the three are evaluated
    independently (`ADR 0037`).
    """

    CONVERSATION_BOUND = "conversation_bound"
    SOURCE_BOUND = "source_bound"
    USER_DURABLE = "user_durable"


class SourceValidity(str, Enum):
    """Caller-owned validity of the source/evidence snapshot."""

    VALID = "valid"
    INVALID = "invalid"
    NOT_REQUIRED = "not_required"


class MemoryRelation(str, Enum):
    """Closed semantic relationship between a candidate and current state."""

    SAME = "same"
    COMPATIBLE = "compatible"
    CONTRADICTION = "contradiction"
    TEMPORAL_UPDATE = "temporal_update"
    SCOPE_EXCEPTION = "scope_exception"
    UNRELATED = "unrelated"
    UNCERTAIN = "uncertain"


class MemoryOperation(str, Enum):
    """Closed mutation vocabulary produced by the deterministic resolver."""

    ADD = "add"
    REINFORCE = "reinforce"
    SUPERSEDE = "supersede"
    ADD_EXCEPTION = "add_exception"
    PENDING_CONFLICT = "pending_conflict"
    REJECT = "reject"
    NOOP = "noop"
    REVOKE = "revoke"


class DecisionOutcome(str, Enum):
    """Closed write-permission outcomes for one candidate."""

    DIRECT_WRITE = "direct_write"
    SHADOW = "shadow"
    HELD_SENSITIVE = "held_sensitive"
    REJECTED = "rejected"
    INVALID = "invalid"


class DecisionReason(str, Enum):
    """Governed reason codes explaining one candidate decision."""

    DIRECT_WRITE_ELIGIBLE = "direct_write_eligible"
    SHADOW_VALID_UNPROMOTED = "shadow_valid_unpromoted"
    HELD_SENSITIVE = "held_sensitive"
    REJECTED_ACTOR = "rejected_actor"
    REJECTED_AUTH = "rejected_auth"
    REJECTED_SOURCE = "rejected_source"
    REJECTED_PROHIBITED = "rejected_prohibited"
    INVALID_KEY = "invalid_key"
    INVALID_VALUE = "invalid_value"
    INVALID_SCOPE = "invalid_scope"
    INVALID_SENSITIVITY = "invalid_sensitivity"
    INVALID_CONDITION = "invalid_condition"


class VersionStatus(str, Enum):
    """Lifecycle states of one assertion version.

    `REVOKED` is product forget, not privacy erasure: the row survives so
    delayed work can be fenced against it, while the assertion's
    `suppression_generation` advances so older-generation evidence can no longer
    form, activate, or read (`ADR 0037`).
    """

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"


def new_evidence_id() -> str:
    """Return a new opaque evidence identifier."""
    return f"{EVIDENCE_ID_PREFIX}{uuid.uuid4().hex}"


def new_candidate_id() -> str:
    """Return a new opaque candidate identifier."""
    return f"{CANDIDATE_ID_PREFIX}{uuid.uuid4().hex}"


def new_version_id() -> str:
    """Return a new opaque assertion-version identifier."""
    return f"{VERSION_ID_PREFIX}{uuid.uuid4().hex}"


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Field '{field_name}' must be a string.")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"Field '{field_name}' must not be blank.")
    return stripped


def _require_utc(value: Any, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"Field '{field_name}' must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"Field '{field_name}' must carry timezone information.")
    return value.astimezone(timezone.utc)


def _require_identity(value: Any, field_name: str, prefix: str) -> str:
    identity = _require_text(value, field_name)
    if not identity.startswith(prefix):
        raise ValueError(f"Field '{field_name}' must start with '{prefix}'.")
    return identity


def _coerce_enum(value: Any, field_name: str, enum_type: type[Enum]) -> Any:
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        try:
            return enum_type(value)
        except ValueError as error:
            allowed = ", ".join(member.value for member in enum_type)
            raise ValueError(
                f"Unknown {field_name} value. Allowed values: {allowed}."
            ) from error
    raise ValueError(f"Field '{field_name}' must be a {enum_type.__name__} value.")


def _require_normalized_value(value: Any, field_name: str) -> NormalizedSemanticValue:
    """Validate the governed shape of one normalized value.

    A `single` key carries one non-blank `str`. A `set` key carries a non-empty
    tuple of non-blank, whitespace-trimmed members in strictly ascending order,
    which is what makes it simultaneously sorted and duplicate-free.

    Order and duplication are refused here rather than normalised, because
    silently sorting would hide a producer that is assembling a snapshot from
    unordered evidence, and the stored snapshot must be reproducible from the
    same inputs. Membership in the registry entry is *not* checked here: that is
    `validate_against_registry`, and checking it in the model would make this
    module import the registry that imports it.
    """
    if isinstance(value, str):
        return _require_text(value, field_name)
    if isinstance(value, tuple):
        if not value:
            raise ValueError(
                f"Field '{field_name}' must not be an empty set. Removing the "
                "last member is a revoke, not a stored snapshot."
            )
        members = []
        for member in value:
            if not isinstance(member, str):
                raise ValueError(
                    f"Every member of '{field_name}' must be a string."
                )
            members.append(_require_text(member, f"{field_name} member"))
        if any(left >= right for left, right in zip(members, members[1:])):
            raise ValueError(
                f"Field '{field_name}' must be strictly ascending, so it is both "
                "sorted and free of duplicates."
            )
        return tuple(members)
    raise ValueError(
        f"Field '{field_name}' must be a string or a tuple of strings."
    )


def _require_positive_generation(value: Any, field_name: str) -> int:
    """Generations are positive integers; a bool is not an integer here."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Field '{field_name}' must be an integer.")
    if value < INITIAL_SUPPRESSION_GENERATION:
        raise ValueError(
            f"Field '{field_name}' must be at least "
            f"{INITIAL_SUPPRESSION_GENERATION}."
        )
    return value


def _optional_utc(value: Any, field_name: str) -> datetime | None:
    """Temporal validity is optional, but never ambiguous when present."""
    if value is None:
        return None
    return _require_utc(value, field_name)


@dataclass(frozen=True)
class MemoryEvidence:
    """One raw semantic observation before normalization and policy."""

    evidence_id: str
    owner_user_id: str
    conversation_id: str
    source_message_id: str
    display_text: str
    authority: Authority | str
    observed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evidence_id",
            _require_identity(self.evidence_id, "evidence_id", EVIDENCE_ID_PREFIX),
        )
        object.__setattr__(
            self, "owner_user_id", _require_text(self.owner_user_id, "owner_user_id")
        )
        object.__setattr__(
            self,
            "conversation_id",
            _require_text(self.conversation_id, "conversation_id"),
        )
        object.__setattr__(
            self,
            "source_message_id",
            _require_text(self.source_message_id, "source_message_id"),
        )
        object.__setattr__(
            self, "display_text", _require_text(self.display_text, "display_text")
        )
        object.__setattr__(
            self,
            "authority",
            _coerce_enum(self.authority, "authority", Authority),
        )
        object.__setattr__(
            self, "observed_at", _require_utc(self.observed_at, "observed_at")
        )


@dataclass(frozen=True)
class MemoryCandidate:
    """One normalized write proposal awaiting a policy decision.

    The canonical key names the registry entry and the normalized value
    carries meaning; display text is presentation only. Registry
    membership is checked by normalization and policy layers, so this
    contract validates shape and lets those layers reject unknown keys.
    """

    candidate_id: str
    evidence_ids: tuple[str, ...]
    owner_user_id: str
    scope: MemoryScope | str
    conversation_id: str | None
    canonical_key: str
    normalized_value: NormalizedSemanticValue
    display_text: str
    authority: Authority | str
    sensitivity: SensitivityBand | str
    condition: str = ""
    subject_key: str = "self"
    observed_at: datetime | None = None
    confidence: float = 1.0
    suppression_generation: int = INITIAL_SUPPRESSION_GENERATION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_id",
            _require_identity(self.candidate_id, "candidate_id", CANDIDATE_ID_PREFIX),
        )
        if not isinstance(self.evidence_ids, tuple):
            raise ValueError("Field 'evidence_ids' must be a tuple.")
        for evidence_id in self.evidence_ids:
            _require_text(evidence_id, "evidence_ids entry")
        object.__setattr__(
            self, "owner_user_id", _require_text(self.owner_user_id, "owner_user_id")
        )
        scope = _coerce_enum(self.scope, "scope", MemoryScope)
        object.__setattr__(self, "scope", scope)
        if scope is MemoryScope.CONVERSATION:
            if (
                not isinstance(self.conversation_id, str)
                or not self.conversation_id.strip()
            ):
                raise ValueError(
                    "A conversation-scoped candidate requires a conversation."
                )
            object.__setattr__(self, "conversation_id", self.conversation_id.strip())
        elif self.conversation_id is not None:
            object.__setattr__(
                self,
                "conversation_id",
                _require_text(self.conversation_id, "conversation_id"),
            )
        object.__setattr__(
            self, "canonical_key", _require_text(self.canonical_key, "canonical_key")
        )
        object.__setattr__(
            self,
            "normalized_value",
            _require_normalized_value(self.normalized_value, "normalized_value"),
        )
        object.__setattr__(
            self, "display_text", _require_text(self.display_text, "display_text")
        )
        object.__setattr__(
            self, "authority", _coerce_enum(self.authority, "authority", Authority)
        )
        object.__setattr__(
            self,
            "sensitivity",
            _coerce_enum(self.sensitivity, "sensitivity", SensitivityBand),
        )
        if not isinstance(self.condition, str):
            raise ValueError("Field 'condition' must be a string.")
        if isinstance(self.confidence, bool) or not isinstance(
            self.confidence, (int, float)
        ):
            raise ValueError("Field 'confidence' must be a number.")
        object.__setattr__(self, "confidence", float(self.confidence))
        object.__setattr__(
            self, "subject_key", _require_text(self.subject_key, "subject_key")
        )
        if self.observed_at is None:
            raise ValueError("Field 'observed_at' is required.")
        object.__setattr__(
            self, "observed_at", _require_utc(self.observed_at, "observed_at")
        )
        object.__setattr__(
            self,
            "suppression_generation",
            _require_positive_generation(
                self.suppression_generation, "suppression_generation"
            ),
        )


@dataclass(frozen=True)
class MemoryDecision:
    """One stamped policy outcome for a candidate.

    Identifiers and timestamps are assigned when a decision draft is
    persisted; policy itself returns the draft below and stays pure.
    """

    decision_id: str
    candidate_id: str
    outcome: DecisionOutcome | str
    reason: DecisionReason | str
    decided_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decision_id",
            _require_identity(self.decision_id, "decision_id", DECISION_ID_PREFIX),
        )
        object.__setattr__(
            self, "candidate_id", _require_text(self.candidate_id, "candidate_id")
        )
        object.__setattr__(
            self, "outcome", _coerce_enum(self.outcome, "outcome", DecisionOutcome)
        )
        object.__setattr__(
            self, "reason", _coerce_enum(self.reason, "reason", DecisionReason)
        )
        object.__setattr__(
            self, "decided_at", _require_utc(self.decided_at, "decided_at")
        )


@dataclass(frozen=True)
class MemoryDecisionDraft:
    """One proposed policy outcome, without identifier or timestamp.

    The decider returns drafts, never stamped decisions: omitting the
    minted fields keeps repeated calls on identical inputs fully equal.
    Stamping moves to later orchestration or persistence layers.
    """

    candidate_id: str
    outcome: DecisionOutcome | str
    reason: DecisionReason | str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "candidate_id", _require_text(self.candidate_id, "candidate_id")
        )
        object.__setattr__(
            self, "outcome", _coerce_enum(self.outcome, "outcome", DecisionOutcome)
        )
        object.__setattr__(
            self, "reason", _coerce_enum(self.reason, "reason", DecisionReason)
        )


@dataclass(frozen=True)
class AssertionIdentity:
    """Deterministic identity of one assertion.

    Built from owner, scope, key, subject, and condition only, so two
    paraphrases of one value resolve to the same identity.

    The value is deliberately absent. A `set`-cardinality assertion therefore
    keeps one identity across every member it holds, which is what lets a
    snapshot grow by union instead of spawning one assertion per member
    (`plan v0.11`).
    """

    owner_user_id: str
    scope: MemoryScope | str
    scope_id: str
    canonical_key: str
    subject_key: str
    condition_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "owner_user_id", _require_text(self.owner_user_id, "owner_user_id")
        )
        object.__setattr__(
            self, "scope", _coerce_enum(self.scope, "scope", MemoryScope)
        )
        object.__setattr__(self, "scope_id", _require_text(self.scope_id, "scope_id"))
        object.__setattr__(
            self, "canonical_key", _require_text(self.canonical_key, "canonical_key")
        )
        object.__setattr__(
            self, "subject_key", _require_text(self.subject_key, "subject_key")
        )
        object.__setattr__(
            self,
            "condition_fingerprint",
            _require_text(self.condition_fingerprint, "condition_fingerprint"),
        )


@dataclass(frozen=True)
class MemoryVersion:
    """One durable value held under an assertion identity."""

    version_id: str
    owner_user_id: str
    scope: MemoryScope | str
    scope_id: str
    canonical_key: str
    subject_key: str
    condition_fingerprint: str
    normalized_value: NormalizedSemanticValue
    display_text: str
    authority: Authority | str
    sensitivity: SensitivityBand | str
    status: VersionStatus | str
    valid_from: datetime
    #: Required. Assigned by `RetentionAssignmentPolicy` before the write and
    #: persisted with the version; the read path reads it back from storage
    #: rather than re-deriving it, so a later policy revision cannot reinterpret
    #: historical Memory.
    retention_mode: RetentionMode | str
    supersedes_version_id: str | None = None
    expires_at: datetime | None = None
    suppression_generation: int = INITIAL_SUPPRESSION_GENERATION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "version_id",
            _require_identity(self.version_id, "version_id", VERSION_ID_PREFIX),
        )
        object.__setattr__(
            self, "owner_user_id", _require_text(self.owner_user_id, "owner_user_id")
        )
        object.__setattr__(
            self, "scope", _coerce_enum(self.scope, "scope", MemoryScope)
        )
        object.__setattr__(self, "scope_id", _require_text(self.scope_id, "scope_id"))
        object.__setattr__(
            self, "canonical_key", _require_text(self.canonical_key, "canonical_key")
        )
        object.__setattr__(
            self, "subject_key", _require_text(self.subject_key, "subject_key")
        )
        object.__setattr__(
            self,
            "condition_fingerprint",
            _require_text(self.condition_fingerprint, "condition_fingerprint"),
        )
        object.__setattr__(
            self,
            "normalized_value",
            _require_normalized_value(self.normalized_value, "normalized_value"),
        )
        object.__setattr__(
            self, "display_text", _require_text(self.display_text, "display_text")
        )
        object.__setattr__(
            self, "authority", _coerce_enum(self.authority, "authority", Authority)
        )
        object.__setattr__(
            self,
            "sensitivity",
            _coerce_enum(self.sensitivity, "sensitivity", SensitivityBand),
        )
        object.__setattr__(
            self, "status", _coerce_enum(self.status, "status", VersionStatus)
        )
        if self.retention_mode is not None:
            object.__setattr__(
                self,
                "retention_mode",
                _coerce_enum(self.retention_mode, "retention_mode", RetentionMode),
            )
        else:
            raise ValueError("Field 'retention_mode' is required.")
        object.__setattr__(
            self, "valid_from", _require_utc(self.valid_from, "valid_from")
        )
        object.__setattr__(
            self, "expires_at", _optional_utc(self.expires_at, "expires_at")
        )
        object.__setattr__(
            self,
            "suppression_generation",
            _require_positive_generation(
                self.suppression_generation, "suppression_generation"
            ),
        )
        if self.supersedes_version_id is not None:
            object.__setattr__(
                self,
                "supersedes_version_id",
                _require_text(self.supersedes_version_id, "supersedes_version_id"),
            )


@dataclass(frozen=True)
class MemoryVersionDraft:
    """One proposed value awaiting persistence, without an identifier.

    The resolver returns drafts, never stored versions: identifiers are
    assigned later by the persistence layer, which does not exist in
    this slice. Every other field is governed exactly like a version,
    so two resolver calls on identical inputs return equal drafts and
    the resolver stays fully deterministic.
    """

    owner_user_id: str
    scope: MemoryScope | str
    scope_id: str
    canonical_key: str
    subject_key: str
    condition_fingerprint: str
    normalized_value: NormalizedSemanticValue
    display_text: str
    authority: Authority | str
    sensitivity: SensitivityBand | str
    valid_from: datetime
    #: Required, with no default. Assigned by `RetentionAssignmentPolicy` before
    #: the write; a draft that never went through assignment must fail here.
    retention_mode: RetentionMode | str
    status: VersionStatus | str = VersionStatus.ACTIVE
    supersedes_version_id: str | None = None
    expires_at: datetime | None = None
    suppression_generation: int = INITIAL_SUPPRESSION_GENERATION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "owner_user_id", _require_text(self.owner_user_id, "owner_user_id")
        )
        object.__setattr__(
            self, "scope", _coerce_enum(self.scope, "scope", MemoryScope)
        )
        object.__setattr__(self, "scope_id", _require_text(self.scope_id, "scope_id"))
        object.__setattr__(
            self, "canonical_key", _require_text(self.canonical_key, "canonical_key")
        )
        object.__setattr__(
            self, "subject_key", _require_text(self.subject_key, "subject_key")
        )
        object.__setattr__(
            self,
            "condition_fingerprint",
            _require_text(self.condition_fingerprint, "condition_fingerprint"),
        )
        object.__setattr__(
            self,
            "normalized_value",
            _require_normalized_value(self.normalized_value, "normalized_value"),
        )
        object.__setattr__(
            self, "display_text", _require_text(self.display_text, "display_text")
        )
        object.__setattr__(
            self, "authority", _coerce_enum(self.authority, "authority", Authority)
        )
        object.__setattr__(
            self,
            "sensitivity",
            _coerce_enum(self.sensitivity, "sensitivity", SensitivityBand),
        )
        object.__setattr__(
            self, "valid_from", _require_utc(self.valid_from, "valid_from")
        )
        object.__setattr__(
            self, "status", _coerce_enum(self.status, "status", VersionStatus)
        )
        object.__setattr__(
            self,
            "retention_mode",
            _coerce_enum(self.retention_mode, "retention_mode", RetentionMode),
        )
        object.__setattr__(
            self, "expires_at", _optional_utc(self.expires_at, "expires_at")
        )
        object.__setattr__(
            self,
            "suppression_generation",
            _require_positive_generation(
                self.suppression_generation, "suppression_generation"
            ),
        )
        if self.supersedes_version_id is not None:
            object.__setattr__(
                self,
                "supersedes_version_id",
                _require_text(self.supersedes_version_id, "supersedes_version_id"),
            )


@dataclass(frozen=True)
class MemoryChangeSet:
    """One deterministic resolver outcome: what mutates and why."""

    operation: MemoryOperation | str
    identity: AssertionIdentity | None
    new_version: MemoryVersionDraft | None
    superseded_version_ids: tuple[str, ...]
    reference_version_id: str | None
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operation",
            _coerce_enum(self.operation, "operation", MemoryOperation),
        )
        if self.identity is not None and not isinstance(
            self.identity, AssertionIdentity
        ):
            raise ValueError("Field 'identity' must be an AssertionIdentity or null.")
        if self.new_version is not None and not isinstance(
            self.new_version, MemoryVersionDraft
        ):
            raise ValueError(
                "Field 'new_version' must be a MemoryVersionDraft or null."
            )
        if not isinstance(self.superseded_version_ids, tuple):
            raise ValueError("Field 'superseded_version_ids' must be a tuple.")
        for version_id in self.superseded_version_ids:
            _require_text(version_id, "superseded_version_ids entry")
        if self.reference_version_id is not None:
            object.__setattr__(
                self,
                "reference_version_id",
                _require_text(self.reference_version_id, "reference_version_id"),
            )
        object.__setattr__(self, "reason", _require_text(self.reason, "reason"))


def assertion_identity(candidate: MemoryCandidate) -> AssertionIdentity:
    """Derive the deterministic identity for one candidate.

    The scope identifier is the owner for user scope and the
    conversation for conversation scope. The condition fingerprint is a
    hash of the whitespace-trimmed, case-folded condition slot. In this
    phase only the empty condition validates upstream, so no
    non-empty rewording ever reaches a durable identity; the hash
    remains so future structured conditions have a stable slot.
    Display text is never consulted.
    """
    if candidate.scope is MemoryScope.USER:
        scope_id = candidate.owner_user_id
    else:
        scope_id = candidate.conversation_id or ""
    fingerprint = hashlib.sha256(
        candidate.condition.strip().casefold().encode("utf-8")
    ).hexdigest()
    return AssertionIdentity(
        owner_user_id=candidate.owner_user_id,
        scope=candidate.scope,
        scope_id=scope_id,
        canonical_key=candidate.canonical_key,
        subject_key=candidate.subject_key,
        condition_fingerprint=fingerprint,
    )
