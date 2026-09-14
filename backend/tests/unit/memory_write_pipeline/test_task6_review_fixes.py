"""Regression tests for Task-6 generation, SET authority, and resolver safety.

Each test pins one approved plan contract that the current implementation
gets wrong:

- S1: a draft must carry its candidate's `suppression_generation`, and the
  resolver must refuse a candidate stamped with a generation older than the
  live assertion's (`plan:710-722`).
- S2: `desired_members` may contain only governed registry members — it is an
  input that becomes durable state, not free text (`plan:836-839`).
- C3: background/model-only evidence may propose compatible additions only;
  it cannot revoke or replace a set snapshot (`plan:899-903`).
- C4: deterministic set relation pre-check: contained -> `SAME`, growth ->
  `COMPATIBLE`, before any classifier relation is consulted (`plan:828-831`).
- C3b: a `CONTRADICTION` whose members do not overlap the active snapshot is
  still an inconsistent classifier output and fails closed (`plan:919-924`).
- Minor: `LifecycleFacts` generations must be positive integers.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys

import pytest

from backend.memory.lifecycle import LifecycleFacts
from backend.memory.write_pipeline.models import (
    Authority,
    ExplicitIntentError,
    MemoryCandidate,
    MemoryOperation,
    MemoryRelation,
    MemoryVersion,
    RetentionMode,
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
ACTIVITY_KEY = "travel.preference.activity_style"


def test_lifecycle_module_imports_in_a_fresh_process():
    """The pure policy owner must not depend on package import order."""
    root = Path(__file__).resolve().parents[4]
    completed = subprocess.run(
        [sys.executable, "-c", "import backend.memory.lifecycle"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


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
    identity = assertion_identity(
        _candidate(canonical_key=overrides.get("canonical_key", HOTEL_ATMOSPHERE_KEY))
    )
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
        "retention_mode": RetentionMode.USER_DURABLE,
    }
    payload.update(overrides)
    return MemoryVersion(**payload)


def _set_candidate(members, **overrides) -> MemoryCandidate:
    payload = {"observed_at": NEWER}
    payload.update(overrides)
    return _candidate(canonical_key=ACTIVITY_KEY, normalized_value=members, **payload)


def _set_version(members, **overrides) -> MemoryVersion:
    return _version(canonical_key=ACTIVITY_KEY, normalized_value=members, **overrides)


# ---------------------------------------------------------------------------
# S1. The generation stamp survives candidate -> draft, and a stale candidate
# is refused by the resolver before any change set is produced.
# ---------------------------------------------------------------------------


def test_the_draft_carries_the_candidate_generation():
    change = resolve_change(
        _candidate(suppression_generation=3), current=(), relation=MemoryRelation.UNRELATED
    )

    assert change.new_version is not None
    assert change.new_version.suppression_generation == 3


def test_a_stale_generation_candidate_is_refused():
    """Generation 7 evidence cannot mutate an assertion now in generation 9.

    This is the resurrection probe: without the refusal, delayed work after a
    REVOKE supersedes the still-live memory it observed before the revoke.
    """
    change = resolve_change(
        _candidate(
            normalized_value="lively",
            suppression_generation=7,
            observed_at=NEWER,
        ),
        current=(_version(suppression_generation=9),),
        relation=MemoryRelation.CONTRADICTION,
    )

    assert change.operation is MemoryOperation.REJECT


def test_a_current_generation_candidate_still_resolves():
    change = resolve_change(
        _candidate(
            normalized_value="lively",
            suppression_generation=4,
            observed_at=NEWER,
        ),
        current=(_version(suppression_generation=4),),
        relation=MemoryRelation.CONTRADICTION,
    )

    assert change.operation is MemoryOperation.SUPERSEDE


def test_single_value_contradiction_uses_authority_and_time_not_character_sets():
    """Distinct scalar values must reach the ordinary contradiction resolver."""
    current = _version(
        canonical_key="travel.profile.default_departure_city",
        normalized_value="da_nang",
        valid_from=MOMENT,
    )
    candidate = _candidate(
        canonical_key="travel.profile.default_departure_city",
        normalized_value="hue",
        observed_at=NEWER,
    )

    change = resolve_change(
        candidate, current=(current,), relation=MemoryRelation.CONTRADICTION
    )

    assert change.operation is MemoryOperation.SUPERSEDE
    assert change.reason == "newer_equal_authority_supersede"


# ---------------------------------------------------------------------------
# S2. desired_members becomes durable state, so it may only name governed
# registry members.
# ---------------------------------------------------------------------------


def test_a_desired_snapshot_with_an_ungoverned_member_is_refused():
    with pytest.raises(ValueError):
        resolve_change(
            _set_candidate(("nature",)),
            current=(_set_version(("nature",)),),
            relation=MemoryRelation.TEMPORAL_UPDATE,
            desired_members=("bogus",),
        )


def test_a_desired_snapshot_with_a_governed_member_replaces():
    change = resolve_change(
        _set_candidate(("nature",)),
        current=(_set_version(("food", "nature")),),
        relation=MemoryRelation.TEMPORAL_UPDATE,
        desired_members=("nature", "food"),
    )

    assert change.operation is MemoryOperation.SUPERSEDE
    assert change.new_version.normalized_value == ("food", "nature")


# ---------------------------------------------------------------------------
# C3. Background/model-only evidence proposes additions; it can never revoke
# or replace a set snapshot, whatever relation it claims.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "relation",
    [MemoryRelation.TEMPORAL_UPDATE, MemoryRelation.CONTRADICTION],
)
def test_background_cannot_revoke_or_replace_a_set(relation):
    """Equal-authority background evidence plus a desired snapshot is exactly
    the probe that reached REVOKE before the gate existed. A temporal-update
    claim violates the explicit-only channel loudly; a contradiction claim is
    refused as an inconsistent relation; neither mutates."""
    background = _set_candidate(
        ("food",), authority=Authority.REPEATED_INFERENCE
    )
    active = _set_version(
        ("culture", "food"), authority=Authority.REPEATED_INFERENCE
    )

    if relation is MemoryRelation.TEMPORAL_UPDATE:
        with pytest.raises(ExplicitIntentError):
            resolve_change(
                background,
                current=(active,),
                relation=relation,
                desired_members=("food",),
            )
    else:
        change = resolve_change(
            background,
            current=(active,),
            relation=relation,
            desired_members=("food",),
        )
        assert change.operation is MemoryOperation.REJECT


def test_background_cannot_revoke_by_omitting_the_desired_snapshot():
    """The reviewer's probe: a newer REPEATED_INFERENCE candidate with an empty
    desired snapshot must not become a revoke."""
    background = _set_candidate(
        ("food",), authority=Authority.REPEATED_INFERENCE
    )
    active = _set_version(
        ("culture", "food"), authority=Authority.REPEATED_INFERENCE
    )

    with pytest.raises(ExplicitIntentError):
        resolve_change(
            background,
            current=(active,),
            relation=MemoryRelation.TEMPORAL_UPDATE,
            desired_members=(),
        )


def test_explicit_authority_still_replaces_its_own_set():
    explicit = _set_candidate(("food",), authority=Authority.EXPLICIT_SAVE)
    active = _set_version(("culture", "food"), authority=Authority.EXPLICIT_SAVE)

    change = resolve_change(
        explicit,
        current=(active,),
        relation=MemoryRelation.TEMPORAL_UPDATE,
        desired_members=("food",),
    )

    assert change.operation is MemoryOperation.SUPERSEDE


# ---------------------------------------------------------------------------
# C4. The deterministic set pre-check resolves contained and growing evidence
# before any classifier relation is consulted.
# ---------------------------------------------------------------------------


def test_contained_positive_set_evidence_is_same_even_when_claimed_compatible():
    """Members already held -> deterministic `SAME`, whatever positive relation
    the caller claimed."""
    active = _set_version(("culture", "food"))

    change = resolve_change(
        _set_candidate(("food",)),
        current=(active,),
        relation=MemoryRelation.COMPATIBLE,
    )

    assert change.operation is MemoryOperation.REINFORCE


def test_growing_positive_set_evidence_is_compatible_even_when_claimed_same():
    active = _set_version(("culture", "food"))

    change = resolve_change(
        _set_candidate(("food", "nature")),
        current=(active,),
        relation=MemoryRelation.SAME,
    )

    assert change.operation is MemoryOperation.SUPERSEDE
    assert change.new_version.normalized_value == ("culture", "food", "nature")


@pytest.mark.parametrize(
    "members",
    [("food",), ("food", "nature"), ("photography",)],
)
def test_a_claimed_contradiction_on_a_set_never_mutates(members):
    """A contradiction claim on a set is never converted into a user action,
    whether it overlaps the snapshot or not (`plan:919-924`); an explicit
    correction travels through the materialised-snapshot channel instead."""
    change = resolve_change(
        _set_candidate(members),
        current=(_set_version(("culture", "food")),),
        relation=MemoryRelation.CONTRADICTION,
    )

    assert change.operation is MemoryOperation.REJECT
    assert change.reason == "rejected_relation_value_mismatch"


# ---------------------------------------------------------------------------
# C3b. A disjoint set CONTRADICTION is an inconsistent classifier output and
# fails closed; it must not fall through to `_contradiction_change`.
# ---------------------------------------------------------------------------


def test_a_disjoint_set_contradiction_fails_closed():
    change = resolve_change(
        _set_candidate(("photography",)),
        current=(_set_version(("culture", "food")),),
        relation=MemoryRelation.CONTRADICTION,
    )

    assert change.operation is MemoryOperation.REJECT
    assert change.reason == "rejected_relation_value_mismatch"


# ---------------------------------------------------------------------------
# Minor. LifecycleFacts generations are positive integers, not bare ints.
# ---------------------------------------------------------------------------


def test_a_non_positive_stamped_generation_is_refused():
    with pytest.raises(ValueError):
        LifecycleFacts(
            retention_mode=RetentionMode.USER_DURABLE,
            stamped_generation=-1,
            current_generation=-1,
            scope="user",
            sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        )


def test_zero_generation_is_refused():
    with pytest.raises(ValueError):
        LifecycleFacts(stamped_generation=0, current_generation=None)
