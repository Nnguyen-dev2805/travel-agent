"""Risk-based memory command service: NL intents plus confirmable controls.

Confirm-all is superseded. Explicit low-risk remember/correct commits
directly through policy, resolver, and the unit of work, and the
application-owned saved event is built only after the commit returns.
Delete-one commits directly with an undo descriptor. Bulk delete and
conversation-to-user scope expansion travel through bounded one-time
preview tokens that revalidate owner, expected versions, sensitivity,
expiry, and deletion epoch before any commit. Sensitive, restricted,
and prohibited input yields no durable write and no save prompt.

Enable/disable have no durable flag store in this slice: they are
validated, owner-scoped direct acknowledgements with explicit
non-persistent semantics. Responses never claim durable flag
persistence; a later child adds the flag store.

Minimal keyword intent parsing covers governed English and Vietnamese
utterances only and performs no model calls. First-match wins in
correct, remember, delete, enable, disable order; substring matching
can misread adversarial phrasing, so ambiguous multi-value utterances
refuse instead of guessing.
"""

from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from backend.memory.write_pipeline.models import (
    Authority,
    MemoryCandidate,
    MemoryChangeSet,
    MemoryEvidence,
    MemoryOperation,
    MemoryRelation,
    MemoryScope,
    VersionStatus,
    assertion_identity,
    new_candidate_id,
    new_evidence_id,
)
from backend.memory.write_pipeline.policy import (
    Actor,
    DecisionContext,
    DecisionOutcome,
    Origin,
    decide_candidate,
)
from backend.memory.write_pipeline.registry import (
    HOTEL_ATMOSPHERE_KEY,
    HOTEL_ATMOSPHERE_SYNONYMS,
    HotelAtmosphere,
    RegistryValidationError,
    get_key_definition,
    normalize_value,
    validate_against_registry,
)
from backend.memory.write_pipeline.resolver import resolve_change
from backend.memory.write_pipeline.secrets import detect_prohibited_content
from backend.memory.write_pipeline.uow import (
    CrossOwnerDeniedError,
    MemoryUnitOfWork,
    MemoryWriteError,
    MemoryWriteResult,
)
from backend.security.models import AuthenticatedPrincipal

TTL_SECONDS = 600.0
MAX_BULK_TARGETS = 20
MAX_PREVIEWS = 512
COMMAND_ID_PREFIX = "cmd_"
PREVIEW_ID_PREFIX = "mprev_"
DELETION_TARGET_TYPE = "memory_version"

_REMEMBER_MARKERS = (
    "remember",
    "save",
    "prefer",
    "like",
    "ghi nhớ",
    "nhớ",
    "lưu",
    "thích",
)
_CORRECT_MARKERS = (
    "correct",
    "change to",
    "switch to",
    "sửa",
    "đổi sang",
    "actually",
    "thực ra",
)
_DELETE_MARKERS = ("delete", "forget", "remove", "xóa", "xoá", "quên", "loại bỏ")
_ENABLE_MARKERS = ("enable", "turn on", "activate", "bật", "kích hoạt")
_DISABLE_MARKERS = ("disable", "turn off", "deactivate", "tắt", "vô hiệu")
_CONVERSATION_MARKERS = (
    "this chat",
    "current chat",
    "trong chat này",
    "trong cuộc trò chuyện này",
    "conversation",
    "cuộc trò chuyện",
)

_VALUE_TOKENS: tuple[tuple[str, tuple[str, ...]], ...] = tuple(
    (member.value, (member.value,) + HOTEL_ATMOSPHERE_SYNONYMS[member.value])
    for member in HotelAtmosphere
)


class MemoryCommandError(Exception):
    """A memory command could not be understood or completed safely."""


class MemoryCommandValidationError(MemoryCommandError):
    """The command shape itself is invalid; nothing was attempted."""


class MemoryCommandNotFoundError(MemoryCommandError):
    """A referenced preview, token, or version is unknown, spent, or expired."""


class MemoryCommandStaleError(MemoryCommandError):
    """State moved under a preview; re-request instead of committing."""


@dataclass(frozen=True)
class ParsedIntent:
    """One parsed utterance: action, normalized value, scope, ambiguity."""

    action: str
    value: str | None = None
    scope: str | None = None
    ambiguous: bool = False


@dataclass(frozen=True)
class UndoDescriptor:
    """A compensating action the caller may offer as Undo (never auto-run)."""

    action: str
    version_ids: tuple[str, ...]
    note: str


@dataclass(frozen=True)
class SavedEvent:
    """Application-owned save acknowledgement, built only after commit."""

    operation: str
    scope: str
    canonical_key: str
    normalized_value: str
    version_id: str


@dataclass(frozen=True)
class DeletedEvent:
    """Application-owned delete acknowledgement with its undo descriptor."""

    deleted_version_ids: tuple[str, ...]
    undo: UndoDescriptor


@dataclass(frozen=True)
class BulkCommitted:
    """Committed bulk delete with per-target undo coverage."""

    operation: str
    committed_version_ids: tuple[str, ...]
    undo: UndoDescriptor


@dataclass(frozen=True)
class ToggledEvent:
    """Direct toggle acknowledgement with explicit non-persistent semantics."""

    action: str
    effective: bool
    persistent: bool
    note: str
    undo: UndoDescriptor


@dataclass(frozen=True)
class HeldEvent:
    """Sensitive content held: no durable write and no save prompt."""

    reason: str


@dataclass(frozen=True)
class PendingEvent:
    """Ambiguous conflict held for later relevance; nothing mutated."""

    reason: str


@dataclass(frozen=True)
class RefusedEvent:
    """Rejected input; nothing was attempted and nothing is stored."""

    reason: str


@dataclass(frozen=True)
class PreviewTarget:
    """One governed target shown on a preview exactly as it will commit."""

    version_id: str
    canonical_key: str
    normalized_value: str
    scope: str
    old_scope: str | None = None
    new_scope: str | None = None


@dataclass(frozen=True)
class PreviewDisplay:
    """Exact operation/scope content a confirmation screen renders."""

    operation: str
    targets: tuple[PreviewTarget, ...]
    expires_in_seconds: float


@dataclass(frozen=True)
class PreviewOffer:
    """A pending bounded preview plus its one-time confirmation token."""

    preview_id: str
    token: str
    display: PreviewDisplay


@dataclass(frozen=True)
class _PreviewRecord:
    preview_id: str
    token: str
    owner_user_id: str
    operation: str
    target_ids: tuple[str, ...]
    expected_active_ids: tuple[str, ...]
    sensitivities: tuple[str, ...]
    created_mono: float
    expires_mono: float
    deletion_epoch: int
    payload_hash: str = ""
    old_scope: str | None = None
    new_scope: str | None = None


def _mentions(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def parse_utterance(text: Any) -> ParsedIntent:
    """Map one utterance to a governed intent without any model call."""
    if not isinstance(text, str) or not text.strip():
        raise MemoryCommandValidationError("An utterance must be non-blank text.")
    lowered = text.strip().casefold()
    if _mentions(lowered, _CORRECT_MARKERS):
        action = "correct"
    elif _mentions(lowered, _REMEMBER_MARKERS):
        action = "remember"
    elif _mentions(lowered, _DELETE_MARKERS):
        action = "delete"
    elif _mentions(lowered, _ENABLE_MARKERS):
        action = "enable"
    elif _mentions(lowered, _DISABLE_MARKERS):
        action = "disable"
    else:
        return ParsedIntent(action="unknown")
    if action in ("enable", "disable"):
        return ParsedIntent(action=action)
    found = [
        value
        for value, tokens in _VALUE_TOKENS
        if any(token.casefold() in lowered for token in tokens)
    ]
    if len(found) > 1:
        return ParsedIntent(action=action, ambiguous=True)
    value = found[0] if found else None
    scope = (
        MemoryScope.CONVERSATION.value
        if _mentions(lowered, _CONVERSATION_MARKERS)
        else None
    )
    return ParsedIntent(action=action, value=value, scope=scope)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _command_id() -> str:
    return f"{COMMAND_ID_PREFIX}{uuid.uuid4().hex}"


class MemoryCommandService:
    """Risk-based memory commands over policy, resolver, and the UoW."""

    def __init__(
        self,
        *,
        uow: MemoryUnitOfWork,
        read_versions: Callable,
        list_active_versions: Callable,
        commit_delete_one: Callable,
        commit_bulk_delete: Callable,
        clock=time.monotonic,
        ttl_seconds: float = TTL_SECONDS,
        max_bulk_targets: int = MAX_BULK_TARGETS,
    ) -> None:
        self._uow = uow
        self._read_versions = read_versions
        self._list_active_versions = list_active_versions
        self._commit_delete_one = commit_delete_one
        self._commit_bulk_delete = commit_bulk_delete
        self._clock = clock
        self._ttl_seconds = ttl_seconds
        self._max_bulk_targets = max_bulk_targets
        self._previews: dict[str, _PreviewRecord] = {}
        self._deletion_epoch = 0

    def handle_utterance(
        self,
        principal: AuthenticatedPrincipal,
        text: Any,
        *,
        conversation_id: str | None = None,
        scope: str | None = None,
        idempotency_key: str | None = None,
    ):
        """Handle one NL memory utterance end to end."""
        owner = principal.owner_user_id
        intent = parse_utterance(text)
        if detect_prohibited_content(text if isinstance(text, str) else "") is not None:
            return RefusedEvent(reason="prohibited_content")
        if intent.action == "unknown":
            return RefusedEvent(reason="unknown_intent")
        if intent.ambiguous:
            return RefusedEvent(reason="ambiguous_value")
        if intent.action in ("enable", "disable"):
            return self._toggle(intent.action)
        if intent.action == "delete":
            return self._delete_by_intent(principal, intent)
        return self._remember_or_correct(
            principal,
            intent,
            conversation_id=conversation_id,
            scope=scope,
            idempotency_key=idempotency_key,
            utterance=text,
        )

    def record_shadow_candidate(
        self,
        principal: AuthenticatedPrincipal,
        candidate: MemoryCandidate,
        evidence: MemoryEvidence,
        *,
        context: DecisionContext | None = None,
        idempotency_key: str | None = None,
    ) -> MemoryWriteResult:
        """Record a background-extracted candidate strictly as shadow evidence.

        Enforces hard invariants:
        - Must never create active versions (MemoryOperation.NOOP).
        - Revalidates owner boundary on principal, candidate, and evidence.
        - Outcomes restricted to SHADOW, HELD_SENSITIVE, REJECTED, or INVALID.
        """
        owner = principal.owner_user_id
        if candidate.owner_user_id != owner:
            raise CrossOwnerDeniedError(
                "Candidate owner does not match authenticated principal."
            )
        if evidence.owner_user_id != owner:
            raise CrossOwnerDeniedError(
                "Evidence owner does not match authenticated principal."
            )

        if context is None:
            context = DecisionContext(
                actor=Actor.USER,
                authenticated=True,
                origin=Origin.BACKGROUND_CHAT,
                source_deleted=False,
            )

        decision = decide_candidate(candidate, context)

        # Invariant: background extraction MUST NOT create active versions
        allowed_outcomes = {
            DecisionOutcome.SHADOW,
            DecisionOutcome.HELD_SENSITIVE,
            DecisionOutcome.REJECTED,
            DecisionOutcome.INVALID,
        }
        if decision.outcome not in allowed_outcomes:
            raise MemoryWriteError(
                f"Background extraction produced disallowed outcome '{decision.outcome}'."
            )

        change = MemoryChangeSet(
            operation=MemoryOperation.NOOP,
            identity=assertion_identity(candidate),
            new_version=None,
            superseded_version_ids=(),
            reference_version_id=None,
            reason=decision.reason.value if hasattr(decision.reason, "value") else str(decision.reason),
        )

        return self._uow.apply_memory_change(
            change,
            principal,
            evidence=(evidence,),
            decision=decision,
            idempotency_key=idempotency_key,
        )

    def list_memories(self, principal, scope: str | None = None):
        """List one owner's active memories, optionally scope-filtered."""
        owner = principal.owner_user_id
        versions = self._list_active_versions(owner)
        if scope is not None:
            versions = tuple(item for item in versions if item.scope.value == scope)
        return versions

    def delete_versions(self, principal, version_ids):
        """Delete one version directly or open a bulk preview for many."""
        owner = principal.owner_user_id
        identities = tuple(
            item.strip() for item in (version_ids or ()) if isinstance(item, str)
        )
        identities = tuple(item for item in identities if item)
        if not identities:
            raise MemoryCommandValidationError("At least one version id is required.")
        if len(identities) > self._max_bulk_targets:
            raise MemoryCommandValidationError("Too many versions for one delete.")
        actives = {item.version_id: item for item in self._list_active_versions(owner)}
        missing = [item for item in identities if item not in actives]
        if missing:
            raise MemoryCommandNotFoundError("The memory entry does not exist.")
        if len(identities) == 1:
            undo = self._commit_delete_one(owner, identities[0], "user_delete")
            self._deletion_epoch += 1
            return DeletedEvent(deleted_version_ids=identities, undo=undo)
        return self._new_preview(
            owner, "bulk_delete", [actives[item] for item in identities]
        )

    def preview_scope_expansion(self, principal, version_id: str):
        """Open a scoped preview widening one conversation version to user."""
        owner = principal.owner_user_id
        if not isinstance(version_id, str) or not version_id.strip():
            raise MemoryCommandValidationError("A version id is required.")
        actives = {item.version_id: item for item in self._list_active_versions(owner)}
        target = actives.get(version_id.strip())
        if target is None:
            raise MemoryCommandNotFoundError("The memory entry does not exist.")
        if target.scope is not MemoryScope.CONVERSATION:
            raise MemoryCommandValidationError("Only conversation scope expands.")
        return self._new_preview(
            owner,
            "scope_expansion",
            [target],
            old_scope=target.scope.value,
            new_scope=MemoryScope.USER.value,
        )

    def confirm_preview(self, principal, preview_id: str, token: str):
        """Revalidate all five preview bindings, then commit exactly once."""
        owner = principal.owner_user_id
        record = self._previews.get(token) if isinstance(token, str) else None
        if record is None or record.preview_id != preview_id:
            raise MemoryCommandNotFoundError("The preview is unknown or spent.")
        if record.owner_user_id != owner:
            raise CrossOwnerDeniedError(
                "The preview does not belong to this owner scope."
            )
        if self._clock() >= record.expires_mono:
            self._previews.pop(token, None)
            raise MemoryCommandNotFoundError("The preview is unknown or spent.")
        if record.deletion_epoch != self._deletion_epoch:
            self._previews.pop(token, None)
            raise MemoryCommandStaleError("Memory changed; request a new preview.")
        actives = {item.version_id: item for item in self._list_active_versions(owner)}
        if any(item not in actives for item in record.target_ids):
            self._previews.pop(token, None)
            raise MemoryCommandStaleError("Memory changed; request a new preview.")
        live_sensitivities = tuple(
            actives[item].sensitivity.value for item in record.target_ids
        )
        if live_sensitivities != record.sensitivities:
            self._previews.pop(token, None)
            raise MemoryCommandStaleError("Memory changed; request a new preview.")
        if record.operation == "bulk_delete":
            undo = self._commit_bulk_delete(owner, record.target_ids, "bulk_delete")
            self._deletion_epoch += 1
            self._previews.pop(token, None)
            return BulkCommitted(
                operation="bulk_delete",
                committed_version_ids=record.target_ids,
                undo=undo,
            )
        if record.operation == "scope_expansion":
            result = self._commit_expansion(principal, actives[record.target_ids[0]])
            self._previews.pop(token, None)
            return result
        raise MemoryCommandNotFoundError(
            "The preview is unknown or spent."
        )  # pragma: no cover

    # Internal flows.

    def _toggle(self, action: str):
        effective = action == "enable"
        inverse = "disable" if effective else "enable"
        return ToggledEvent(
            action=action,
            effective=effective,
            persistent=False,
            note=(
                "Toggle state is session-local in this slice: no durable "
                "flag store exists yet, so this acknowledgement is "
                "non-persistent by design."
            ),
            undo=UndoDescriptor(
                action=inverse, version_ids=(), note="Re-send to reverse."
            ),
        )

    def _delete_by_intent(self, principal, intent: ParsedIntent):
        owner = principal.owner_user_id
        actives = self._list_active_versions(owner)
        if intent.value is not None:
            actives = tuple(
                item for item in actives if item.normalized_value == intent.value
            )
        if intent.scope is not None:
            actives = tuple(
                item for item in actives if item.scope.value == intent.scope
            )
        if not actives:
            return RefusedEvent(reason="no_match")
        if len(actives) == 1:
            undo = self._commit_delete_one(owner, actives[0].version_id, "user_delete")
            self._deletion_epoch += 1
            return DeletedEvent(deleted_version_ids=(actives[0].version_id,), undo=undo)
        if len(actives) > self._max_bulk_targets:
            return RefusedEvent(reason="bulk_too_large")
        return self._new_preview(owner, "bulk_delete", list(actives))

    def _remember_or_correct(
        self,
        principal,
        intent: ParsedIntent,
        *,
        conversation_id,
        scope,
        idempotency_key,
        utterance,
    ):

        owner = principal.owner_user_id
        if intent.value is None:
            return RefusedEvent(reason="no_value")
        resolved_scope = scope or intent.scope or MemoryScope.USER.value
        if resolved_scope not in (
            MemoryScope.USER.value,
            MemoryScope.CONVERSATION.value,
        ):
            raise MemoryCommandValidationError("Scope must be user or conversation.")
        if resolved_scope == MemoryScope.CONVERSATION.value and not (
            isinstance(conversation_id, str) and conversation_id.strip()
        ):
            raise MemoryCommandValidationError(
                "Conversation scope needs a conversation."
            )
        command_id = _command_id()
        evidence = ()
        evidence_ids: tuple[str, ...] = ()
        if isinstance(conversation_id, str) and conversation_id.strip():
            evidence = (
                MemoryEvidence(
                    evidence_id=new_evidence_id(),
                    owner_user_id=owner,
                    conversation_id=conversation_id.strip(),
                    source_message_id=command_id,
                    display_text=_bound_text(utterance),
                    authority=Authority.EXPLICIT_STATEMENT,
                    observed_at=_utc_now(),
                ),
            )
            evidence_ids = (evidence[0].evidence_id,)
        candidate = MemoryCandidate(
            candidate_id=new_candidate_id(),
            evidence_ids=evidence_ids,
            owner_user_id=owner,
            scope=resolved_scope,
            conversation_id=(
                conversation_id.strip()
                if isinstance(conversation_id, str) and conversation_id.strip()
                else None
            ),
            canonical_key=HOTEL_ATMOSPHERE_KEY,
            normalized_value=normalize_value(HOTEL_ATMOSPHERE_KEY, intent.value),
            display_text=_bound_text(utterance),
            authority=Authority.EXPLICIT_SAVE,
            sensitivity=get_key_definition(HOTEL_ATMOSPHERE_KEY).minimum_sensitivity,
            observed_at=_utc_now(),
        )
        try:
            validate_against_registry(candidate)
        except RegistryValidationError as error:
            return RefusedEvent(reason=f"invalid_{error.reason}")
        decision = decide_candidate(
            candidate,
            DecisionContext(
                actor=Actor.USER,
                authenticated=True,
                origin=Origin.EXPLICIT_COMMAND,
                source_deleted=False,
            ),
        )
        if decision.outcome is not DecisionOutcome.DIRECT_WRITE:
            if decision.outcome is DecisionOutcome.HELD_SENSITIVE:
                return HeldEvent(reason=decision.reason.value)
            if decision.outcome is DecisionOutcome.SHADOW:
                return HeldEvent(reason=decision.reason.value)
            return RefusedEvent(reason=decision.reason.value)
        identity = assertion_identity(candidate)
        current = self._read_versions(identity)
        relation, extra = self._derive_relation(principal, candidate, current)
        current = current + extra

        change = resolve_change(candidate, current, relation)
        if change.operation is MemoryOperation.PENDING_CONFLICT:
            return PendingEvent(reason=change.reason)
        if change.operation in (MemoryOperation.REJECT, MemoryOperation.NOOP):
            return RefusedEvent(reason=change.reason)
        expected = None
        if change.operation is MemoryOperation.SUPERSEDE:
            expected = change.superseded_version_ids[0]
        elif change.operation is MemoryOperation.REINFORCE:
            expected = change.reference_version_id
        result = self._uow.apply_memory_change(
            change,
            principal,
            evidence=evidence,
            decision=decision,
            idempotency_key=idempotency_key or command_id,
            expected_version_id=expected,
        )
        return SavedEvent(
            operation=result.operation.value,
            scope=candidate.scope.value,
            canonical_key=candidate.canonical_key,
            normalized_value=candidate.normalized_value,
            version_id=result.version_id or result.reference_version_id or "",
        )

    def _derive_relation(self, principal, candidate, current):

        if candidate.scope is MemoryScope.CONVERSATION:
            defaults = tuple(
                item
                for item in self._list_active_versions(principal.owner_user_id)
                if item.scope is MemoryScope.USER
                and item.status is VersionStatus.ACTIVE
                and item.canonical_key == candidate.canonical_key
                and item.owner_user_id == principal.owner_user_id
            )
            if defaults and not any(
                item.scope is MemoryScope.CONVERSATION for item in current
            ):
                # The resolver links the exception against the live user
                # default, which lives under a different identity: hand
                # it over explicitly alongside the conversation history.
                return MemoryRelation.SCOPE_EXCEPTION, defaults
        if not current:
            return MemoryRelation.UNRELATED, ()
        actives = tuple(item for item in current if item.status is VersionStatus.ACTIVE)
        if any(item.normalized_value == candidate.normalized_value for item in actives):
            return MemoryRelation.SAME, ()
        return MemoryRelation.CONTRADICTION, ()

    def _commit_expansion(self, principal, target):
        owner = principal.owner_user_id
        user_actives = tuple(
            item
            for item in self._list_active_versions(owner)
            if item.scope is MemoryScope.USER
            and item.canonical_key == target.canonical_key
            and item.status is VersionStatus.ACTIVE
        )
        if user_actives:
            raise MemoryCommandStaleError("Memory changed; request a new preview.")
        candidate = MemoryCandidate(
            candidate_id=new_candidate_id(),
            evidence_ids=(),
            owner_user_id=owner,
            scope=MemoryScope.USER.value,
            conversation_id=None,
            canonical_key=target.canonical_key,
            normalized_value=target.normalized_value,
            display_text=target.normalized_value,
            authority=Authority.EXPLICIT_SAVE,
            sensitivity=target.sensitivity,
            observed_at=_utc_now(),
        )
        decision = decide_candidate(
            candidate,
            DecisionContext(
                actor=Actor.USER,
                authenticated=True,
                origin=Origin.EXPLICIT_COMMAND,
                source_deleted=False,
            ),
        )
        if decision.outcome is not DecisionOutcome.DIRECT_WRITE:
            raise MemoryCommandStaleError("Memory changed; request a new preview.")

        identity = assertion_identity(candidate)
        change = resolve_change(
            candidate, self._read_versions(identity), MemoryRelation.UNRELATED
        )
        result = self._uow.apply_memory_change(
            change,
            principal,
            evidence=(),
            decision=decision,
            idempotency_key=_command_id(),
            expected_version_id=None,
        )
        # Tombstone the old conversation version so it does not linger as duplicate
        self._commit_delete_one(owner, target.version_id, "scope_expansion")
        self._deletion_epoch += 1
        return SavedEvent(
            operation=result.operation.value,
            scope=candidate.scope.value,
            canonical_key=candidate.canonical_key,
            normalized_value=candidate.normalized_value,
            version_id=result.version_id or "",
        )

    def _new_preview(
        self,
        owner: str,
        operation: str,
        targets,
        *,
        old_scope: str | None = None,
        new_scope: str | None = None,
    ) -> PreviewOffer:
        self._sweep_expired()
        if len(self._previews) >= MAX_PREVIEWS:
            oldest = min(self._previews.values(), key=lambda item: item.created_mono)
            self._previews.pop(oldest.token, None)
        preview_id = f"{PREVIEW_ID_PREFIX}{uuid.uuid4().hex}"
        token = secrets.token_urlsafe(32)
        now = self._clock()
        display_targets = tuple(
            PreviewTarget(
                version_id=item.version_id,
                canonical_key=item.canonical_key,
                normalized_value=item.normalized_value,
                scope=item.scope.value,
                old_scope=old_scope,
                new_scope=new_scope,
            )
            for item in targets
        )
        target_ids = tuple(item.version_id for item in targets)
        payload_material = f"{operation}:{','.join(target_ids)}:{old_scope}:{new_scope}"
        payload_hash = hashlib.sha256(payload_material.encode("utf-8")).hexdigest()
        record = _PreviewRecord(
            preview_id=preview_id,
            token=token,
            owner_user_id=owner,
            operation=operation,
            target_ids=target_ids,
            expected_active_ids=target_ids,
            sensitivities=tuple(item.sensitivity.value for item in targets),
            created_mono=now,
            expires_mono=now + self._ttl_seconds,
            deletion_epoch=self._deletion_epoch,
            payload_hash=payload_hash,
            old_scope=old_scope,
            new_scope=new_scope,
        )
        self._previews[token] = record
        return PreviewOffer(
            preview_id=preview_id,
            token=token,
            display=PreviewDisplay(
                operation=operation,
                targets=display_targets,
                expires_in_seconds=self._ttl_seconds,
            ),
        )

    def _sweep_expired(self) -> None:
        now = self._clock()
        for token in [
            token for token, item in self._previews.items() if now >= item.expires_mono
        ]:
            self._previews.pop(token, None)


def _bound_text(value: Any) -> str:
    text = value.strip() if isinstance(value, str) else ""
    return text[:500] if text else "command"
