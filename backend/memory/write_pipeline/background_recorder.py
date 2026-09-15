"""Narrow background recording interface for semantic memory.

Per ADR 0020, ADR 0021, and ADR 0022, background extraction is strictly separated
from user-initiated memory management. Background extraction produces shadow
observations only and never creates active versions or confirmable proposals.

BackgroundMemoryRecorder provides a single write-pipeline entry point:
`record(candidate: ShadowCandidate) -> BackgroundRecordResult`.
It exposes NO user-initiated methods (no remember, correct, forget, toggle, preview, confirm, expand).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import logging
from typing import TYPE_CHECKING, Any, Callable, Sequence

if TYPE_CHECKING:
    from backend.memory.lifecycle import (
        MemoryLifecyclePolicy,
        RetentionAssignmentPolicy,
    )

from backend.memory.activation import (
    ActivationFacts,
    ActivationReason,
    MemoryActivationPolicy,
)
from backend.memory.commit_coordinators import (
    BackgroundMemoryCommit,
    BackgroundMemoryCommitRequest,
)
from backend.memory.source_handling import (
    MemoryFamily,
    SourceHandlingRecord,
    allows_background_formation,
)
from backend.memory.write_pipeline.outbox import (
    MEMORY_FAMILY_BY_EVENT_TYPE,
)
from backend.memory.write_pipeline.models import (
    AssertionIdentity,
    Authority,
    DecisionOutcome,
    EvidenceIdentity,
    MemoryCandidate,
    MemoryChangeSet,
    MemoryEvidence,
    MemoryOperation,
    MemoryRelation,
    MemoryScope,
    SourceValidity,
    MemoryVersion,
    SensitivityBand,
    VersionStatus,
    assertion_identity,
    new_candidate_id,
    new_evidence_id,
    CANDIDATE_ID_PREFIX,
    EVIDENCE_ID_PREFIX,
)
from backend.memory.write_pipeline.policy import (
    Actor,
    DecisionContext,
    Origin,
    decide_candidate,
)
from backend.memory.write_pipeline.registry import get_key_definition
from backend.memory.write_pipeline.resolver import resolve_change
from backend.memory.write_pipeline.uow import FenceContext, MemoryUnitOfWork
from backend.security.models import AuthenticatedPrincipal, AuthMode

logger = logging.getLogger("travel_agent_memory_recorder")

MIN_CONFIDENCE_THRESHOLD = 0.5


def _enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _semantic_idempotency_key(
    *,
    source_outbox_id: str | None,
    identity: AssertionIdentity | None,
    normalized_value: str,
    operation: str,
) -> str:
    """Derive a stable idempotency key from the semantic effect.

    The per-extraction candidate id is deliberately excluded: model
    extraction mints fresh ids on every run, so keying on it would let a
    redelivered outbox event write the same observation twice. The same
    source event resolving to the same identity, value, and operation
    always yields the same key.
    """
    material = "|".join(
        [
            source_outbox_id or "",
            identity.owner_user_id if identity is not None else "",
            _enum_value(identity.scope) if identity is not None else "",
            identity.scope_id if identity is not None else "",
            identity.canonical_key if identity is not None else "",
            identity.subject_key if identity is not None else "",
            identity.condition_fingerprint if identity is not None else "",
            normalized_value,
            operation,
        ]
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]
    return f"bg_{digest}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _no_key_has_a_conclusive_evaluation(_canonical_key: str) -> bool:
    """Fail-closed default for the per-key/type promotion gate (R5).

    Active inferred Memory requires a conclusive passing evaluation *for that
    semantic key/type*. No such per-key evaluation exists yet, so the honest
    answer is `False` for every key — not `True` by omission. A deployment that
    completes a per-key evaluation supplies its own gate to the recorder.
    """
    return False


@dataclass(frozen=True)
class ShadowCandidate:
    """Input candidate for background memory recording."""

    candidate_id: str
    owner_user_id: str
    canonical_key: str
    normalized_value: Any
    display_text: str
    authority: Authority = Authority.REPEATED_INFERENCE
    sensitivity: SensitivityBand = SensitivityBand.ORDINARY_PERSONAL
    scope: MemoryScope = MemoryScope.USER
    scope_id: str = "global"
    confidence: float = 1.0
    subject_key: str | None = None
    relation: MemoryRelation = MemoryRelation.UNRELATED
    condition_fingerprint: str | None = None
    observed_at: datetime | None = None
    conversation_id: str | None = None
    source_message_id: str | None = None


@dataclass(frozen=True)
class BackgroundRecordResult:
    """Outcome of one background memory recording attempt."""

    status: str  # "recorded", "held_sensitive", "rejected", "low_confidence"
    candidate_id: str
    decision_outcome: DecisionOutcome
    operation: MemoryOperation
    reason: str
    write_result: Any = None
    target_status: VersionStatus = VersionStatus.SHADOW
    #: Set when the commit is deferred to the coordinator. The coordinator is
    #: invoked once per outbox event, so a prepared result carries its request
    #: until every candidate of that event has been prepared.
    pending_commit: BackgroundMemoryCommitRequest | None = None


class BackgroundMemoryRecorder:
    """Narrow background recording service for shadow memory extraction and semantic activation.

    Coordinates:
    - Positive source handling authority gate
    - Pre-model secret scan / confidence filtering
    - Policy evaluation (decide_candidate)
    - Conflict and cardinality resolution (resolve_change)
    - Lifecycle eligibility evaluation at LifecycleStage.ACTIVATION
    - Semantic activation evaluation (MemoryActivationPolicy)
    - Atomic persistence through BackgroundMemoryCommit or MemoryUnitOfWork
    """

    def __init__(
        self,
        policy: Any = None,
        resolver: Any = None,
        uow_factory: Callable[[], MemoryUnitOfWork] | MemoryUnitOfWork | None = None,
        *,
        uow: MemoryUnitOfWork | None = None,
        min_confidence: float = MIN_CONFIDENCE_THRESHOLD,
        commit_coordinator: BackgroundMemoryCommit | None = None,
        activation_policy: MemoryActivationPolicy | None = None,
        lifecycle_policy: MemoryLifecyclePolicy | None = None,
        retention_policy: RetentionAssignmentPolicy | None = None,
        source_handling_loader: Callable[[str, str, Any], SourceHandlingRecord | None] | None = None,
        inferred_activation_enabled: bool = False,
        type_evaluation_gate: Callable[[str], bool] | None = None,
    ) -> None:
        self._policy = policy if policy is not None else decide_candidate
        self._resolver = resolver if resolver is not None else resolve_change
        resolved_uow = uow_factory if uow_factory is not None else uow
        if resolved_uow is None:
            raise ValueError("uow_factory or uow must be provided")
        self._uow_factory = (
            resolved_uow if callable(resolved_uow) else lambda: resolved_uow
        )
        self._min_confidence = min_confidence
        self._commit_coordinator = commit_coordinator
        self._activation_policy = activation_policy or MemoryActivationPolicy()
        if lifecycle_policy is not None:
            self._lifecycle_policy = lifecycle_policy
        else:
            from backend.memory.lifecycle import MemoryLifecyclePolicy

            self._lifecycle_policy = MemoryLifecyclePolicy()

        if retention_policy is not None:
            self._retention_policy = retention_policy
        else:
            from backend.memory.lifecycle import RetentionAssignmentPolicy

            self._retention_policy = RetentionAssignmentPolicy()

        self._source_handling_loader = source_handling_loader
        self._inferred_activation_enabled = inferred_activation_enabled
        # Per-key/type promotion gate (R5). Injected rather than defaulted open:
        # a recorder that cannot prove a key has a conclusive evaluation must not
        # treat the absence of evidence as a pass.
        self._type_evaluation_gate = (
            type_evaluation_gate
            if type_evaluation_gate is not None
            else _no_key_has_a_conclusive_evaluation
        )

    def _to_memory_candidate(
        self, candidate: ShadowCandidate | MemoryCandidate
    ) -> MemoryCandidate:
        if isinstance(candidate, MemoryCandidate):
            return candidate
        cid = candidate.candidate_id or new_candidate_id()
        if not cid.startswith(CANDIDATE_ID_PREFIX):
            cid = f"{CANDIDATE_ID_PREFIX}{cid}"
        ev_id = getattr(candidate, "source_message_id", None) or new_evidence_id()
        if not ev_id.startswith(EVIDENCE_ID_PREFIX):
            ev_id = f"{EVIDENCE_ID_PREFIX}{ev_id}"
        return MemoryCandidate(
            candidate_id=cid,
            evidence_ids=(ev_id,),
            owner_user_id=candidate.owner_user_id,
            scope=candidate.scope,
            conversation_id=getattr(candidate, "conversation_id", None),
            canonical_key=candidate.canonical_key,
            normalized_value=str(candidate.normalized_value),
            display_text=candidate.display_text,
            authority=candidate.authority,
            sensitivity=candidate.sensitivity,
            condition=getattr(candidate, "condition", "") or "",
            subject_key=getattr(candidate, "subject_key", None) or "self",
            observed_at=candidate.observed_at or _utc_now(),
            confidence=candidate.confidence,
        )

    def _prepare_core(
        self,
        candidate: ShadowCandidate | MemoryCandidate,
        source_outbox_id: str | None = None,
        source_message_id: str | None = None,
        conversation_id: str | None = None,
        fence: FenceContext | None = None,
        source_handling_record: SourceHandlingRecord | None = None,
        source_validity: SourceValidity = SourceValidity.VALID,
        event_type: str | None = None,
    ) -> BackgroundRecordResult:
        """Prepare one candidate's outcome without committing it.

        Returns a result that is final for every refusal path, and that carries a
        `pending_commit` request when the coordinator must be invoked. Keeping
        preparation and commit separate is what lets one outbox event with several
        candidates be committed once.
        """
        # 1. Confidence check
        confidence = candidate.confidence
        if confidence < self._min_confidence:
            return BackgroundRecordResult(
                status="low_confidence",
                candidate_id=candidate.candidate_id,
                decision_outcome=DecisionOutcome.REJECTED,
                operation=MemoryOperation.NOOP,
                reason=f"confidence_{confidence:.2f}_below_threshold_{self._min_confidence:.2f}",
                target_status=VersionStatus.SHADOW,
            )

        mem_candidate = self._to_memory_candidate(candidate)

        # 2. Source handling authority gate
        sh_record = source_handling_record
        if sh_record is None and self._source_handling_loader is not None:
            # The fence already carries the authoritative outbox id, and
            # `record_sync` proves it agrees with `source_outbox_id` when both are
            # supplied. Falling back to it means a fence-only caller is judged on
            # its source handling rather than refused for want of a lookup key.
            lookup_outbox_id = (
                source_outbox_id
                if source_outbox_id is not None
                else (fence.outbox_id if fence is not None else None)
            )
            if lookup_outbox_id is not None:
                sh_record = self._source_handling_loader(
                    mem_candidate.owner_user_id,
                    lookup_outbox_id,
                    MEMORY_FAMILY_BY_EVENT_TYPE.get(
                        event_type, MemoryFamily.SEMANTIC
                    ),
                )

        # Absence is `UNHANDLED`, and `UNHANDLED` is not permission (ADR 0038:59,
        # plan constraint 8). The first implementation read
        # `if sh_record is not None and not allows_background_formation(...)`,
        # which let a source with no persisted record through the gate — the one
        # input the gate exists to refuse. `allows_background_formation` already
        # denies `None`, so the call must be unconditional.
        if not allows_background_formation(sh_record):
            return BackgroundRecordResult(
                status="rejected",
                candidate_id=candidate.candidate_id,
                decision_outcome=DecisionOutcome.REJECTED,
                operation=MemoryOperation.NOOP,
                reason="source_handling_denied",
                target_status=VersionStatus.SHADOW,
            )

        # 3. Policy check
        ctx = DecisionContext(
            actor=Actor.USER,
            authenticated=True,
            origin=Origin.BACKGROUND_CHAT,
            source_deleted=False,
        )
        if callable(self._policy):
            decision = self._policy(mem_candidate, ctx)
        else:
            decision = self._policy.decide(mem_candidate, ctx)

        # Non-storable or rejected candidates cause NO mutation
        if decision.outcome in (DecisionOutcome.REJECTED, DecisionOutcome.INVALID):
            reason_str = _enum_value(decision.reason)
            return BackgroundRecordResult(
                status="rejected",
                candidate_id=candidate.candidate_id,
                decision_outcome=decision.outcome,
                operation=MemoryOperation.NOOP,
                reason=reason_str,
                target_status=VersionStatus.SHADOW,
            )

        if decision.outcome == DecisionOutcome.HELD_SENSITIVE:
            reason_str = _enum_value(decision.reason)
            return BackgroundRecordResult(
                status="held_sensitive",
                candidate_id=candidate.candidate_id,
                decision_outcome=decision.outcome,
                operation=MemoryOperation.NOOP,
                reason=reason_str,
                target_status=VersionStatus.SHADOW,
            )

        # 4. Resolve candidate against existing active versions
        uow = self._uow_factory()
        existing_versions = tuple(
            uow.get_active_versions(
                mem_candidate.owner_user_id, mem_candidate.canonical_key
            )
        )

        relation = getattr(candidate, "relation", None) or MemoryRelation.UNRELATED
        if callable(self._resolver):
            try:
                resolved_change = self._resolver(
                    mem_candidate, existing_versions, relation
                )
            except TypeError:
                resolved_change = self._resolver(mem_candidate, existing_versions)
        else:
            try:
                resolved_change = self._resolver.resolve(
                    mem_candidate, existing_versions, relation
                )
            except TypeError:
                resolved_change = self._resolver.resolve(
                    mem_candidate, existing_versions
                )

        identity = (
            resolved_change.identity
            if resolved_change.identity is not None
            else assertion_identity(mem_candidate)
        )

        conv_id = (
            getattr(candidate, "conversation_id", None)
            or conversation_id
            or "cv_unknown"
        )
        msg_id = (
            getattr(candidate, "source_message_id", None)
            or source_message_id
            or (sh_record.source_message_id if sh_record else None)
            or "ms_unknown"
        )
        evidence = MemoryEvidence(
            evidence_id=new_evidence_id(),
            owner_user_id=mem_candidate.owner_user_id,
            conversation_id=conv_id,
            source_message_id=msg_id,
            display_text=mem_candidate.display_text,
            authority=mem_candidate.authority,
            observed_at=mem_candidate.observed_at or _utc_now(),
        )
        cand_ev_identity = EvidenceIdentity(
            evidence_id=evidence.evidence_id,
            conversation_id=evidence.conversation_id or "",
            source_message_id=evidence.source_message_id or "",
        )

        # 5. Load prior active evidence, the assertion identity, and the
        # authoritative conflict state. These are declared seams on
        # `MemoryUnitOfWork`, so they are called directly: an earlier revision
        # probed with `hasattr`, which turned a missing capability into a
        # silently empty history instead of a type error (C8).
        assertion_id, has_unresolved_conflict = uow.get_assertion_identity_details(
            identity
        )

        active_evidence: Sequence[EvidenceIdentity] = ()
        if assertion_id is not None:
            active_evidence = uow.get_active_evidence_for_assertion(
                identity.owner_user_id, assertion_id
            )

        # 6. Lifecycle eligibility evaluation at ACTIVATION stage.
        #
        # Every fact below is read from canonical state. The first revision
        # hard-coded both generations to 1 and the source validity to VALID,
        # which made `STALE_GENERATION` structurally unsatisfiable and
        # `SOURCE_INVALID` unreachable at the one stage whose job is to refuse
        # those inputs. It also swallowed a failed retention assignment and
        # substituted a local default — naming a `RetentionMode` member that does
        # not exist.
        cand_scope = mem_candidate.scope
        cand_sensitivity = mem_candidate.sensitivity
        cand_authority = mem_candidate.authority
        try:
            retention_mode = self._retention_policy.assign(
                scope=cand_scope,
                authority=cand_authority,
            )
        except ValueError:
            # Assignment is a privacy decision and has no default. An ungoverned
            # pair means a vocabulary grew without the table growing with it,
            # which must be refused rather than guessed.
            return BackgroundRecordResult(
                status="rejected",
                candidate_id=candidate.candidate_id,
                decision_outcome=DecisionOutcome.REJECTED,
                operation=MemoryOperation.NOOP,
                reason="retention_ungoverned",
                target_status=VersionStatus.SHADOW,
            )

        current_generation = uow.get_assertion_generation(
            identity.owner_user_id, identity.canonical_key
        )
        key_definition = get_key_definition(mem_candidate.canonical_key)

        from backend.memory.lifecycle import LifecycleFacts, LifecycleStage

        lifecycle_facts = LifecycleFacts(
            retention_mode=retention_mode,
            stamped_generation=mem_candidate.suppression_generation,
            current_generation=current_generation,
            scope=cand_scope,
            sensitivity=cand_sensitivity,
            source_validity=source_validity,
            # The registry's own constraints, so the stage re-checks the scope and
            # sensitivity floor it is the owner of rather than trusting that the
            # caller already did.
            allowed_scopes=key_definition.allowed_scopes,
            minimum_sensitivity=key_definition.minimum_sensitivity,
        )
        lifecycle_decision = self._lifecycle_policy.evaluate(
            stage=LifecycleStage.ACTIVATION,
            facts=lifecycle_facts,
        )

        # 7. Semantic activation policy evaluation. The per-key/type promotion
        # gate is supplied by the injected gate, never defaulted open.
        activation_facts = ActivationFacts(
            scope=cand_scope,
            canonical_key=mem_candidate.canonical_key,
            target_conversation_id=conv_id,
            candidate_evidence=(cand_ev_identity,),
            has_unresolved_conflict=has_unresolved_conflict,
            is_constraint=mem_candidate.canonical_key.startswith("travel.constraint."),
            lifecycle_eligible=lifecycle_decision.eligible,
            type_evaluation_conclusive=self._type_evaluation_gate(
                mem_candidate.canonical_key
            ),
            memory_family=MemoryFamily.SEMANTIC,
            active_evidence=active_evidence,
            inferred_activation_enabled=self._inferred_activation_enabled,
        )
        activation_decision = self._activation_policy.evaluate(activation_facts)
        target_status = activation_decision.target_status

        decision_reason = _enum_value(decision.reason)
        resolved_operation = _enum_value(resolved_change.operation)

        if target_status == VersionStatus.ACTIVE:
            target_change = resolved_change
            reason_str = f"{decision_reason}|resolved_{resolved_operation}|{activation_decision.reason.value}"
        else:
            reason_str = f"{decision_reason}|resolved_{resolved_operation}|{activation_decision.reason.value}"
            target_change = MemoryChangeSet(
                operation=MemoryOperation.NOOP,
                identity=identity,
                new_version=None,
                superseded_version_ids=(),
                reference_version_id=None,
                reason=reason_str,
            )

        principal = AuthenticatedPrincipal(
            owner_user_id=mem_candidate.owner_user_id,
            auth_mode=AuthMode.AUTHENTICATED,
            credential_label="background_recorder",
        )

        semantic_key = _semantic_idempotency_key(
            source_outbox_id=source_outbox_id,
            identity=target_change.identity,
            normalized_value=mem_candidate.normalized_value,
            operation=resolved_operation,
        )

        if self._commit_coordinator is not None and fence is not None:
            # Deferred, not committed here. The coordinator is invoked once per
            # outbox event, never once per candidate: completing the source event
            # inside the first candidate's transaction retires the lease, so every
            # later candidate of the same event failed `check_outbox_lease` with
            # LEASE_LOST and was dropped without a trace.
            return BackgroundRecordResult(
                status="recorded",
                candidate_id=candidate.candidate_id,
                decision_outcome=decision.outcome,
                operation=target_change.operation,
                reason=reason_str,
                write_result=None,
                target_status=target_status,
                pending_commit=BackgroundMemoryCommitRequest(
                    principal=principal,
                    change=target_change,
                    evidence=(evidence,),
                    decision=decision,
                    idempotency_key=semantic_key,
                    expected_version_id=None,
                    source_validity=source_validity,
                    fence=fence,
                ),
            )

        write_result = uow.apply_memory_change(
            target_change,
            principal,
            evidence=(evidence,),
            decision=decision,
            idempotency_key=semantic_key,
            fence=fence,
            source_validity=source_validity,
        )

        return BackgroundRecordResult(
            status="recorded",
            candidate_id=candidate.candidate_id,
            decision_outcome=decision.outcome,
            operation=target_change.operation,
            reason=reason_str,
            write_result=write_result,
            target_status=target_status,
        )

    def record_sync(
        self,
        candidate: ShadowCandidate | MemoryCandidate,
        source_outbox_id: str | None = None,
        source_message_id: str | None = None,
        conversation_id: str | None = None,
        *,
        fence: FenceContext,
        source_handling_record: SourceHandlingRecord | None = None,
        source_validity: SourceValidity = SourceValidity.VALID,
    ) -> BackgroundRecordResult:
        """Record one background memory candidate as shadow or active evidence.

        Synchronous by design, so the worker never needs event-loop inspection or
        thread-pool dispatch.

        `fence` is mandatory: every background write must be bound to the
        lease and epoch its extraction observed, so a delete landing
        between extraction and commit fails closed instead of slipping
        through. When `source_outbox_id` is also given it must agree with
        the fence's outbox id.
        """
        if source_outbox_id is not None and source_outbox_id != fence.outbox_id:
            raise ValueError("source_outbox_id disagrees with the fence outbox id.")
        return self.record_batch_sync(
            (candidate,),
            source_outbox_id=source_outbox_id,
            source_message_id=source_message_id,
            conversation_id=conversation_id,
            fence=fence,
            source_handling_record=source_handling_record,
            source_validity=source_validity,
        )[0]

    def record_batch_sync(
        self,
        candidates: Sequence[ShadowCandidate | MemoryCandidate],
        source_outbox_id: str | None = None,
        source_message_id: str | None = None,
        conversation_id: str | None = None,
        *,
        fence: FenceContext,
        source_handling_record: SourceHandlingRecord | None = None,
        source_validity: SourceValidity = SourceValidity.VALID,
        event_type: str | None = None,
    ) -> tuple[BackgroundRecordResult, ...]:
        """Record every candidate of one outbox event through a single commit.

        The unit of work is the outbox event, not the candidate. One event can
        legitimately extract several governed preferences, and the coordinator
        completes the source event as part of its transaction — so committing per
        candidate would retire the lease after the first one and drop the rest.
        Preparing all candidates first and committing once keeps every candidate
        of an event inside one transaction, which is also the only shape that
        makes the event's effect all-or-nothing.
        """
        if source_outbox_id is not None and source_outbox_id != fence.outbox_id:
            raise ValueError("source_outbox_id disagrees with the fence outbox id.")

        prepared = tuple(
            self._prepare_core(
                candidate,
                source_outbox_id,
                source_message_id,
                conversation_id,
                fence,
                source_handling_record=source_handling_record,
                source_validity=source_validity,
                event_type=event_type,
            )
            for candidate in candidates
        )

        requests = tuple(
            result.pending_commit
            for result in prepared
            if result.pending_commit is not None
        )
        if not requests:
            return prepared

        assert self._commit_coordinator is not None
        committed = iter(self._commit_coordinator.commit_many(requests))
        return tuple(
            replace(result, write_result=next(committed), pending_commit=None)
            if result.pending_commit is not None
            else result
            for result in prepared
        )
