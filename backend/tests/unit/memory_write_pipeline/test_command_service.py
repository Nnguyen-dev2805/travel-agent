"""Unit tests for the risk-based memory command service.

Confirm-all is superseded: low-risk remember/correct commits directly
and returns an application-owned saved event only after commit, while
bulk delete and scope expansion travel through bounded one-time
preview tokens. No test here touches a database, a model, HTTP, or
the network: the unit of work, reads, and control writes are fakes.
"""

from datetime import datetime, timezone

import pytest

from backend.memory.write_pipeline.models import (
    Authority,
    MemoryOperation,
    MemoryScope,
    MemoryVersion,
    SensitivityBand,
    VersionStatus,
    assertion_identity,
    new_candidate_id,
    new_evidence_id,
    new_version_id,
)
from backend.memory.write_pipeline.service import (
    BulkCommitted,
    DeletedEvent,
    HeldEvent,
    MemoryCommandNotFoundError,
    MemoryCommandService,
    MemoryCommandStaleError,
    MemoryCommandValidationError,
    PreviewOffer,
    RefusedEvent,
    SavedEvent,
    ToggledEvent,
    UndoDescriptor,
    parse_utterance,
)
from backend.memory.write_pipeline.uow import (
    CrossOwnerDeniedError,
    MemoryWriteError,
    MemoryWriteResult,
)
from backend.security.models import AuthenticatedPrincipal, AuthMode

MOMENT = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
NEWER = datetime(2026, 9, 7, 13, 0, 0, tzinfo=timezone.utc)


def _principal(owner="owner_a"):
    return AuthenticatedPrincipal(
        owner_user_id=owner,
        auth_mode=AuthMode.AUTHENTICATED,
        credential_label="test",
    )


def _candidate(**overrides):
    from backend.memory.write_pipeline.models import MemoryCandidate

    payload = {
        "candidate_id": new_candidate_id(),
        "evidence_ids": (new_evidence_id(),),
        "owner_user_id": "owner_a",
        "scope": MemoryScope.USER,
        "conversation_id": None,
        "canonical_key": "travel.preference.hotel_atmosphere",
        "normalized_value": "quiet",
        "display_text": "a quiet hotel",
        "authority": Authority.EXPLICIT_SAVE,
        "sensitivity": SensitivityBand.ORDINARY_PERSONAL,
        "observed_at": MOMENT,
    }
    payload.update(overrides)
    return MemoryCandidate(**payload)


def _version(**overrides):
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


class FakeUoW:
    """Scripted unit of work recording every apply call."""

    def __init__(self):
        self.calls = []
        self.failures = {}

    def apply_memory_change(
        self,
        change,
        principal,
        *,
        evidence=(),
        decision=None,
        idempotency_key=None,
        expected_version_id=None,
    ):
        self.calls.append(
            {
                "change": change,
                "principal": principal,
                "evidence": evidence,
                "decision": decision,
                "idempotency_key": idempotency_key,
                "expected_version_id": expected_version_id,
            }
        )
        if idempotency_key in self.failures:
            raise self.failures[idempotency_key]
        streaming = change.operation in (
            MemoryOperation.ADD,
            MemoryOperation.SUPERSEDE,
            MemoryOperation.ADD_EXCEPTION,
        )
        return MemoryWriteResult(
            operation=change.operation,
            version_id="mem_committed" if streaming else None,
            superseded_version_ids=tuple(change.superseded_version_ids),
            reference_version_id=change.reference_version_id,
            decision_id="mdc_committed" if decision is not None else None,
            reason=change.reason,
        )


class FakeStore:
    """In-memory versions with read and control-write seams."""

    def __init__(self, versions=()):
        self.versions = list(versions)
        self.delete_calls = []
        self.bulk_calls = []
        self.fail_delete = None

    def read_versions(self, identity):
        return tuple(
            item
            for item in self.versions
            if (
                item.owner_user_id == identity.owner_user_id
                and item.scope == identity.scope
                and item.scope_id == identity.scope_id
                and item.canonical_key == identity.canonical_key
                and item.subject_key == identity.subject_key
                and item.condition_fingerprint == identity.condition_fingerprint
            )
        )

    def list_active(self, owner):
        return tuple(
            item
            for item in self.versions
            if item.owner_user_id == owner and item.status is VersionStatus.ACTIVE
        )

    def commit_delete_one(self, owner, version_id, reason):
        self.delete_calls.append((owner, version_id, reason))
        if self.fail_delete is not None:
            raise self.fail_delete
        for index, item in enumerate(self.versions):
            if item.version_id == version_id and item.owner_user_id == owner:
                import dataclasses

                self.versions[index] = dataclasses.replace(
                    item, status=VersionStatus.SUPERSEDED
                )
                return UndoDescriptor(
                    action="restore",
                    version_ids=(version_id,),
                    note="Restore keeps history; re-check scope before restoring.",
                )
        raise AssertionError("fake store has no such owned version")

    def commit_bulk_delete(self, owner, version_ids, reason):
        self.bulk_calls.append((owner, tuple(version_ids), reason))
        if self.fail_delete is not None:
            raise self.fail_delete
        return UndoDescriptor(
            action="restore",
            version_ids=tuple(version_ids),
            note="Restore keeps history; re-check scope before restoring.",
        )


def _service(store=None, uow=None, clock=None):
    store = store if store is not None else FakeStore()
    uow = uow if uow is not None else FakeUoW()
    kwargs = {
        "uow": uow,
        "read_versions": store.read_versions,
        "list_active_versions": store.list_active,
        "commit_delete_one": store.commit_delete_one,
        "commit_bulk_delete": store.commit_bulk_delete,
    }
    if clock is not None:
        kwargs["clock"] = clock
    service = MemoryCommandService(**kwargs)
    return service, store, uow


# 1. Minimal NL intent parsing across both languages.


@pytest.mark.parametrize(
    ("utterance", "action", "value", "scope"),
    [
        ("remember quiet hotels", "remember", "quiet", None),
        ("hãy nhớ khách sạn yên tĩnh", "remember", "quiet", None),
        ("prefer a lively area in this chat", "remember", "lively", "conversation"),
        ("sửa lại thành trung tâm", "correct", "central", None),
        ("thực ra tôi thích biệt lập", "correct", "secluded", None),
        ("delete quiet", "delete", "quiet", None),
        ("forget lively memories", "delete", "lively", None),
        ("enable memory", "enable", None, None),
        ("tắt memory", "disable", None, None),
        ("what is the weather", "unknown", None, None),
    ],
)
def test_parse_utterance_matrix(utterance, action, value, scope):
    intent = parse_utterance(utterance)
    assert intent.action == action
    assert intent.value == value
    assert intent.scope == scope
    assert intent.ambiguous is False


def test_parse_utterance_marks_two_values_ambiguous():
    intent = parse_utterance("remember quiet lively hotels")
    assert intent.ambiguous is True


# 2. Remember commits directly and reports an app-owned saved event.


def test_remember_direct_saves_after_commit():
    service, store, uow = _service()
    result = service.handle_utterance(
        _principal(), "remember quiet hotels", idempotency_key="key-remember"
    )

    assert isinstance(result, SavedEvent)
    assert result.operation == "add"
    assert result.scope == "user"
    assert result.canonical_key == "travel.preference.hotel_atmosphere"
    assert result.normalized_value == "quiet"
    assert result.version_id == "mem_committed"
    assert len(uow.calls) == 1
    call = uow.calls[0]
    assert call["idempotency_key"] == "key-remember"
    assert call["decision"] is not None
    assert call["principal"].owner_user_id == "owner_a"


def test_remember_mints_idempotency_key_when_absent():
    service, store, uow = _service()
    service.handle_utterance(_principal(), "remember quiet hotels")

    assert len(uow.calls) == 1
    assert isinstance(uow.calls[0]["idempotency_key"], str)
    assert uow.calls[0]["idempotency_key"]


def test_correct_direct_supersedes_with_expected_version():
    active = _version()
    service, store, uow = _service(FakeStore([active]))
    result = service.handle_utterance(
        _principal(), "sửa lại thành trung tâm", idempotency_key="key-correct"
    )

    assert isinstance(result, SavedEvent)
    assert result.operation == "supersede"
    assert result.normalized_value == "central"
    assert len(uow.calls) == 1
    assert uow.calls[0]["expected_version_id"] == active.version_id


# 3. Delete-one commits directly and returns an undo descriptor.


def test_delete_one_direct_commits_with_undo():
    active = _version()
    service, store, uow = _service(FakeStore([active]))
    result = service.handle_utterance(_principal(), "delete quiet")

    assert isinstance(result, DeletedEvent)
    assert result.deleted_version_ids == (active.version_id,)
    assert result.undo.version_ids == (active.version_id,)
    assert store.delete_calls == [("owner_a", active.version_id, "user_delete")]
    assert uow.calls == []


def test_delete_without_match_refuses_without_mutation():
    service, store, uow = _service()
    result = service.handle_utterance(_principal(), "delete quiet")

    assert isinstance(result, RefusedEvent)
    assert store.delete_calls == [] and store.bulk_calls == [] and uow.calls == []


# 4. Toggles validate and acknowledge without durable writes.


def test_toggle_direct_acknowledges_without_persistence():
    service, store, uow = _service(FakeStore([_version()]))
    result = service.handle_utterance(_principal(), "disable memory")

    assert isinstance(result, ToggledEvent)
    assert result.effective is False
    assert result.persistent is False
    assert "non-persistent" in result.note
    assert store.delete_calls == [] and store.bulk_calls == [] and uow.calls == []


# 5. Bulk delete travels through a bounded one-time token.


def test_bulk_delete_preview_token_confirm_commit():
    first = _version()
    second = _version(normalized_value="lively", display_text="lively hotel")
    service, store, uow = _service(FakeStore([first, second]))

    offered = service.handle_utterance(_principal(), "delete")
    assert isinstance(offered, PreviewOffer)
    assert len(offered.display.targets) == 2
    assert offered.token and offered.preview_id
    assert uow.calls == [] and store.bulk_calls == []

    committed = service.confirm_preview(_principal(), offered.preview_id, offered.token)
    assert isinstance(committed, BulkCommitted)
    assert committed.committed_version_ids == (first.version_id, second.version_id)
    assert committed.undo.version_ids == (first.version_id, second.version_id)
    assert store.bulk_calls == [
        ("owner_a", (first.version_id, second.version_id), "bulk_delete")
    ]

    with pytest.raises(MemoryCommandNotFoundError):
        service.confirm_preview(_principal(), offered.preview_id, offered.token)


def test_preview_wrong_token_and_foreign_owner_miss_without_mutation():
    service, store, uow = _service(FakeStore([_version(), _version()]))
    offered = service.handle_utterance(_principal(), "delete")

    with pytest.raises(MemoryCommandNotFoundError):
        service.confirm_preview(_principal(), offered.preview_id, "wrong-token")
    with pytest.raises(CrossOwnerDeniedError):
        service.confirm_preview(
            _principal("owner_b"), offered.preview_id, offered.token
        )
    assert store.bulk_calls == [] and uow.calls == []


def test_preview_expiry_and_stale_reject_without_mutation():
    now = [1000.0]
    service, store, uow = _service(
        FakeStore([_version(), _version()]), clock=lambda: now[0]
    )
    offered = service.handle_utterance(_principal(), "delete")

    now[0] += 10_000.0
    with pytest.raises(MemoryCommandNotFoundError):
        service.confirm_preview(_principal(), offered.preview_id, offered.token)
    assert store.bulk_calls == [] and uow.calls == []

    now[0] = 1000.0
    fresh = service.handle_utterance(_principal(), "delete")
    store.versions.pop()
    with pytest.raises(MemoryCommandStaleError):
        service.confirm_preview(_principal(), fresh.preview_id, fresh.token)
    assert store.bulk_calls == [] and uow.calls == []


def test_empty_preview_input_is_rejected():
    service, store, uow = _service()
    with pytest.raises(MemoryCommandValidationError):
        service.delete_versions(_principal(), ())


# 6. Sensitive input is held with no store and no prompt.


def test_prohibited_secret_is_refused_without_mutation_or_leak():
    service, store, uow = _service()
    utterance = "remember api key sk-test-AbC999 please"
    result = service.handle_utterance(_principal(), utterance)

    assert isinstance(result, RefusedEvent)
    assert uow.calls == [] and store.delete_calls == [] and store.bulk_calls == []
    assert "sk-test-AbC999" not in str(result)


# 7. Exact operation/scope display and ack-only-after-commit.


def test_preview_display_names_operation_and_scopes():
    first = _version()
    service, store, uow = _service(FakeStore([first, first]))
    offered = service.handle_utterance(_principal(), "delete")

    assert offered.display.operation == "bulk_delete"
    assert {target.scope for target in offered.display.targets} == {"user"}
    assert {target.normalized_value for target in offered.display.targets} == {"quiet"}


def test_ack_only_after_commit():
    service, store, uow = _service()
    uow.failures["key-boom"] = MemoryWriteError("injected commit failure")
    with pytest.raises(MemoryWriteError):
        service.handle_utterance(
            _principal(), "remember quiet hotels", idempotency_key="key-boom"
        )
    assert len(uow.calls) == 1


# 8. Scope expansion flow (preview -> confirm -> commit + tombstone old conversation).


def _conversation_version(**overrides):
    conv_id = "cv_room_1"
    candidate = _candidate(
        scope=MemoryScope.CONVERSATION,
        conversation_id=conv_id,
        normalized_value="lively",
    )
    identity = assertion_identity(candidate)
    payload = {
        "version_id": new_version_id(),
        "owner_user_id": identity.owner_user_id,
        "scope": identity.scope,
        "scope_id": identity.scope_id,
        "canonical_key": identity.canonical_key,
        "subject_key": identity.subject_key,
        "condition_fingerprint": identity.condition_fingerprint,
        "normalized_value": "lively",
        "display_text": "a lively atmosphere",
        "authority": Authority.EXPLICIT_SAVE,
        "sensitivity": SensitivityBand.ORDINARY_PERSONAL,
        "status": VersionStatus.ACTIVE,
        "valid_from": MOMENT,
    }
    payload.update(overrides)
    return MemoryVersion(**payload)


def test_preview_scope_expansion_success():
    conv_ver = _conversation_version()
    service, store, uow = _service(FakeStore([conv_ver]))

    offer = service.preview_scope_expansion(_principal(), conv_ver.version_id)
    assert isinstance(offer, PreviewOffer)
    assert offer.display.operation == "scope_expansion"
    assert len(offer.display.targets) == 1
    target = offer.display.targets[0]
    assert target.version_id == conv_ver.version_id
    assert target.old_scope == "conversation"
    assert target.new_scope == "user"
    assert target.scope == "conversation"
    assert target.normalized_value == "lively"


def test_preview_scope_expansion_requires_conversation_scope():
    user_ver = _version()
    service, store, uow = _service(FakeStore([user_ver]))

    with pytest.raises(MemoryCommandValidationError, match="Only conversation scope expands"):
        service.preview_scope_expansion(_principal(), user_ver.version_id)


def test_preview_scope_expansion_missing_or_foreign():
    service, store, uow = _service(FakeStore([_conversation_version()]))

    with pytest.raises(MemoryCommandNotFoundError):
        service.preview_scope_expansion(_principal(), "mem_nonexistent")

    with pytest.raises(MemoryCommandNotFoundError):
        service.preview_scope_expansion(_principal("owner_other"), _conversation_version().version_id)


def test_confirm_scope_expansion_success_and_tombstones_conversation_version():
    conv_ver = _conversation_version()
    service, store, uow = _service(FakeStore([conv_ver]))

    offer = service.preview_scope_expansion(_principal(), conv_ver.version_id)
    result = service.confirm_preview(_principal(), offer.preview_id, offer.token)

    assert isinstance(result, SavedEvent)
    assert result.scope == "user"
    assert result.normalized_value == "lively"
    assert result.operation == "add"

    # UoW committed the new user version
    assert len(uow.calls) == 1
    assert uow.calls[0]["change"].identity.scope == MemoryScope.USER

    # Store tombstoned the old conversation version
    assert store.delete_calls == [("owner_a", conv_ver.version_id, "scope_expansion")]
    assert conv_ver.version_id not in [item.version_id for item in store.list_active("owner_a")]

    # Token is spent
    with pytest.raises(MemoryCommandNotFoundError):
        service.confirm_preview(_principal(), offer.preview_id, offer.token)


def test_confirm_scope_expansion_stale_if_user_already_has_active_memory():
    conv_ver = _conversation_version()
    service, store, uow = _service(FakeStore([conv_ver]))

    offer = service.preview_scope_expansion(_principal(), conv_ver.version_id)

    # Concurrently, a user-level active memory is added
    user_ver = _version(normalized_value="quiet")
    store.versions.append(user_ver)

    with pytest.raises(MemoryCommandStaleError):
        service.confirm_preview(_principal(), offer.preview_id, offer.token)


def test_record_shadow_candidate_persists_as_shadow_without_active_versions():
    from backend.memory.write_pipeline.models import (
        Authority,
        MemoryEvidence,
        MemoryOperation,
        new_evidence_id,
    )
    from backend.memory.write_pipeline.policy import DecisionOutcome
    from backend.memory.write_pipeline.uow import CrossOwnerDeniedError

    service, store, uow = _service()
    principal = _principal("owner_a")

    candidate = _candidate(
        owner_user_id="owner_a",
        authority=Authority.REPEATED_INFERENCE,
        display_text="I prefer quiet hotels",
    )
    evidence = MemoryEvidence(
        evidence_id=new_evidence_id(),
        owner_user_id="owner_a",
        conversation_id="cv_123",
        source_message_id="ms_456",
        display_text="I prefer quiet hotels",
        authority=Authority.REPEATED_INFERENCE,
        observed_at=MOMENT,
    )

    result = service.record_shadow_candidate(
        principal, candidate, evidence, idempotency_key="bg_key_1"
    )

    assert len(uow.calls) == 1
    call = uow.calls[0]
    assert call["change"].operation is MemoryOperation.NOOP
    assert call["change"].new_version is None
    assert call["decision"].outcome is DecisionOutcome.SHADOW
    assert call["evidence"] == (evidence,)
    assert call["idempotency_key"] == "bg_key_1"

    # Cross-owner rejected
    foreign_principal = _principal("owner_b")
    with pytest.raises(CrossOwnerDeniedError):
        service.record_shadow_candidate(foreign_principal, candidate, evidence)

