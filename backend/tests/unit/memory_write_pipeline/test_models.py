"""Unit tests for immutable semantic-memory write contracts.

Identity derives from owner, scope, key, subject, and condition only:
display text never defines identity, so a Vietnamese and an English
paraphrase of one normalized value share one assertion identity. No test
here touches a database, a model, HTTP, or the network.
"""

import dataclasses
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.memory.write_pipeline.models import (
    AssertionIdentity,
    Authority,
    Cardinality,
    MemoryCandidate,
    MemoryChangeSet,
    MemoryDecisionDraft,
    MemoryEvidence,
    MemoryOperation,
    MemoryRelation,
    MemoryVersion,
    MemoryVersionDraft,
    NormalizedSemanticValue,
    RetentionMode,
    SensitivityBand,
    VersionStatus,
    assertion_identity,
    new_candidate_id,
    new_evidence_id,
    new_version_id,
)
from backend.memory.write_pipeline.registry import HOTEL_ATMOSPHERE_KEY

REPO_ROOT = Path(__file__).resolve().parents[4]

MOMENT = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)


def _evidence(**overrides) -> MemoryEvidence:
    payload = {
        "evidence_id": new_evidence_id(),
        "owner_user_id": "user_owner",
        "conversation_id": "cv_example",
        "source_message_id": "ms_example",
        "display_text": "Tôi thích khách sạn yên tĩnh",
        "authority": Authority.EXPLICIT_STATEMENT,
        "observed_at": MOMENT,
    }
    payload.update(overrides)
    return MemoryEvidence(**payload)


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


def _decision(**overrides) -> MemoryDecisionDraft:
    payload = {
        "candidate_id": new_candidate_id(),
        "outcome": "direct_write",
        "reason": "direct_write_eligible",
    }
    payload.update(overrides)
    return MemoryDecisionDraft(**payload)


def _version_payload(**overrides) -> dict:
    payload = {
        "version_id": new_version_id(),
        "owner_user_id": "user_owner",
        "scope": "user",
        "scope_id": "user_owner",
        "canonical_key": HOTEL_ATMOSPHERE_KEY,
        "subject_key": "self",
        "condition_fingerprint": "e3b0c44298fc1c149afbf4c8996fb924",
        "normalized_value": "quiet",
        "display_text": "a quiet hotel",
        "authority": Authority.EXPLICIT_SAVE,
        "sensitivity": SensitivityBand.ORDINARY_PERSONAL,
        "status": VersionStatus.ACTIVE,
        "valid_from": MOMENT,
        "retention_mode": RetentionMode.USER_DURABLE,
    }
    payload.update(overrides)
    return payload


def _draft_payload(**overrides) -> dict:
    payload = {
        "owner_user_id": "user_owner",
        "scope": "user",
        "scope_id": "user_owner",
        "canonical_key": HOTEL_ATMOSPHERE_KEY,
        "subject_key": "self",
        "condition_fingerprint": "e3b0c44298fc1c149afbf4c8996fb924",
        "normalized_value": "lively",
        "display_text": "a lively hotel",
        "authority": Authority.EXPLICIT_SAVE,
        "sensitivity": SensitivityBand.ORDINARY_PERSONAL,
        "valid_from": MOMENT,
        "retention_mode": RetentionMode.USER_DURABLE,
    }
    payload.update(overrides)
    return payload


def _version(**overrides) -> MemoryVersion:
    return MemoryVersion(**_version_payload(**overrides))


def _draft(**overrides) -> MemoryVersionDraft:
    return MemoryVersionDraft(**_draft_payload(**overrides))


# 1. Governed identifier prefixes and UTC timestamps.


def test_generated_identifiers_use_governed_prefixes():
    assert new_evidence_id().startswith("mev_")
    assert new_candidate_id().startswith("mc_")
    assert new_version_id().startswith("mem_")


def test_generated_identifiers_differ_across_calls():
    assert new_candidate_id() != new_candidate_id()
    assert new_version_id() != new_version_id()


def test_timestamps_must_be_timezone_aware_utc():
    naive = datetime(2026, 9, 7, 12, 0, 0)
    with pytest.raises(ValueError):
        _evidence(observed_at=naive)
    with pytest.raises(ValueError):
        _candidate(observed_at=naive)
    with pytest.raises(ValueError):
        _version(valid_from=naive)


def test_contract_timestamps_normalize_to_utc():
    from datetime import timedelta

    offset = timezone(timedelta(hours=7))
    local = datetime(2026, 9, 7, 19, 0, 0, tzinfo=offset)
    assert _evidence(observed_at=local).observed_at.utcoffset().total_seconds() == 0
    assert _candidate(observed_at=local).observed_at == MOMENT


# 2. Frozen-dataclass immutability.


@pytest.mark.parametrize(
    "instance",
    [
        _evidence(),
        _candidate(),
        _decision(),
        _version(),
        AssertionIdentity(
            owner_user_id="user_owner",
            scope="user",
            scope_id="user_owner",
            canonical_key=HOTEL_ATMOSPHERE_KEY,
            subject_key="self",
            condition_fingerprint="abc",
        ),
    ],
)
def test_contracts_are_frozen(instance):
    with pytest.raises(dataclasses.FrozenInstanceError):
        instance.owner_user_id = "user_other"


def test_change_set_is_frozen():
    change = MemoryChangeSet(
        operation="add",
        identity=assertion_identity(_candidate()),
        new_version=_draft(),
        superseded_version_ids=(),
        reference_version_id=None,
        reason="first_add",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        change.reason = "other"


def test_change_set_accepts_a_draft_but_not_a_stored_version():
    change = MemoryChangeSet(
        operation="add",
        identity=assertion_identity(_candidate()),
        new_version=_draft(),
        superseded_version_ids=(),
        reference_version_id=None,
        reason="first_add",
    )
    assert change.new_version == _draft()
    with pytest.raises(ValueError):
        MemoryChangeSet(
            operation="add",
            identity=assertion_identity(_candidate()),
            new_version=_version(),
            superseded_version_ids=(),
            reference_version_id=None,
            reason="first_add",
        )


def test_version_draft_carries_no_identifier():
    draft = _draft()
    assert not hasattr(draft, "version_id")
    assert draft.status is VersionStatus.ACTIVE
    assert draft.valid_from == MOMENT
    with pytest.raises(dataclasses.FrozenInstanceError):
        draft.normalized_value = "quiet"


# 3. Shape validation: blank fields fail closed.


@pytest.mark.parametrize("field", ["owner_user_id", "display_text"])
def test_evidence_rejects_blank_fields(field):
    with pytest.raises(ValueError):
        _evidence(**{field: "   "})


@pytest.mark.parametrize(
    "field", ["owner_user_id", "canonical_key", "normalized_value", "display_text"]
)
def test_candidate_rejects_blank_fields(field):
    with pytest.raises(ValueError):
        _candidate(**{field: "   "})


def test_conversation_scope_requires_a_conversation():
    with pytest.raises(ValueError):
        _candidate(scope="conversation", conversation_id=None)
    scoped = _candidate(scope="conversation", conversation_id="cv_example")
    assert scoped.conversation_id == "cv_example"


# 4. Display text never defines identity.


def test_vietnamese_and_english_paraphrase_share_one_identity():
    vietnamese = _candidate(
        normalized_value="quiet", display_text="Tôi thích khách sạn yên tĩnh"
    )
    english = _candidate(
        normalized_value="quiet", display_text="I like a quiet hotel near the beach"
    )
    assert assertion_identity(vietnamese) == assertion_identity(english)


def test_empty_condition_wording_does_not_change_identity():
    first = _candidate(condition="", display_text="quiet room please")
    second = _candidate(condition="", display_text="yên tĩnh nhé")
    assert assertion_identity(first) == assertion_identity(second)


def test_identity_covers_owner_scope_key_subject_and_condition():
    identity = assertion_identity(_candidate())
    assert identity.owner_user_id == "user_owner"
    assert identity.scope == "user"
    assert identity.scope_id == "user_owner"
    assert identity.canonical_key == HOTEL_ATMOSPHERE_KEY
    assert identity.subject_key == "self"


def test_condition_fingerprint_is_deterministic():
    # Pins hash mechanics only: Phase-1 validation admits the empty
    # condition alone, so no non-empty rewording below shares a
    # pipeline identity.
    first = assertion_identity(_candidate(condition="  Beach Trip "))
    second = assertion_identity(_candidate(condition="beach trip"))
    assert first.condition_fingerprint == second.condition_fingerprint
    other = assertion_identity(_candidate(condition="city break"))
    assert other.condition_fingerprint != first.condition_fingerprint


def test_conversation_scope_identity_uses_the_conversation():
    scoped = _candidate(scope="conversation", conversation_id="cv_example")
    identity = assertion_identity(scoped)
    assert identity.scope == "conversation"
    assert identity.scope_id == "cv_example"
    assert identity != assertion_identity(_candidate())


# 5. Closed relation, operation, and sensitivity vocabularies.


def test_sensitivity_vocabulary_matches_adr_0017():
    assert {member.value for member in SensitivityBand} == {
        "ordinary_personal",
        "contextually_sensitive",
        "restricted",
        "prohibited_secret",
    }


def test_relation_vocabulary_is_closed():
    assert {member.value for member in MemoryRelation} == {
        "same",
        "compatible",
        "contradiction",
        "temporal_update",
        "scope_exception",
        "unrelated",
        "uncertain",
    }


def test_operation_vocabulary_is_closed():
    assert {member.value for member in MemoryOperation} == {
        "add",
        "reinforce",
        "supersede",
        "add_exception",
        "pending_conflict",
        "reject",
        "noop",
        "revoke",
    }


def test_version_defaults_to_active_without_a_predecessor():
    version = _version()
    assert version.status is VersionStatus.ACTIVE
    assert version.supersedes_version_id is None


# ---------------------------------------------------------------------------
# Task 6: cardinality, retention, revocation, temporal validity, generation.
# ---------------------------------------------------------------------------


def test_cardinality_vocabulary_is_single_and_set():
    """`SET` is the only addition; the vocabulary stays closed at two."""
    assert {member.value for member in Cardinality} == {"single", "set"}


def test_retention_vocabulary_is_closed():
    """Three retention modes, and they are independent of authority."""
    assert {member.value for member in RetentionMode} == {
        "conversation_bound",
        "source_bound",
        "user_durable",
    }


def test_version_status_adds_revoked():
    """`REVOKED` is a lifecycle state, not a deletion."""
    assert {member.value for member in VersionStatus} == {
        "active",
        "superseded",
        "revoked",
    }


def test_normalized_semantic_value_is_the_declared_union():
    """The set representation is declared, never inferred from delimiters."""
    assert NormalizedSemanticValue == str | tuple[str, ...]


def test_a_single_keyed_candidate_still_carries_one_string():
    """The existing single-valued shape is unchanged."""
    assert _candidate(normalized_value="quiet").normalized_value == "quiet"


def test_a_set_keyed_candidate_carries_a_tuple():
    candidate = _candidate(
        normalized_value=("culture", "food"),
        canonical_key="travel.preference.activity_style",
    )
    assert candidate.normalized_value == ("culture", "food")


@pytest.mark.parametrize(
    "value",
    [
        (),  # empty set is a revoke, not a stored snapshot
        ("food", "culture"),  # unsorted
        ("culture", "culture"),  # duplicated
        ("culture", "   "),  # blank member
        ("culture", 7),  # non-string member
        ["culture", "food"],  # list, not a tuple
    ],
)
def test_a_set_value_rejects_a_malformed_snapshot(value):
    """Sorted, deduplicated, non-empty and string-typed, or refused.

    A set that reaches persistence unsorted would make the stored snapshot
    depend on the order evidence arrived in, and one that carries a duplicate
    would make a re-read compare unequal to itself.

    Surrounding whitespace is *not* in this list on purpose: members are
    trimmed like every other text field, and a member that becomes blank after
    trimming is rejected by the blank case above.
    """
    with pytest.raises(ValueError):
        _candidate(
            normalized_value=value,
            canonical_key="travel.preference.activity_style",
        )


def test_a_set_member_is_trimmed_and_order_is_checked_after_trimming():
    """Trimming happens first, so trimming cannot smuggle an out-of-order set in.

    `(" food", "culture")` is only ascending once the first member is trimmed,
    which is exactly the case that must still be refused.
    """
    assert _candidate(
        normalized_value=("culture", " food"),
        canonical_key="travel.preference.activity_style",
    ).normalized_value == ("culture", "food")

    with pytest.raises(ValueError):
        _candidate(
            normalized_value=(" food", "culture"),
            canonical_key="travel.preference.activity_style",
        )


def test_a_version_and_draft_accept_the_same_set_contract():
    """The contract is one shape across candidate, draft, and version."""
    draft = _draft(normalized_value=("cafe", "local"))
    version = _version(normalized_value=("cafe", "local"))

    assert draft.normalized_value == ("cafe", "local")
    assert version.normalized_value == ("cafe", "local")


def test_generation_defaults_to_one():
    """A new assertion starts at generation 1 (spec v0.7, plan v0.11)."""
    assert _candidate().suppression_generation == 1
    assert _draft().suppression_generation == 1
    assert _version().suppression_generation == 1


@pytest.mark.parametrize("value", [0, -1])
def test_generation_must_be_positive(value):
    with pytest.raises(ValueError):
        _candidate(suppression_generation=value)


def test_generation_rejects_a_bool():
    """`True` is an `int` in Python and would silently become generation 1."""
    with pytest.raises(ValueError):
        _candidate(suppression_generation=True)


def test_a_version_carries_the_generation_it_was_stamped_with():
    assert _version(suppression_generation=4).suppression_generation == 4


def test_expires_at_is_optional():
    """Temporal validity is an independent dimension, not a required one."""
    assert _draft().expires_at is None
    assert _version().expires_at is None


def test_expires_at_is_normalized_to_utc():
    bangkok = timezone(timedelta(hours=7))
    draft = _draft(expires_at=datetime(2026, 10, 1, 9, 0, tzinfo=bangkok))

    assert draft.expires_at == datetime(2026, 10, 1, 2, 0, tzinfo=timezone.utc)
    assert draft.expires_at.utcoffset() == timedelta(0)


def test_expires_at_rejects_a_naive_datetime():
    """A naive expiry would expire at a different instant per host."""
    with pytest.raises(ValueError):
        _draft(expires_at=datetime(2026, 10, 1, 9, 0))


def test_expiry_does_not_mutate_retention_or_generation():
    """The three dimensions stay independent (ADR 0037).

    Setting a temporal expiry must not touch retention or the generation: they
    answer different questions, and a reader that conflated them would treat an
    expired value as forgotten (or the reverse).
    """
    expiring = _draft(
        expires_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        retention_mode=RetentionMode.USER_DURABLE,
        suppression_generation=3,
    )

    assert expiring.retention_mode is RetentionMode.USER_DURABLE
    assert expiring.suppression_generation == 3
    assert expiring.expires_at == datetime(2026, 10, 1, tzinfo=timezone.utc)


def test_no_retention_mode_is_ever_defaulted():
    """Neither contract invents a retention mode.

    A defaulted *mode* means a construction path that skipped
    `RetentionAssignmentPolicy` still persists a decision — just not one anybody
    made. Both classes require the assignment outright.
    """
    for cls in (MemoryVersion, MemoryVersionDraft):
        declared = {field.name: field for field in dataclasses.fields(cls)}[
            "retention_mode"
        ]

        assert declared.default is dataclasses.MISSING, cls
        assert declared.default_factory is dataclasses.MISSING, cls


def test_the_draft_requires_a_retention_assignment():
    """The write path is where a missed assignment is the hazard."""
    payload = _draft_payload()
    del payload["retention_mode"]

    with pytest.raises(TypeError):
        MemoryVersionDraft(**payload)


def test_the_version_also_requires_a_retention_assignment():
    """The read path reads retention back from storage, so absence is an error.

    A version with no retention could only come from a row the migration had not
    reached, and defaulting one here would hand it a decision nobody made.
    """
    payload = _version_payload()
    del payload["retention_mode"]

    with pytest.raises(TypeError):
        MemoryVersion(**payload)


def test_retention_is_persisted_exactly_as_assigned():
    """The field round-trips; the contract does not reinterpret it."""
    for mode in RetentionMode:
        assert _version(retention_mode=mode).retention_mode is mode
        assert _draft(retention_mode=mode).retention_mode is mode


def test_retention_rejects_an_unknown_mode():
    with pytest.raises(ValueError):
        _version(retention_mode="forever")


_STALE_SINGLE_ONLY_CLAIMS = {
    "backend/memory/write_pipeline/models.py": (
        "one single-valued assertion",
        "Scopes the first registry key",
    ),
}


@pytest.mark.parametrize(
    ("relative_path", "phrase"),
    [
        (path, phrase)
        for path, phrases in _STALE_SINGLE_ONLY_CLAIMS.items()
        for phrase in phrases
    ],
)
def test_no_stale_single_only_claim_survives(relative_path, phrase):
    """The registry is no longer one key and assertions are no longer all single.

    `plan v0.11` requires the stale single-only docstrings and comments to be
    updated rather than left implying every assertion holds one value. A
    comment that outlives the contract it described is how a reader learns the
    wrong rule.
    """
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")

    assert phrase not in source, f"stale claim still present in {relative_path}"
