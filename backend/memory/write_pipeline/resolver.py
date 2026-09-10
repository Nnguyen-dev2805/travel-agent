"""Deterministic candidate-to-change-set resolution.

A pure function over domain inputs: cardinality, authority, scope, time,
and uncertainty rules decide one typed change set. No clock, no network,
no side effects; inputs are never mutated. This module depends on the
Python standard library and the sibling contract and registry modules
only.
"""

from __future__ import annotations

from backend.memory.write_pipeline.models import (
    AUTHORITY_RANK,
    Authority,
    Cardinality,
    MemoryCandidate,
    MemoryChangeSet,
    MemoryOperation,
    MemoryRelation,
    MemoryScope,
    MemoryVersion,
    MemoryVersionDraft,
    SensitivityBand,
    VersionStatus,
    assertion_identity,
)
from backend.memory.write_pipeline.registry import (
    RegistryValidationError,
    UnknownKeyError,
    get_key_definition,
    validate_against_registry,
)


def _identity_matches(version: MemoryVersion, identity) -> bool:
    return (
        version.owner_user_id == identity.owner_user_id
        and version.scope == identity.scope
        and version.scope_id == identity.scope_id
        and version.canonical_key == identity.canonical_key
        and version.subject_key == identity.subject_key
        and version.condition_fingerprint == identity.condition_fingerprint
    )


def _latest(versions: tuple[MemoryVersion, ...]) -> MemoryVersion:
    return max(versions, key=lambda item: (item.valid_from, item.version_id))


def _new_draft(
    candidate: MemoryCandidate, identity, supersedes_version_id: str | None
) -> MemoryVersionDraft:
    """Build the proposed version content without an identifier.

    Identifiers are assigned later by the persistence layer. Omitting
    them here keeps repeated calls on identical inputs fully equal.
    """
    return MemoryVersionDraft(
        owner_user_id=identity.owner_user_id,
        scope=identity.scope,
        scope_id=identity.scope_id,
        canonical_key=identity.canonical_key,
        subject_key=identity.subject_key,
        condition_fingerprint=identity.condition_fingerprint,
        normalized_value=candidate.normalized_value,
        display_text=candidate.display_text,
        authority=candidate.authority,
        sensitivity=candidate.sensitivity,
        valid_from=candidate.observed_at,
        status=VersionStatus.ACTIVE,
        supersedes_version_id=supersedes_version_id,
    )


def _contradiction_change(
    candidate: MemoryCandidate, identity, active: tuple[MemoryVersion, ...]
) -> MemoryChangeSet:
    """Resolve one contradiction by authority rank, then by time.

    A stronger observation supersedes every active same-identity version
    at once, which keeps single cardinality exact. A weaker observation
    holds without touching state. Equal authority needs a strictly newer
    observation; anything else stays pending instead of guessing.
    """
    candidate_rank = AUTHORITY_RANK[candidate.authority]
    best_rank = max(AUTHORITY_RANK[item.authority] for item in active)
    if candidate_rank > best_rank:
        latest = _latest(active)
        return MemoryChangeSet(
            operation=MemoryOperation.SUPERSEDE,
            identity=identity,
            new_version=_new_draft(candidate, identity, latest.version_id),
            superseded_version_ids=tuple(item.version_id for item in active),
            reference_version_id=None,
            reason="stronger_authority_supersede",
        )
    if candidate_rank < best_rank:
        return MemoryChangeSet(
            operation=MemoryOperation.NOOP,
            identity=identity,
            new_version=None,
            superseded_version_ids=(),
            reference_version_id=None,
            reason="held_weaker_authority",
        )
    newest_active_time = max(item.valid_from for item in active)
    if candidate.observed_at > newest_active_time:
        latest = _latest(active)
        return MemoryChangeSet(
            operation=MemoryOperation.SUPERSEDE,
            identity=identity,
            new_version=_new_draft(candidate, identity, latest.version_id),
            superseded_version_ids=tuple(item.version_id for item in active),
            reference_version_id=None,
            reason="newer_equal_authority_supersede",
        )
    return MemoryChangeSet(
        operation=MemoryOperation.PENDING_CONFLICT,
        identity=identity,
        new_version=None,
        superseded_version_ids=(),
        reference_version_id=None,
        reason="equal_authority_ambiguous",
    )


def resolve_change(
    candidate: MemoryCandidate,
    current: tuple[MemoryVersion, ...],
    relation: MemoryRelation,
) -> MemoryChangeSet:
    """Resolve one candidate against current versions to one change set.

    Rule order is fixed: reject registry violations, reject prohibited
    content, hold uncertain relations pending, add first signals, ignore
    unrelated signals, reinforce restated values, resolve contradictions
    by authority then time, apply temporal updates, and attach scope
    exceptions beside the untouched default.
    """
    try:
        validate_against_registry(candidate)
    except UnknownKeyError:
        return MemoryChangeSet(
            operation=MemoryOperation.REJECT,
            identity=None,
            new_version=None,
            superseded_version_ids=(),
            reference_version_id=None,
            reason="rejected_unknown_key",
        )
    except RegistryValidationError:
        # No identity is derived here: hashing rejected free text would
        # mint identifiers from ungoverned input.
        return MemoryChangeSet(
            operation=MemoryOperation.REJECT,
            identity=None,
            new_version=None,
            superseded_version_ids=(),
            reference_version_id=None,
            reason="rejected_registry_violation",
        )
    identity = assertion_identity(candidate)
    same_identity = tuple(item for item in current if _identity_matches(item, identity))
    active = tuple(
        item for item in same_identity if item.status is VersionStatus.ACTIVE
    )
    if relation is MemoryRelation.SAME and any(
        item.normalized_value != candidate.normalized_value for item in active
    ):
        return MemoryChangeSet(
            operation=MemoryOperation.REJECT,
            identity=identity,
            new_version=None,
            superseded_version_ids=(),
            reference_version_id=None,
            reason="rejected_relation_value_mismatch",
        )
    if relation is MemoryRelation.CONTRADICTION and any(
        item.normalized_value == candidate.normalized_value for item in active
    ):
        return MemoryChangeSet(
            operation=MemoryOperation.REJECT,
            identity=identity,
            new_version=None,
            superseded_version_ids=(),
            reference_version_id=None,
            reason="rejected_relation_value_mismatch",
        )
    if relation is MemoryRelation.COMPATIBLE and any(
        item.normalized_value != candidate.normalized_value for item in active
    ):
        # A single-valued key cannot hold two values at once, so a
        # compatibility claim against a differing live value is an
        # inconsistent classifier output. Gated on registry cardinality
        # so future set-valued keys keep their own compatible semantics.
        definition = get_key_definition(candidate.canonical_key)
        if definition.cardinality is Cardinality.SINGLE:
            return MemoryChangeSet(
                operation=MemoryOperation.REJECT,
                identity=identity,
                new_version=None,
                superseded_version_ids=(),
                reference_version_id=None,
                reason="rejected_relation_value_mismatch",
            )
    if candidate.sensitivity is SensitivityBand.PROHIBITED_SECRET:
        return MemoryChangeSet(
            operation=MemoryOperation.REJECT,
            identity=identity,
            new_version=None,
            superseded_version_ids=(),
            reference_version_id=None,
            reason="rejected_prohibited",
        )
    if relation is MemoryRelation.UNCERTAIN:
        return MemoryChangeSet(
            operation=MemoryOperation.PENDING_CONFLICT,
            identity=identity,
            new_version=None,
            superseded_version_ids=(),
            reference_version_id=None,
            reason="pending_uncertain_relation",
        )
    if relation is MemoryRelation.SCOPE_EXCEPTION:
        # An exception is valid only downward: a conversation candidate
        # beside an active user-scope default with the same owner, key,
        # subject, and condition. Any other direction, or no live
        # default, is rejected instead of inventing a parent.
        if candidate.scope is not MemoryScope.CONVERSATION:
            return MemoryChangeSet(
                operation=MemoryOperation.REJECT,
                identity=identity,
                new_version=None,
                superseded_version_ids=(),
                reference_version_id=None,
                reason="rejected_exception_direction",
            )
        defaults = tuple(
            item
            for item in current
            if item.owner_user_id == identity.owner_user_id
            and item.canonical_key == identity.canonical_key
            and item.subject_key == identity.subject_key
            and item.condition_fingerprint == identity.condition_fingerprint
            and item.scope is MemoryScope.USER
            and item.status is VersionStatus.ACTIVE
        )
        if not defaults:
            return MemoryChangeSet(
                operation=MemoryOperation.REJECT,
                identity=identity,
                new_version=None,
                superseded_version_ids=(),
                reference_version_id=None,
                reason="rejected_exception_without_default",
            )
        return MemoryChangeSet(
            operation=MemoryOperation.ADD_EXCEPTION,
            identity=identity,
            new_version=_new_draft(candidate, identity, None),
            superseded_version_ids=(),
            reference_version_id=_latest(defaults).version_id,
            reason="scope_exception_added",
        )
    if not same_identity:
        return MemoryChangeSet(
            operation=MemoryOperation.ADD,
            identity=identity,
            new_version=_new_draft(candidate, identity, None),
            superseded_version_ids=(),
            reference_version_id=None,
            reason="first_add",
        )
    if not active:
        return MemoryChangeSet(
            operation=MemoryOperation.ADD,
            identity=identity,
            new_version=_new_draft(candidate, identity, None),
            superseded_version_ids=(),
            reference_version_id=None,
            reason="re_add_superseded_only",
        )
    if relation is MemoryRelation.UNRELATED:
        return MemoryChangeSet(
            operation=MemoryOperation.NOOP,
            identity=identity,
            new_version=None,
            superseded_version_ids=(),
            reference_version_id=None,
            reason="unrelated_noop",
        )
    if relation in (MemoryRelation.SAME, MemoryRelation.COMPATIBLE):
        matches = tuple(
            item
            for item in active
            if item.normalized_value == candidate.normalized_value
        )
        if matches:
            return MemoryChangeSet(
                operation=MemoryOperation.REINFORCE,
                identity=identity,
                new_version=None,
                superseded_version_ids=(),
                reference_version_id=_latest(matches).version_id,
                reason="reinforce_same_value",
            )
    if relation is MemoryRelation.TEMPORAL_UPDATE:
        # A temporal update supersedes only when it is both at least as
        # authoritative as the active value and strictly newer. Weaker,
        # older, or equally old evidence stays pending instead of
        # rewriting explicit state on a hunch.
        best_rank = max(AUTHORITY_RANK[item.authority] for item in active)
        newest_active_time = max(item.valid_from for item in active)
        if (
            AUTHORITY_RANK[candidate.authority] >= best_rank
            and candidate.observed_at > newest_active_time
        ):
            latest = _latest(active)
            return MemoryChangeSet(
                operation=MemoryOperation.SUPERSEDE,
                identity=identity,
                new_version=_new_draft(candidate, identity, latest.version_id),
                superseded_version_ids=tuple(item.version_id for item in active),
                reference_version_id=None,
                reason="temporal_update_supersede",
            )
        return MemoryChangeSet(
            operation=MemoryOperation.PENDING_CONFLICT,
            identity=identity,
            new_version=None,
            superseded_version_ids=(),
            reference_version_id=None,
            reason="temporal_pending",
        )
    return _contradiction_change(candidate, identity, active)
