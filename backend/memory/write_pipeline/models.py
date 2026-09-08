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
    """Scopes the first registry key may live in."""

    USER = "user"
    CONVERSATION = "conversation"


class Cardinality(str, Enum):
    """How many current values one assertion identity may hold."""

    SINGLE = "single"


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
    """Lifecycle states of one assertion version."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"


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
    normalized_value: str
    display_text: str
    authority: Authority | str
    sensitivity: SensitivityBand | str
    condition: str = ""
    subject_key: str = "self"
    observed_at: datetime | None = None

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
            _require_text(self.normalized_value, "normalized_value"),
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
        object.__setattr__(
            self, "subject_key", _require_text(self.subject_key, "subject_key")
        )
        if self.observed_at is None:
            raise ValueError("Field 'observed_at' is required.")
        object.__setattr__(
            self, "observed_at", _require_utc(self.observed_at, "observed_at")
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
    """Deterministic identity of one single-valued assertion.

    Built from owner, scope, key, subject, and condition only, so two
    paraphrases of one value resolve to the same identity.
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
    normalized_value: str
    display_text: str
    authority: Authority | str
    sensitivity: SensitivityBand | str
    status: VersionStatus | str
    valid_from: datetime
    supersedes_version_id: str | None = None

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
            _require_text(self.normalized_value, "normalized_value"),
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
        object.__setattr__(
            self, "valid_from", _require_utc(self.valid_from, "valid_from")
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
    normalized_value: str
    display_text: str
    authority: Authority | str
    sensitivity: SensitivityBand | str
    valid_from: datetime
    status: VersionStatus | str = VersionStatus.ACTIVE
    supersedes_version_id: str | None = None

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
            _require_text(self.normalized_value, "normalized_value"),
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
