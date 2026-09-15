"""Unit tests for MemoryFormationEngine (Plan v0.18 / ADR 0038)."""

from datetime import datetime, timezone
import pytest

from backend.memory.formation import MemoryFormationEngine, FormedMemoryItem
from backend.memory.lifecycle import MemoryLifecyclePolicy, RetentionAssignmentPolicy
from backend.memory.source_handling import (
    MemoryFamily,
    SourceHandlingOutcome,
    SourceHandlingReason,
    SourceHandlingRecord,
)
from backend.memory.write_pipeline.models import (
    Authority,
    MemoryCandidate,
    MemoryEvidence,
    MemoryScope,
    RetentionMode,
    SensitivityBand,
    SourceValidity,
    new_candidate_id,
)
from backend.memory.write_pipeline.registry import HOTEL_ATMOSPHERE_KEY


class FakeModelAdapter:
    def __init__(self, candidates=()):
        self.candidates = tuple(candidates)
        self.extracted_messages = []

    def extract(self, messages, owner_user_id, conversation_id, evidence_ids=()):
        self.extracted_messages.extend(messages)
        return self.candidates


def _make_record(outcome: SourceHandlingOutcome) -> SourceHandlingRecord:
    return SourceHandlingRecord(
        source_outbox_id="cout_1",
        source_message_id="msg_1",
        family=MemoryFamily.SEMANTIC,
        outcome=outcome,
        reason_code=SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE if outcome == SourceHandlingOutcome.BACKGROUND_ELIGIBLE else SourceHandlingReason.EXPLICIT_ACTION,
        recorded_at=datetime.now(timezone.utc),
    )


def test_formation_refuses_when_source_handling_missing_unhandled():
    engine = MemoryFormationEngine(model_adapter=FakeModelAdapter())
    result = engine.form_memory(
        source_outbox_id="cout_1",
        source_message_id="msg_1",
        owner_user_id="user_1",
        conversation_id="conv_1",
        user_text="Tôi thích khách sạn yên tĩnh",
        source_handling_record=None,  # UNHANDLED
    )
    assert len(result) == 0


def test_formation_refuses_when_source_handling_not_background_eligible():
    engine = MemoryFormationEngine(model_adapter=FakeModelAdapter())
    for outcome in (
        SourceHandlingOutcome.EXPLICIT_APPLIED,
        SourceHandlingOutcome.EXPLICIT_REFUSED,
        SourceHandlingOutcome.EXPLICIT_NOOP,
        SourceHandlingOutcome.FORGET_APPLIED,
        SourceHandlingOutcome.FORGET_REFUSED,
    ):
        result = engine.form_memory(
            source_outbox_id="cout_1",
            source_message_id="msg_1",
            owner_user_id="user_1",
            conversation_id="conv_1",
            user_text="Tôi thích khách sạn yên tĩnh",
            source_handling_record=_make_record(outcome),
        )
        assert len(result) == 0


def test_pre_model_secret_scan_rejects_prohibited_content():
    fake_adapter = FakeModelAdapter()
    engine = MemoryFormationEngine(model_adapter=fake_adapter)
    result = engine.form_memory(
        source_outbox_id="cout_1",
        source_message_id="msg_1",
        owner_user_id="user_1",
        conversation_id="conv_1",
        user_text="API key sk-proj-1234567890abcdef1234567890abcdef",
        source_handling_record=_make_record(SourceHandlingOutcome.BACKGROUND_ELIGIBLE),
    )
    assert len(result) == 0
    # Pre-model check must not even pass messages to adapter
    assert len(fake_adapter.extracted_messages) == 0


def test_successful_formation_emits_evidence_candidate_and_retention():
    sample_candidate = MemoryCandidate(
        candidate_id=new_candidate_id(),
        evidence_ids=(),
        owner_user_id="user_1",
        scope=MemoryScope.CONVERSATION,
        conversation_id="conv_1",
        canonical_key=HOTEL_ATMOSPHERE_KEY,
        normalized_value="quiet",
        display_text="yên tĩnh",
        authority=Authority.REPEATED_INFERENCE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        observed_at=datetime.now(timezone.utc),
    )
    fake_adapter = FakeModelAdapter(candidates=[sample_candidate])
    engine = MemoryFormationEngine(model_adapter=fake_adapter)

    items = engine.form_memory(
        source_outbox_id="cout_1",
        source_message_id="msg_1",
        owner_user_id="user_1",
        conversation_id="conv_1",
        user_text="Tôi thích khách sạn yên tĩnh",
        source_handling_record=_make_record(SourceHandlingOutcome.BACKGROUND_ELIGIBLE),
    )
    assert len(items) == 1
    item = items[0]
    assert isinstance(item.evidence, MemoryEvidence)
    assert item.evidence.source_message_id == "msg_1"
    assert item.evidence.display_text == "Tôi thích khách sạn yên tĩnh"
    assert isinstance(item.candidate, MemoryCandidate)
    assert item.candidate.canonical_key == HOTEL_ATMOSPHERE_KEY
    assert item.candidate.normalized_value == "quiet"
    assert item.retention_mode == RetentionMode.CONVERSATION_BOUND


def test_formation_rejects_unknown_registry_key():
    bad_candidate = MemoryCandidate(
        candidate_id=new_candidate_id(),
        evidence_ids=(),
        owner_user_id="user_1",
        scope=MemoryScope.CONVERSATION,
        conversation_id="conv_1",
        canonical_key="unknown.key.fake",
        normalized_value="quiet",
        display_text="fake",
        authority=Authority.REPEATED_INFERENCE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        observed_at=datetime.now(timezone.utc),
    )
    fake_adapter = FakeModelAdapter(candidates=[bad_candidate])
    engine = MemoryFormationEngine(model_adapter=fake_adapter)

    items = engine.form_memory(
        source_outbox_id="cout_1",
        source_message_id="msg_1",
        owner_user_id="user_1",
        conversation_id="conv_1",
        user_text="Tôi thích khách sạn yên tĩnh",
        source_handling_record=_make_record(SourceHandlingOutcome.BACKGROUND_ELIGIBLE),
    )
    assert len(items) == 0


def test_formation_rejects_lifecycle_stale_generation():
    sample_candidate = MemoryCandidate(
        candidate_id=new_candidate_id(),
        evidence_ids=(),
        owner_user_id="user_1",
        scope=MemoryScope.CONVERSATION,
        conversation_id="conv_1",
        canonical_key=HOTEL_ATMOSPHERE_KEY,
        normalized_value="quiet",
        display_text="yên tĩnh",
        authority=Authority.REPEATED_INFERENCE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        observed_at=datetime.now(timezone.utc),
    )
    fake_adapter = FakeModelAdapter(candidates=[sample_candidate])
    engine = MemoryFormationEngine(model_adapter=fake_adapter)

    # Stamped gen 1, current gen 2 -> STALE_GENERATION
    items = engine.form_memory(
        source_outbox_id="cout_1",
        source_message_id="msg_1",
        owner_user_id="user_1",
        conversation_id="conv_1",
        user_text="Tôi thích khách sạn yên tĩnh",
        source_handling_record=_make_record(SourceHandlingOutcome.BACKGROUND_ELIGIBLE),
        stamped_generation=1,
        current_generation=2,
    )
    assert len(items) == 0


def test_formation_rejects_lifecycle_invalid_source():
    sample_candidate = MemoryCandidate(
        candidate_id=new_candidate_id(),
        evidence_ids=(),
        owner_user_id="user_1",
        scope=MemoryScope.CONVERSATION,
        conversation_id="conv_1",
        canonical_key=HOTEL_ATMOSPHERE_KEY,
        normalized_value="quiet",
        display_text="yên tĩnh",
        authority=Authority.REPEATED_INFERENCE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        observed_at=datetime.now(timezone.utc),
    )
    fake_adapter = FakeModelAdapter(candidates=[sample_candidate])
    engine = MemoryFormationEngine(model_adapter=fake_adapter)

    # source_validity DELETED -> SOURCE_INVALID
    items = engine.form_memory(
        source_outbox_id="cout_1",
        source_message_id="msg_1",
        owner_user_id="user_1",
        conversation_id="conv_1",
        user_text="Tôi thích khách sạn yên tĩnh",
        source_handling_record=_make_record(SourceHandlingOutcome.BACKGROUND_ELIGIBLE),
        source_validity=SourceValidity.INVALID,
    )
    assert len(items) == 0
