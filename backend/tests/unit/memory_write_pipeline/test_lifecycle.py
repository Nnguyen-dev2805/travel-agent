"""Unit tests for the shared lifecycle-policy owner.

`MemoryLifecyclePolicy` is the one place that answers "is this Memory eligible
at this stage". Two properties matter more than any individual predicate:

- **It fails closed.** A fact a stage requires but did not receive denies with
  `MISSING_REQUIRED_FACT`; it is never treated as satisfied.
- **Its reason is deterministic.** When several predicates fail, the reported
  reason is the first in the normative order, so the same input always produces
  the same explanation and a caller cannot be told "expired" today and
  "stale_generation" tomorrow.

`RetentionAssignmentPolicy` is tested here too, because it is the same owner
answering a different question: assignment happens *before* a version exists,
evaluation never re-derives it.

No test here touches a database, a model, HTTP, or the network.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from backend.memory.lifecycle import (
    LifecycleDecision,
    LifecycleFacts,
    LifecycleReason,
    LifecycleStage,
    MemoryLifecyclePolicy,
    RetentionAssignmentPolicy,
    SourceValidity,
)
from backend.memory.write_pipeline.models import (
    Authority,
    MemoryScope,
    RetentionMode,
    SensitivityBand,
    VersionStatus,
)

MOMENT = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)

#: The normative precedence order. Written out here so reordering the
#: implementation's checks fails a test instead of silently changing which
#: reason a caller is told.
REASON_PRECEDENCE = (
    LifecycleReason.MISSING_REQUIRED_FACT,
    LifecycleReason.SCOPE_INELIGIBLE,
    LifecycleReason.SENSITIVITY_INELIGIBLE,
    LifecycleReason.STALE_GENERATION,
    LifecycleReason.EXPIRED,
    LifecycleReason.SOURCE_INVALID,
    LifecycleReason.STATUS_INELIGIBLE,
    LifecycleReason.ELIGIBLE,
)


def _facts(**overrides) -> LifecycleFacts:
    """A fully eligible `READ` fact set; override one thing at a time."""
    payload = {
        "retention_mode": RetentionMode.USER_DURABLE,
        "stamped_generation": 1,
        "current_generation": 1,
        "scope": MemoryScope.USER,
        "sensitivity": SensitivityBand.ORDINARY_PERSONAL,
        "source_validity": SourceValidity.NOT_REQUIRED,
        "status": VersionStatus.ACTIVE,
    }
    payload.update(overrides)
    return LifecycleFacts(**payload)


def _bound_facts(**overrides) -> LifecycleFacts:
    """A `SOURCE_BOUND` fact set, which does require source validity."""
    payload = {
        "retention_mode": RetentionMode.SOURCE_BOUND,
        "source_validity": SourceValidity.VALID,
    }
    payload.update(overrides)
    return _facts(**payload)


def _evaluate(stage: LifecycleStage, facts: LifecycleFacts) -> LifecycleDecision:
    return MemoryLifecyclePolicy().evaluate(stage=stage, facts=facts)


# ---------------------------------------------------------------------------
# Closed vocabularies.
# ---------------------------------------------------------------------------


def test_stage_vocabulary_is_closed():
    assert {member.value for member in LifecycleStage} == {
        "write",
        "formation",
        "activation",
        "read",
    }


def test_reason_vocabulary_is_closed():
    assert {member.value for member in LifecycleReason} == {
        "missing_required_fact",
        "scope_ineligible",
        "sensitivity_ineligible",
        "stale_generation",
        "expired",
        "source_invalid",
        "status_ineligible",
        "eligible",
    }


def test_source_validity_vocabulary_is_closed():
    """Never a raw bool: `NOT_REQUIRED` and `INVALID` mean different things."""
    assert {member.value for member in SourceValidity} == {
        "valid",
        "invalid",
        "not_required",
    }


def test_a_decision_carries_only_eligibility_and_a_reason():
    assert {field.name for field in dataclasses.fields(LifecycleDecision)} == {
        "eligible",
        "reason",
    }


# ---------------------------------------------------------------------------
# Missing facts fail closed, for every stage.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stage", list(LifecycleStage))
@pytest.mark.parametrize(
    "missing",
    [
        "retention_mode",
        "stamped_generation",
        "current_generation",
        "scope",
        "sensitivity",
    ],
)
def test_a_stage_required_fact_that_is_absent_denies(stage, missing):
    """Absence is never satisfied. This is the fail-closed core."""
    facts = _bound_facts(**{missing: None})

    decision = _evaluate(stage, facts)

    assert decision.eligible is False
    assert decision.reason is LifecycleReason.MISSING_REQUIRED_FACT


def test_read_requires_a_lifecycle_status():
    """`READ` is the only stage that has a status to look at."""
    decision = _evaluate(LifecycleStage.READ, _facts(status=None))

    assert decision.reason is LifecycleReason.MISSING_REQUIRED_FACT


@pytest.mark.parametrize(
    "stage",
    [LifecycleStage.WRITE, LifecycleStage.FORMATION, LifecycleStage.ACTIVATION],
)
def test_an_earlier_stage_does_not_require_a_status(stage):
    """A candidate or draft is not pretending to be an active version yet."""
    decision = _evaluate(stage, _bound_facts(status=None))

    assert decision.eligible is True


def test_an_expiry_without_an_evaluation_time_denies():
    """A temporal rule with no clock is an unanswerable question, not a pass."""
    facts = _facts(expires_at=MOMENT + timedelta(days=1), evaluated_at=None)

    assert _evaluate(LifecycleStage.READ, facts).reason is (
        LifecycleReason.MISSING_REQUIRED_FACT
    )


# ---------------------------------------------------------------------------
# Each predicate, and the precedence between them.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stage", list(LifecycleStage))
def test_a_stale_generation_denies_at_every_stage(stage):
    """A generation-N artifact cannot form, activate, or read after N+1."""
    decision = _evaluate(stage, _bound_facts(stamped_generation=1, current_generation=2))

    assert decision.reason is LifecycleReason.STALE_GENERATION


@pytest.mark.parametrize("stage", list(LifecycleStage))
def test_an_expired_version_denies(stage):
    facts = _bound_facts(expires_at=MOMENT, evaluated_at=MOMENT)

    assert _evaluate(stage, facts).reason is LifecycleReason.EXPIRED


@pytest.mark.parametrize("stage", list(LifecycleStage))
def test_a_future_expiry_does_not_deny(stage):
    facts = _bound_facts(
        expires_at=MOMENT + timedelta(seconds=1), evaluated_at=MOMENT
    )

    assert _evaluate(stage, facts).eligible is True


@pytest.mark.parametrize("stage", list(LifecycleStage))
def test_read_denies_a_version_that_is_not_active(stage):
    """Only `READ` looks at status; earlier stages have none to look at."""
    facts = _bound_facts(status=VersionStatus.REVOKED)

    decision = _evaluate(stage, facts)

    if stage is LifecycleStage.READ:
        assert decision.eligible is False
    else:
        assert decision.eligible is True


def test_read_denies_a_revoked_version_with_status_ineligible():
    decision = _evaluate(LifecycleStage.READ, _facts(status=VersionStatus.REVOKED))

    assert decision.reason is LifecycleReason.STATUS_INELIGIBLE


def test_a_revoked_version_is_not_status_checked_before_read():
    """Earlier stages have no status, so revocation reaches them as absence.

    A revoked version must not be re-formed, and the mechanism is the
    suppression generation, not the status column — the status check is a
    `READ` concern only.
    """
    decision = _evaluate(LifecycleStage.FORMATION, _bound_facts(status=None))

    assert decision.eligible is True


@pytest.mark.parametrize("stage", list(LifecycleStage))
def test_a_prohibited_secret_is_never_eligible(stage):
    """Hard policy, at every stage, regardless of any other fact."""
    facts = _bound_facts(sensitivity=SensitivityBand.PROHIBITED_SECRET)

    assert _evaluate(stage, facts).reason is LifecycleReason.SENSITIVITY_INELIGIBLE


@pytest.mark.parametrize("stage", list(LifecycleStage))
def test_a_sensitivity_below_the_supplied_floor_denies(stage):
    facts = _bound_facts(
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        minimum_sensitivity=SensitivityBand.RESTRICTED,
    )

    assert _evaluate(stage, facts).reason is LifecycleReason.SENSITIVITY_INELIGIBLE


@pytest.mark.parametrize("stage", list(LifecycleStage))
def test_a_scope_outside_the_supplied_allowance_denies(stage):
    facts = _bound_facts(
        scope=MemoryScope.CONVERSATION,
        allowed_scopes=(MemoryScope.USER,),
    )

    assert _evaluate(stage, facts).reason is LifecycleReason.SCOPE_INELIGIBLE


@pytest.mark.parametrize("stage", list(LifecycleStage))
def test_an_unsupplied_scope_or_floor_constraint_does_not_apply(stage):
    """The matrix does not list them as required, so their absence is not a denial.

    Per-key scope and floor are already enforced by `validate_against_registry`
    at the write boundary; the lifecycle policy only re-checks them when the
    caller supplies the entry's values.
    """
    decision = _evaluate(stage, _bound_facts())

    assert decision.eligible is True


def test_the_first_applicable_reason_wins():
    """Four predicates fail at once; the normative order decides the answer."""
    facts = _bound_facts(
        stamped_generation=1,
        current_generation=2,
        expires_at=MOMENT,
        evaluated_at=MOMENT,
        source_validity=SourceValidity.INVALID,
        status=VersionStatus.REVOKED,
    )

    decision = _evaluate(LifecycleStage.READ, facts)

    assert decision.reason is LifecycleReason.STALE_GENERATION


def test_the_precedence_order_is_the_documented_one():
    """Peel the predicates off one at a time and check the order they surface.

    Each step removes the reason that just won, so the sequence of reasons the
    policy reports *is* the precedence order. Reordering the implementation
    changes this sequence and fails here.
    """
    observed = []
    facts = _bound_facts(
        scope=MemoryScope.CONVERSATION,
        allowed_scopes=(MemoryScope.USER,),
        sensitivity=SensitivityBand.PROHIBITED_SECRET,
        stamped_generation=1,
        current_generation=2,
        expires_at=MOMENT,
        evaluated_at=MOMENT,
        source_validity=SourceValidity.INVALID,
        status=VersionStatus.REVOKED,
    )

    for expected in REASON_PRECEDENCE[1:7]:
        decision = _evaluate(LifecycleStage.READ, facts)
        observed.append(decision.reason)
        assert decision.reason is expected, observed
        facts = _peel(facts, expected)

    assert _evaluate(LifecycleStage.READ, facts).reason is LifecycleReason.ELIGIBLE
    assert observed == list(REASON_PRECEDENCE[1:7])


def _peel(facts: LifecycleFacts, reason: LifecycleReason) -> LifecycleFacts:
    """Return `facts` with the predicate behind `reason` satisfied."""
    if reason is LifecycleReason.SENSITIVITY_INELIGIBLE:
        return dataclasses.replace(facts, sensitivity=SensitivityBand.ORDINARY_PERSONAL)
    if reason is LifecycleReason.SCOPE_INELIGIBLE:
        return dataclasses.replace(
            facts, scope=MemoryScope.USER, allowed_scopes=(MemoryScope.USER,)
        )
    if reason is LifecycleReason.STALE_GENERATION:
        return dataclasses.replace(facts, stamped_generation=2)
    if reason is LifecycleReason.EXPIRED:
        return dataclasses.replace(facts, expires_at=None, evaluated_at=None)
    if reason is LifecycleReason.SOURCE_INVALID:
        return dataclasses.replace(facts, source_validity=SourceValidity.VALID)
    if reason is LifecycleReason.STATUS_INELIGIBLE:
        return dataclasses.replace(facts, status=VersionStatus.ACTIVE)
    raise AssertionError(f"nothing to peel for {reason}")


# ---------------------------------------------------------------------------
# Source validity: the one fact whose requirement depends on retention.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "retention",
    [RetentionMode.CONVERSATION_BOUND, RetentionMode.SOURCE_BOUND],
)
@pytest.mark.parametrize("stage", list(LifecycleStage))
def test_a_bound_version_requires_a_source_validity_fact(retention, stage):
    """`None` and `NOT_REQUIRED` are both absent facts for a bound version."""
    for absent in (None, SourceValidity.NOT_REQUIRED):
        decision = _evaluate(
            stage, _facts(retention_mode=retention, source_validity=absent)
        )

        assert decision.reason is LifecycleReason.MISSING_REQUIRED_FACT, absent


@pytest.mark.parametrize(
    "retention",
    [RetentionMode.CONVERSATION_BOUND, RetentionMode.SOURCE_BOUND],
)
@pytest.mark.parametrize("stage", list(LifecycleStage))
def test_a_bound_version_with_invalid_provenance_denies(retention, stage):
    facts = _facts(
        retention_mode=retention, source_validity=SourceValidity.INVALID
    )

    assert _evaluate(stage, facts).reason is LifecycleReason.SOURCE_INVALID


@pytest.mark.parametrize("stage", list(LifecycleStage))
def test_a_user_durable_value_survives_source_deletion(stage):
    """`NOT_REQUIRED` is the explicit valid state for durable retention.

    The normalized value is allowed to outlive its source; what must not survive
    is access to the deleted source's raw evidence, and that is a read-boundary
    concern rather than a lifecycle predicate (spec v0.7).
    """
    facts = _facts(
        retention_mode=RetentionMode.USER_DURABLE,
        source_validity=SourceValidity.NOT_REQUIRED,
    )

    assert _evaluate(stage, facts).eligible is True


@pytest.mark.parametrize("stage", list(LifecycleStage))
def test_an_absent_source_validity_denies_a_durable_value_too(stage):
    """Absence is not a licence, even where the fact is not required.

    `NOT_REQUIRED` states a fact; `None` states nothing, and the policy does not
    guess which one a caller meant.
    """
    facts = _facts(
        retention_mode=RetentionMode.USER_DURABLE, source_validity=None
    )

    assert _evaluate(stage, facts).reason is LifecycleReason.MISSING_REQUIRED_FACT


# ---------------------------------------------------------------------------
# The policy is pure and stage-aware, and knows nothing about its caller.
# ---------------------------------------------------------------------------


def test_the_policy_takes_no_execution_mode():
    """The API and worker paths share one policy, so it cannot branch on one."""
    signature = MemoryLifecyclePolicy.evaluate.__code__.co_varnames

    assert "execution_mode" not in signature
    assert "is_worker" not in signature
    assert "is_api" not in signature


def test_the_policy_is_stateless_and_repeatable():
    """The same facts produce the same decision, however often they are asked."""
    policy = MemoryLifecyclePolicy()
    facts = _bound_facts(stamped_generation=1, current_generation=2)

    first = policy.evaluate(stage=LifecycleStage.READ, facts=facts)
    second = policy.evaluate(stage=LifecycleStage.READ, facts=facts)

    assert first == second
    assert first.reason is LifecycleReason.STALE_GENERATION


def test_the_policy_module_does_not_import_storage_or_providers():
    """Pure domain policy: no SQLAlchemy, no FastAPI, no provider SDK."""
    source = (
        __import__("pathlib").Path(__file__).resolve().parents[4]
        / "backend/memory/lifecycle.py"
    ).read_text(encoding="utf-8")

    for forbidden in ("sqlalchemy", "fastapi", "psycopg", "openai"):
        assert forbidden not in source, forbidden


# ---------------------------------------------------------------------------
# Retention assignment: a separate question, answered before a version exists.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("scope", "authority", "expected"),
    [
        (MemoryScope.CONVERSATION, Authority.EXPLICIT_SAVE, RetentionMode.CONVERSATION_BOUND),
        (MemoryScope.CONVERSATION, Authority.EXPLICIT_STATEMENT, RetentionMode.CONVERSATION_BOUND),
        (MemoryScope.CONVERSATION, Authority.REPEATED_INFERENCE, RetentionMode.CONVERSATION_BOUND),
        (MemoryScope.USER, Authority.EXPLICIT_SAVE, RetentionMode.USER_DURABLE),
        (MemoryScope.USER, Authority.EXPLICIT_STATEMENT, RetentionMode.SOURCE_BOUND),
        (MemoryScope.USER, Authority.REPEATED_INFERENCE, RetentionMode.SOURCE_BOUND),
    ],
)
def test_retention_assignment_mapping_is_closed(scope, authority, expected):
    """Every current scope/authority combination, and only those."""
    assigned = RetentionAssignmentPolicy().assign(scope=scope, authority=authority)

    assert assigned is expected


def test_only_a_corroborated_save_earns_durable_retention():
    """The one path to `USER_DURABLE`, stated as a property.

    A plain statement is evidence, not durable-save intent, and inferred state
    stays tied to its provenance (ADR 0037, spec v0.7).
    """
    durable = [
        (scope, authority)
        for scope in MemoryScope
        for authority in Authority
        if RetentionAssignmentPolicy().assign(scope=scope, authority=authority)
        is RetentionMode.USER_DURABLE
    ]

    assert durable == [(MemoryScope.USER, Authority.EXPLICIT_SAVE)]


def test_retention_assignment_fails_closed_on_an_unknown_input():
    with pytest.raises(ValueError):
        RetentionAssignmentPolicy().assign(scope="agent", authority=Authority.EXPLICIT_SAVE)

    with pytest.raises(ValueError):
        RetentionAssignmentPolicy().assign(scope=MemoryScope.USER, authority="magic")


@pytest.mark.parametrize(
    ("scope", "authority"),
    [
        (None, Authority.EXPLICIT_SAVE),
        (MemoryScope.USER, None),
        (None, None),
        (MemoryScope.CONVERSATION, None),
        (None, Authority.REPEATED_INFERENCE),
    ],
)
def test_retention_assignment_refuses_an_absent_input(scope, authority):
    """`None` is an absent fact, not a scope or an authority.

    The first version of this policy coerced `None` to `None`, matched nothing,
    and fell through to `SOURCE_BOUND` — so a caller that forgot to pass a scope
    silently received a retention decision for a combination nobody had
    reviewed. Assignment is a privacy decision; it has no default.
    """
    with pytest.raises(ValueError):
        RetentionAssignmentPolicy().assign(scope=scope, authority=authority)


@pytest.mark.parametrize(
    ("scope", "authority"),
    [
        (MemoryScope.USER, object()),
        (object(), Authority.EXPLICIT_SAVE),
        (MemoryScope.USER, 7),
        (3.5, Authority.EXPLICIT_SAVE),
    ],
)
def test_retention_assignment_refuses_a_non_governed_input(scope, authority):
    """A value outside the closed vocabularies is refused, never defaulted."""
    with pytest.raises(ValueError):
        RetentionAssignmentPolicy().assign(scope=scope, authority=authority)


def test_the_assignment_mapping_is_total_over_the_closed_vocabularies():
    """Every combination the vocabularies can produce has an explicit answer.

    Totality is the property that removes the need for a fallback: if every
    reachable pair is in the table, an unlisted pair can only come from a
    vocabulary that grew without the table growing with it — which is exactly
    the case that must raise rather than guess.
    """
    policy = RetentionAssignmentPolicy()

    assigned = {
        (scope, authority): policy.assign(scope=scope, authority=authority)
        for scope in MemoryScope
        for authority in Authority
    }

    assert len(assigned) == len(MemoryScope) * len(Authority)
    assert set(assigned.values()) <= set(RetentionMode)


def test_retention_assignment_takes_no_execution_mode():
    signature = RetentionAssignmentPolicy.assign.__code__.co_varnames

    assert "execution_mode" not in signature
