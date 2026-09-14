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
    ExplicitIntentError,
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
    candidate: MemoryCandidate,
    identity,
    supersedes_version_id: str | None,
    *,
    normalized_value=None,
) -> MemoryVersionDraft:
    """Build the proposed version content without an identifier.

    Identifiers are assigned later by the persistence layer. Omitting
    them here keeps repeated calls on identical inputs fully equal.

    Retention is assigned here rather than defaulted on the contract, because
    this is the last point at which the scope and authority that decide it are
    both in hand. The draft carries a required field, so a construction path
    that skipped assignment cannot persist a retention nobody chose.

    `normalized_value` overrides the candidate's own value for the two paths
    whose snapshot is *computed* rather than proposed: a set union, and an
    explicit replacement the caller materialised itself.

    The candidate's `suppression_generation` stamp travels onto the draft
    unchanged (`plan:710-722`): a draft that fell back to the initial
    generation would let delayed pre-revoke work resurrect the memory a
    revoke retired.
    """
    # Deferred to avoid making the pure lifecycle module depend on the eager
    # write-pipeline package initializer during import.
    from backend.memory.lifecycle import RetentionAssignmentPolicy

    return MemoryVersionDraft(
        owner_user_id=identity.owner_user_id,
        scope=identity.scope,
        scope_id=identity.scope_id,
        canonical_key=identity.canonical_key,
        subject_key=identity.subject_key,
        condition_fingerprint=identity.condition_fingerprint,
        normalized_value=(
            candidate.normalized_value
            if normalized_value is None
            else normalized_value
        ),
        display_text=candidate.display_text,
        authority=candidate.authority,
        sensitivity=candidate.sensitivity,
        valid_from=candidate.observed_at,
        retention_mode=RetentionAssignmentPolicy().assign(
            scope=identity.scope, authority=candidate.authority
        ),
        status=VersionStatus.ACTIVE,
        supersedes_version_id=supersedes_version_id,
        suppression_generation=candidate.suppression_generation,
    )


def _ordered_members(values, definition) -> tuple[str, ...]:
    """Validate and canonically order a materialised desired snapshot.

    Sorted and duplicate-free, so the stored snapshot does not depend on the
    order the caller assembled it in. An empty result is legal here — it is the
    revoke signal — which is why this is not the candidate's own value contract:
    a governed set *value* is never empty.

    Every member must be a governed registry member of the key, not merely a
    non-empty string: the desired snapshot becomes durable state, and free
    text that slips past this seam would bypass the registry entirely
    (`plan:836-839`).
    """
    if not isinstance(values, tuple):
        raise ValueError("Field 'desired_members' must be a tuple.")
    governed = frozenset(definition.values)
    members = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Every desired member must be a non-empty string.")
        stripped = value.strip()
        if stripped not in governed:
            raise ValueError(
                f"Desired member '{stripped}' is not a governed value of "
                f"'{definition.key}'."
            )
        members.append(stripped)
    if len(set(members)) != len(members):
        raise ValueError("Desired members must not repeat.")
    return tuple(sorted(members))


def _relation_value_mismatch(identity) -> MemoryChangeSet:
    """The classifier's relation disagrees with the live value.

    A governed reason rather than a silent no-op: the caller needs to be able to
    tell an inconsistent classifier result apart from "nothing to do".
    """
    return MemoryChangeSet(
        operation=MemoryOperation.REJECT,
        identity=identity,
        new_version=None,
        superseded_version_ids=(),
        reference_version_id=None,
        reason="rejected_relation_value_mismatch",
    )


def _set_union_change(candidate, identity, active) -> MemoryChangeSet:
    """Grow a set snapshot by deterministic union, or reinforce it.

    Positive evidence is member evidence, never a replacement command: a
    candidate that restates part of the live snapshot must not shrink it. If the
    union equals what is already live there is nothing to write, so the result is
    `REINFORCE`; otherwise the union becomes a new full snapshot and the prior
    version is superseded rather than edited.
    """
    live = set()
    for item in active:
        live.update(item.normalized_value)
    union = live | set(candidate.normalized_value)
    latest = _latest(active)
    if union == live:
        return MemoryChangeSet(
            operation=MemoryOperation.REINFORCE,
            identity=identity,
            new_version=None,
            superseded_version_ids=(),
            reference_version_id=latest.version_id,
            reason="reinforce_set_contained",
        )
    snapshot = tuple(sorted(union))
    return MemoryChangeSet(
        operation=MemoryOperation.SUPERSEDE,
        identity=identity,
        new_version=_new_draft(
            candidate, identity, latest.version_id, normalized_value=snapshot
        ),
        superseded_version_ids=tuple(item.version_id for item in active),
        reference_version_id=None,
        reason="compatible_union_supersede",
    )


def _contradiction_change(
    candidate: MemoryCandidate, identity, active: tuple[MemoryVersion, ...]
) -> MemoryChangeSet:
    """Resolve one contradiction by authority rank, then by time.

    A stronger observation supersedes every active same-identity version
    at once, which keeps single cardinality exact. A weaker observation
    holds without touching state. Equal authority needs a strictly newer
    observation; anything else stays pending instead of guessing.

    For a set assertion, a contradiction is a deliberate classifier claim
    that the snapshot is wrong in a member the evidence names. A disjoint
    claim reached here only because the deterministic member pre-check could
    not classify it, so it fails closed like any other inconsistent output
    (`plan:919-924`): a disjoint disagreement is an ambiguous negative, and
    ambiguous negative intent stays non-mutating.
    """
    if isinstance(candidate.normalized_value, tuple) and any(
        not (set(item.normalized_value) & set(candidate.normalized_value))
        for item in active
    ):
        return _relation_value_mismatch(identity)
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
    *,
    desired_members: tuple[str, ...] | None = None,
) -> MemoryChangeSet:
    """Resolve one candidate against current versions to one change set.

    Rule order is fixed: reject stale-generation and registry violations,
    reject prohibited content, hold uncertain relations pending, add first
    signals, ignore unrelated signals, reinforce restated values, resolve
    contradictions by authority then time, apply temporal updates, and attach
    scope exceptions beside the untouched default.

    `desired_members` is the explicit-replacement channel for a
    `set`-cardinality assertion: the caller materialises the snapshot it wants
    and submits it here. It exists because a governed set *value* is never
    empty, while the desired snapshot legitimately can be — and an empty one is
    a revoke rather than a stored value. It is refused for a single-valued key,
    which has no members to replace.

    A set candidate whose relation the members themselves decide is
    re-classified before the caller's relation is consulted: evidence contained
    by the live snapshot is `SAME`, evidence that grows it is `COMPATIBLE`.
    Only evidence that shrinks the snapshot leaves the classifier's verdict
    standing, and a shrink claimed as `CONTRADICTION` with no overlap is the
    inconsistent result that fails closed (`plan:828-831`, `plan:919-924`).
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
    definition = get_key_definition(candidate.canonical_key)
    is_set = definition.cardinality is Cardinality.SET
    if desired_members is not None:
        if not is_set:
            raise ValueError(
                "Field 'desired_members' applies to a set-cardinality key only; "
                "a single-valued assertion has no members to replace."
            )
        desired_members = _ordered_members(desired_members, definition)

    identity = assertion_identity(candidate)
    same_identity = tuple(item for item in current if _identity_matches(item, identity))
    active = tuple(
        item for item in same_identity if item.status is VersionStatus.ACTIVE
    )
    if any(
        item.suppression_generation != candidate.suppression_generation
        for item in active
    ):
        # A generation-N candidate may not mutate an assertion that has moved
        # on. This is the domain-level half of the no-resurrection fence; the
        # locked storage boundary re-checks the durable value before writing.
        return MemoryChangeSet(
            operation=MemoryOperation.REJECT,
            identity=identity,
            new_version=None,
            superseded_version_ids=(),
            reference_version_id=None,
            reason="rejected_stale_generation",
        )
    # Relation/value consistency. A single-valued assertion holds exactly one
    # value, so a classifier claim that disagrees with the live value is
    # inconsistent output and is refused.
    #
    # A set assertion is resolved by its members before the classifier's raw
    # relation is trusted (`plan:828-831`): evidence already contained by the
    # live snapshot is deterministically `SAME`, and evidence that grows it is
    # deterministically `COMPATIBLE` — so repeated positive evidence reaches
    # `REINFORCE`/union instead of depending on what the classifier said.
    # Evidence that shrinks the snapshot leaves the classifier's verdict
    # standing, but a `CONTRADICTION` with no member overlap is still an
    # inconsistent output and fails closed (`plan:919-924`): converting it into
    # an idempotent user action would make a defect look like intent.
    if not is_set:
        if relation is MemoryRelation.SAME and any(
            item.normalized_value != candidate.normalized_value for item in active
        ):
            return _relation_value_mismatch(identity)
        if relation is MemoryRelation.CONTRADICTION and any(
            item.normalized_value == candidate.normalized_value for item in active
        ):
            return _relation_value_mismatch(identity)
        if relation is MemoryRelation.COMPATIBLE and any(
            item.normalized_value != candidate.normalized_value for item in active
        ):
            return _relation_value_mismatch(identity)
    elif active:
        candidate_members = frozenset(candidate.normalized_value)
        active_members: set[str] = set()
        for item in active:
            active_members.update(item.normalized_value)
        if relation is MemoryRelation.CONTRADICTION:
            # A contradiction claim on a set is never a mutation: an explicit
            # correction travels through the materialised-snapshot channel
            # (`plan:843-848`), so a classifier CONTRADICTION here is
            # inconsistent output whether it overlaps the snapshot or not
            # (`plan:919-924`), and ambiguous negative intent stays
            # non-mutating.
            return _relation_value_mismatch(identity)
        if desired_members is None:
            # Deterministic member pre-check for positive evidence
            # (`plan:828-831`): the members themselves classify contained
            # evidence as `SAME` and growing evidence as `COMPATIBLE`, so
            # repeated positive evidence reinforces without consulting the
            # classifier. A subset claim cannot shrink the snapshot: the
            # union equals the live set and reinforces.
            if candidate_members <= active_members:
                relation = MemoryRelation.SAME
            elif candidate_members - active_members:
                relation = MemoryRelation.COMPATIBLE
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
    if is_set and relation in (MemoryRelation.SAME, MemoryRelation.COMPATIBLE):
        return _set_union_change(candidate, identity, active)
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
            if desired_members is not None and candidate.authority is not (
                Authority.EXPLICIT_SAVE
            ):
                # Background/model-only evidence proposes positive additions;
                # it has no authority to revoke a snapshot or replace it with
                # a smaller one (`plan:899-903`). The materialised snapshot is
                # the explicit channel, so a non-explicit candidate arriving
                # through it is a caller contract violation, not a resolution
                # outcome.
                raise ExplicitIntentError(
                    "Only an explicit user statement may replace or revoke a "
                    "set snapshot; background evidence proposes additions."
                )
            latest = _latest(active)
            superseded = tuple(item.version_id for item in active)
            if desired_members is not None:
                if not desired_members:
                    # Removing the final member is a revoke, not a stored empty
                    # set: no version is written, and the assertion's generation
                    # advance is owned by the locked persistence boundary.
                    return MemoryChangeSet(
                        operation=MemoryOperation.REVOKE,
                        identity=identity,
                        new_version=None,
                        superseded_version_ids=superseded,
                        reference_version_id=None,
                        reason="revoked_empty_snapshot",
                    )
                return MemoryChangeSet(
                    operation=MemoryOperation.SUPERSEDE,
                    identity=identity,
                    new_version=_new_draft(
                        candidate,
                        identity,
                        latest.version_id,
                        normalized_value=desired_members,
                    ),
                    superseded_version_ids=superseded,
                    reference_version_id=None,
                    reason="explicit_replacement_supersede",
                )
            return MemoryChangeSet(
                operation=MemoryOperation.SUPERSEDE,
                identity=identity,
                new_version=_new_draft(candidate, identity, latest.version_id),
                superseded_version_ids=superseded,
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
