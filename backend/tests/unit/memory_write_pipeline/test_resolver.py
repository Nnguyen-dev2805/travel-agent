"""Unit tests for the deterministic conflict resolver.

Every row of the conflict truth table is pinned from pure domain inputs:
no database, no model, no clock, no side effects. No test here touches a
database, a model, HTTP, or the network.
"""

from datetime import datetime, timedelta, timezone

import pytest

from backend.memory.write_pipeline.models import (
    Authority,
    MemoryCandidate,
    MemoryOperation,
    MemoryRelation,
    MemoryVersion,
    SensitivityBand,
    VersionStatus,
    assertion_identity,
    new_candidate_id,
    new_evidence_id,
    new_version_id,
)
from backend.memory.write_pipeline.registry import HOTEL_ATMOSPHERE_KEY
from backend.memory.write_pipeline.resolver import resolve_change

MOMENT = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
NEWER = MOMENT + timedelta(hours=1)


def _candidate(**overrides) -> MemoryCandidate:
    payload = {
        "candidate_id": new_candidate_id(),
        "evidence_ids": (new_evidence_id(),),
        "owner_user_id": "user_owner",
        "scope": "user",
        "conversation_id": None,
        "canonical_key": HOTEL_ATMOSPHERE_KEY,
        "normalized_value": "quiet",
        "display_text": "a quiet hotel",
        "authority": Authority.EXPLICIT_SAVE,
        "sensitivity": SensitivityBand.ORDINARY_PERSONAL,
        "observed_at": MOMENT,
    }
    payload.update(overrides)
    return MemoryCandidate(**payload)


def _version(**overrides) -> MemoryVersion:
    identity = assertion_identity(_candidate())
    payload = {
        "version_id": new_version_id(),
        "owner_user_id": identity.owner_user_id,
        "scope": identity.scope,
        "scope_id": identity.scope_id,
        "canonical_key": identity.canonical_key,
        "subject_key": identity.subject_key,
        "condition_fingerprint": identity.condition_fingerprint,
        "normalized_value": "quiet",
        "display_text": "a quiet hotel",
        "authority": Authority.EXPLICIT_SAVE,
        "sensitivity": SensitivityBand.ORDINARY_PERSONAL,
        "status": VersionStatus.ACTIVE,
        "valid_from": MOMENT,
    }
    payload.update(overrides)
    return MemoryVersion(**payload)


# 1. A first signal adds one active version.


def test_new_signal_adds_one_active_version():
    change = resolve_change(_candidate(), current=(), relation=MemoryRelation.UNRELATED)

    assert change.operation is MemoryOperation.ADD
    assert change.new_version is not None
    assert change.new_version.status is VersionStatus.ACTIVE
    assert change.new_version.normalized_value == "quiet"
    assert change.new_version.supersedes_version_id is None
    assert change.superseded_version_ids == ()
    assert change.identity == assertion_identity(_candidate())


# 2. A paraphrase of the current value reinforces without duplication.


def test_paraphrase_of_current_value_reinforces():
    active = _version()
    paraphrase = _candidate(display_text="Tôi thích khách sạn yên tĩnh")

    change = resolve_change(paraphrase, current=(active,), relation=MemoryRelation.SAME)

    assert change.operation is MemoryOperation.REINFORCE
    assert change.new_version is None
    assert change.superseded_version_ids == ()
    assert change.reference_version_id == active.version_id


# 3. An explicit correction supersedes exactly the active version.


def test_explicit_correction_supersedes_only_the_active_version():
    history = _version(normalized_value="lively", status=VersionStatus.SUPERSEDED)
    active = _version()
    correction = _candidate(
        normalized_value="lively",
        display_text="Thực ra tôi thích sôi động",
        observed_at=NEWER,
    )

    change = resolve_change(
        correction, current=(history, active), relation=MemoryRelation.CONTRADICTION
    )

    assert change.operation is MemoryOperation.SUPERSEDE
    assert change.new_version is not None
    assert change.new_version.status is VersionStatus.ACTIVE
    assert change.new_version.normalized_value == "lively"
    assert change.new_version.supersedes_version_id == active.version_id
    assert change.superseded_version_ids == (active.version_id,)
    # History is kept: inputs are immutable and the older record is untouched.
    assert history.status is VersionStatus.SUPERSEDED
    assert active.status is VersionStatus.ACTIVE


# 4. A weaker inference never supersedes an explicit value.


def test_weaker_inference_holds_without_supersession():
    active = _version()
    weak = _candidate(
        normalized_value="lively",
        authority=Authority.REPEATED_INFERENCE,
        observed_at=NEWER,
    )

    change = resolve_change(
        weak, current=(active,), relation=MemoryRelation.CONTRADICTION
    )

    assert change.operation is MemoryOperation.NOOP
    assert change.reason == "held_weaker_authority"
    assert change.new_version is None
    assert change.superseded_version_ids == ()


# 5. A conversation exception leaves the user default untouched.


def test_conversation_exception_preserves_the_user_default():
    default = _version()
    exception = _candidate(
        scope="conversation",
        conversation_id="cv_trip",
        normalized_value="lively",
        observed_at=NEWER,
    )

    change = resolve_change(
        exception, current=(default,), relation=MemoryRelation.SCOPE_EXCEPTION
    )

    assert change.operation is MemoryOperation.ADD_EXCEPTION
    assert change.new_version is not None
    assert change.new_version.status is VersionStatus.ACTIVE
    assert change.new_version.scope == "conversation"
    assert change.new_version.scope_id == "cv_trip"
    assert change.superseded_version_ids == ()
    assert change.reference_version_id == default.version_id
    assert default.status is VersionStatus.ACTIVE


# 6. Equal authority without a newer time stays pending, never mutating.


def test_equal_authority_ambiguity_is_pending_without_mutation():
    active = _version()
    rival = _candidate(normalized_value="lively", observed_at=MOMENT)

    change = resolve_change(
        rival, current=(active,), relation=MemoryRelation.CONTRADICTION
    )

    assert change.operation is MemoryOperation.PENDING_CONFLICT
    assert change.new_version is None
    assert change.superseded_version_ids == ()


def test_equal_authority_newer_time_supersedes():
    active = _version()
    rival = _candidate(normalized_value="lively", observed_at=NEWER)

    change = resolve_change(
        rival, current=(active,), relation=MemoryRelation.CONTRADICTION
    )

    assert change.operation is MemoryOperation.SUPERSEDE
    assert change.superseded_version_ids == (active.version_id,)


# 7. Non-mutating outcomes share one shape: no version, no supersession.


@pytest.mark.parametrize(
    ("candidate_kwargs", "relation", "operation"),
    [
        (
            {
                "normalized_value": "lively",
                "authority": Authority.REPEATED_INFERENCE,
                "observed_at": NEWER,
            },
            MemoryRelation.CONTRADICTION,
            MemoryOperation.NOOP,
        ),
        (
            {"normalized_value": "lively", "observed_at": MOMENT},
            MemoryRelation.CONTRADICTION,
            MemoryOperation.PENDING_CONFLICT,
        ),
        (
            {"normalized_value": "lively", "observed_at": NEWER},
            MemoryRelation.UNCERTAIN,
            MemoryOperation.PENDING_CONFLICT,
        ),
        (
            {"normalized_value": "lively", "observed_at": NEWER},
            MemoryRelation.UNRELATED,
            MemoryOperation.NOOP,
        ),
        (
            {"sensitivity": SensitivityBand.PROHIBITED_SECRET, "observed_at": NEWER},
            MemoryRelation.CONTRADICTION,
            MemoryOperation.REJECT,
        ),
    ],
    ids=[
        "weaker-hold",
        "equal-ambiguous",
        "uncertain",
        "unrelated",
        "prohibited",
    ],
)
def test_non_mutating_outcomes_create_nothing(candidate_kwargs, relation, operation):
    active = _version()

    change = resolve_change(
        _candidate(**candidate_kwargs), current=(active,), relation=relation
    )

    assert change.operation is operation
    assert change.new_version is None
    assert change.superseded_version_ids == ()
    assert active.status is VersionStatus.ACTIVE


def test_same_relation_with_different_values_is_rejected():
    active = _version()

    change = resolve_change(
        _candidate(normalized_value="lively"),
        current=(active,),
        relation=MemoryRelation.SAME,
    )

    assert change.operation is MemoryOperation.REJECT
    assert change.new_version is None
    assert change.superseded_version_ids == ()


def test_contradiction_with_equal_values_is_rejected():
    active = _version()

    change = resolve_change(
        _candidate(normalized_value="quiet", display_text="other words"),
        current=(active,),
        relation=MemoryRelation.CONTRADICTION,
    )

    assert change.operation is MemoryOperation.REJECT
    assert change.new_version is None
    assert change.superseded_version_ids == ()


def test_exception_without_user_default_is_rejected():
    orphan = _candidate(
        scope="conversation",
        conversation_id="cv_trip",
        normalized_value="lively",
        observed_at=NEWER,
    )

    change = resolve_change(orphan, current=(), relation=MemoryRelation.SCOPE_EXCEPTION)

    assert change.operation is MemoryOperation.REJECT
    assert change.reason == "rejected_exception_without_default"
    assert change.new_version is None
    assert change.superseded_version_ids == ()


def test_user_candidate_with_conversation_base_is_rejected():
    conv_base = _version(
        scope="conversation",
        scope_id="cv_trip",
        normalized_value="lively",
    )
    candidate = _candidate(normalized_value="quiet", observed_at=NEWER)

    change = resolve_change(
        candidate, current=(conv_base,), relation=MemoryRelation.SCOPE_EXCEPTION
    )

    assert change.operation is MemoryOperation.REJECT
    assert change.reason == "rejected_exception_direction"
    assert change.new_version is None
    assert change.superseded_version_ids == ()
    assert conv_base.status is VersionStatus.ACTIVE


def test_registry_violation_returns_no_identity():
    change = resolve_change(
        _candidate(condition="near the beach"),
        current=(),
        relation=MemoryRelation.UNRELATED,
    )

    assert change.operation is MemoryOperation.REJECT
    assert change.identity is None
    assert change.new_version is None


def test_non_empty_condition_rejected_on_exception_path():
    # The exception path matches on scope, never on condition text, and
    # Phase-1 conditions never reach it: entry validation rejects first.
    default = _version()
    change = resolve_change(
        _candidate(
            scope="conversation",
            conversation_id="cv_trip",
            normalized_value="lively",
            condition="beach trip",
            observed_at=NEWER,
        ),
        current=(default,),
        relation=MemoryRelation.SCOPE_EXCEPTION,
    )

    assert change.operation is MemoryOperation.REJECT
    assert change.new_version is None
    assert default.status is VersionStatus.ACTIVE


def test_compatible_with_differing_active_value_is_rejected():
    active = _version()

    change = resolve_change(
        _candidate(normalized_value="lively", observed_at=NEWER),
        current=(active,),
        relation=MemoryRelation.COMPATIBLE,
    )

    assert change.operation is MemoryOperation.REJECT
    assert change.new_version is None
    assert change.superseded_version_ids == ()


def test_compatible_with_equal_active_value_proceeds():
    active = _version()
    paraphrase = _candidate(display_text="yên tĩnh nhé")

    change = resolve_change(
        paraphrase, current=(active,), relation=MemoryRelation.COMPATIBLE
    )

    assert change.operation is MemoryOperation.REINFORCE
    assert change.reference_version_id == active.version_id


def test_unknown_key_is_rejected():
    change = resolve_change(
        _candidate(canonical_key="travel.preference.unknown_key"),
        current=(),
        relation=MemoryRelation.UNRELATED,
    )

    assert change.operation is MemoryOperation.REJECT
    assert change.new_version is None
    assert change.identity is None


def test_unknown_registry_value_is_rejected_never_added():
    change = resolve_change(
        _candidate(normalized_value="beachfront"),
        current=(),
        relation=MemoryRelation.UNRELATED,
    )

    assert change.operation is MemoryOperation.REJECT
    assert change.new_version is None
    assert change.superseded_version_ids == ()


def test_non_empty_condition_is_rejected():
    change = resolve_change(
        _candidate(condition="near the beach"),
        current=(),
        relation=MemoryRelation.UNRELATED,
    )

    assert change.operation is MemoryOperation.REJECT
    assert change.new_version is None


def test_superseded_only_history_adds_fresh_without_crash():
    older = _version(normalized_value="lively", status=VersionStatus.SUPERSEDED)
    retired = _version(status=VersionStatus.SUPERSEDED)
    candidate = _candidate(observed_at=NEWER)

    change = resolve_change(
        candidate, current=(older, retired), relation=MemoryRelation.CONTRADICTION
    )

    assert change.operation is MemoryOperation.ADD
    assert change.new_version is not None
    assert change.new_version.normalized_value == "quiet"
    assert change.superseded_version_ids == ()


# The temporal rule is rank >= best AND strictly newer: each single
# relaxed to OR must flip its pin from PENDING to SUPERSEDE loudly.


def test_temporal_weaker_but_newer_stays_pending():
    active = _version()
    weak_new = _candidate(
        normalized_value="lively",
        authority=Authority.REPEATED_INFERENCE,
        observed_at=NEWER,
    )

    change = resolve_change(
        weak_new, current=(active,), relation=MemoryRelation.TEMPORAL_UPDATE
    )

    assert change.operation is MemoryOperation.PENDING_CONFLICT
    assert change.new_version is None
    assert change.superseded_version_ids == ()


def test_temporal_equal_authority_equal_time_stays_pending():
    active = _version()
    rival = _candidate(normalized_value="lively", observed_at=MOMENT)

    change = resolve_change(
        rival, current=(active,), relation=MemoryRelation.TEMPORAL_UPDATE
    )

    assert change.operation is MemoryOperation.PENDING_CONFLICT
    assert change.new_version is None
    assert change.superseded_version_ids == ()


def test_temporal_equal_authority_older_stays_pending():
    active = _version()
    rival = _candidate(
        normalized_value="lively", observed_at=MOMENT - timedelta(hours=1)
    )

    change = resolve_change(
        rival, current=(active,), relation=MemoryRelation.TEMPORAL_UPDATE
    )

    assert change.operation is MemoryOperation.PENDING_CONFLICT
    assert change.new_version is None
    assert change.superseded_version_ids == ()


def test_temporal_stronger_but_older_stays_pending():
    old_explicit = _version(authority=Authority.REPEATED_INFERENCE, valid_from=MOMENT)
    strong_old = _candidate(
        normalized_value="lively",
        authority=Authority.EXPLICIT_SAVE,
        observed_at=MOMENT - timedelta(hours=1),
    )

    change = resolve_change(
        strong_old,
        current=(old_explicit,),
        relation=MemoryRelation.TEMPORAL_UPDATE,
    )

    assert change.operation is MemoryOperation.PENDING_CONFLICT
    assert change.new_version is None
    assert change.superseded_version_ids == ()


def test_temporal_stronger_equal_time_stays_pending():
    old_explicit = _version(authority=Authority.REPEATED_INFERENCE)
    strong_same_time = _candidate(
        normalized_value="lively",
        authority=Authority.EXPLICIT_SAVE,
        observed_at=MOMENT,
    )

    change = resolve_change(
        strong_same_time,
        current=(old_explicit,),
        relation=MemoryRelation.TEMPORAL_UPDATE,
    )

    assert change.operation is MemoryOperation.PENDING_CONFLICT
    assert change.new_version is None
    assert change.superseded_version_ids == ()


def test_temporal_update_with_weaker_older_evidence_stays_pending():
    active = _version()
    weak_old = _candidate(
        normalized_value="lively",
        authority=Authority.REPEATED_INFERENCE,
        observed_at=MOMENT - timedelta(hours=1),
    )

    change = resolve_change(
        weak_old, current=(active,), relation=MemoryRelation.TEMPORAL_UPDATE
    )

    assert change.operation is MemoryOperation.PENDING_CONFLICT
    assert change.new_version is None
    assert change.superseded_version_ids == ()


def test_temporal_update_newer_explicit_supersedes_older_inference():
    old_inference = _version(
        authority=Authority.REPEATED_INFERENCE,
        valid_from=MOMENT - timedelta(hours=1),
    )
    update = _candidate(normalized_value="lively", observed_at=MOMENT)

    change = resolve_change(
        update, current=(old_inference,), relation=MemoryRelation.TEMPORAL_UPDATE
    )

    assert change.operation is MemoryOperation.SUPERSEDE
    assert change.superseded_version_ids == (old_inference.version_id,)


def test_temporal_update_supersedes():
    active = _version()
    update = _candidate(normalized_value="central", observed_at=NEWER)

    change = resolve_change(
        update, current=(active,), relation=MemoryRelation.TEMPORAL_UPDATE
    )

    assert change.operation is MemoryOperation.SUPERSEDE
    assert change.superseded_version_ids == (active.version_id,)


# 8. The resolver is pure: deterministic and side-effect free.


def test_resolver_is_deterministic():
    active = _version()
    candidate = _candidate(normalized_value="lively", observed_at=NEWER)

    first = resolve_change(
        candidate, current=(active,), relation=MemoryRelation.CONTRADICTION
    )
    second = resolve_change(
        candidate, current=(active,), relation=MemoryRelation.CONTRADICTION
    )

    assert first == second
    assert first.new_version is not candidate
    assert active.status is VersionStatus.ACTIVE
