"""Unit tests for immutable semantic-memory write contracts.

Identity derives from owner, scope, key, subject, and condition only:
display text never defines identity, so a Vietnamese and an English
paraphrase of one normalized value share one assertion identity. No test
here touches a database, a model, HTTP, or the network.
"""

import dataclasses
from datetime import datetime, timezone

import pytest

from backend.memory.write_pipeline.models import (
    AssertionIdentity,
    Authority,
    MemoryCandidate,
    MemoryChangeSet,
    MemoryDecisionDraft,
    MemoryEvidence,
    MemoryOperation,
    MemoryRelation,
    MemoryVersion,
    MemoryVersionDraft,
    SensitivityBand,
    VersionStatus,
    assertion_identity,
    new_candidate_id,
    new_evidence_id,
    new_version_id,
)
from backend.memory.write_pipeline.registry import HOTEL_ATMOSPHERE_KEY

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


def _version(**overrides) -> MemoryVersion:
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
    }
    payload.update(overrides)
    return MemoryVersion(**payload)


def _draft(**overrides) -> MemoryVersionDraft:
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
    }
    payload.update(overrides)
    return MemoryVersionDraft(**payload)


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
    }


def test_version_defaults_to_active_without_a_predecessor():
    version = _version()
    assert version.status is VersionStatus.ACTIVE
    assert version.supersedes_version_id is None
