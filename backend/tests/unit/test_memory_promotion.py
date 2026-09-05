"""Unit tests for R6 candidate-to-record promotion.

The policy is exercised directly with contract fixtures and through the
service with in-memory fakes plus the real deterministic extractor. No test
modifies R5 extraction or policy behavior to widen promotion coverage.

No test here touches a real database, a model provider, Chroma, or the
network.
"""

from datetime import datetime, timedelta, timezone

import pytest

from backend.conversations.models import (
    Conversation,
    Message,
    MessageRole,
    MessageSource,
    TraceVisibility,
    generate_conversation_id,
    generate_message_id,
)
from backend.conversations.service import (
    ConversationNotFoundError,
    WorkspaceNotFoundError,
)
from backend.memory.extraction import RuleBasedMemoryExtractor
from backend.memory.models import (
    MemoryCandidate,
    MemoryCandidateStatus,
    MemoryExtractionTrigger,
    MemoryRecordScope,
    MemoryRecordStatus,
    MemoryScope,
    MemoryType,
    MemoryValidationError,
    PolicyReason,
    PromotionSkipReason,
    SensitivityLabel,
    generate_memory_candidate_id,
)
from backend.memory.policy import MemoryPolicy
from backend.memory.promotion import (
    MEMORY_PROMOTION_MIN_CONFIDENCE,
    PROMOTABLE_REASONS,
    MemoryPromotionPolicy,
)
from backend.memory.service import (
    MemoryScopeMismatchError,
    MemoryService,
)
from backend.workspaces.models import TripWorkspace, generate_workspace_id

MOMENT = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)

PREFERENCE_TEXT = "Tôi ăn chay trường, hãy nhớ giúp tôi."
CONSTRAINT_TEXT = "Ngân sách chuyến này tối đa 20 triệu."
CORRECTION_TEXT = "Thực ra tôi đổi sang đi tàu hỏa, sửa lại giúp tôi."
SIBLING_CORRECTION_TEXT = "Thực ra tôi thích núi hơn, sửa lại giúp tôi."
"""One sentence the R5 extractor reads as both a correction and a preference."""


class FakeWorkspaceRepository:
    def __init__(self, workspaces=()):
        self._workspaces = {item.workspace_id: item for item in workspaces}

    def get(self, workspace_id):
        return self._workspaces.get(workspace_id)

    def list_by_owner(self, owner_user_id):
        raise AssertionError("out of scope for promotion tests")


class FakeConversationRepository:
    def __init__(self, conversations=(), messages=()):
        self._conversations = {item.conversation_id: item for item in conversations}
        self._messages = {item.message_id: item for item in messages}

    def get(self, conversation_id):
        return self._conversations.get(conversation_id)

    def list_by_workspace(self, workspace_id):
        raise AssertionError("out of scope for promotion tests")

    def append_message(self, message, message_id):
        raise AssertionError("promotion never appends messages")

    def get_message(self, message_id):
        return self._messages.get(message_id)

    def list_messages(self, conversation_id, after_sequence, limit):
        raise AssertionError("promotion never lists history")


class FakeMemoryRepository:
    def __init__(self):
        self.runs = {}
        self.candidates = []
        self.records = {}
        self.promotion_runs = {}
        self.traces = []

    def create_run(self, run):
        self.runs[run.run_id] = run
        return run

    def create_candidates(self, candidates):
        ordered = tuple(candidates)
        self.candidates.extend(ordered)
        return ordered

    def list_runs(self, workspace_id, conversation_id=None):
        return tuple(
            run
            for run in self.runs.values()
            if run.workspace_id == workspace_id
            and (conversation_id is None or run.conversation_id == conversation_id)
        )

    def list_candidates(self, run_id=None, workspace_id=None, conversation_id=None):
        return tuple(
            item
            for item in self.candidates
            if (run_id is None or item.run_id == run_id)
            and (workspace_id is None or item.workspace_id == workspace_id)
            and (conversation_id is None or item.conversation_id == conversation_id)
        )

    def create_promotion_run(self, run):
        self.promotion_runs[run.promotion_run_id] = run
        return run

    def create_records(self, records):
        ordered = tuple(records)
        for record in ordered:
            self.records[record.memory_id] = record
        return ordered

    def list_records(
        self,
        workspace_id=None,
        conversation_id=None,
        owner_user_id=None,
        scope=None,
        status=None,
    ):
        def value(item):
            return getattr(item, "value", item)

        return tuple(
            record
            for record in self.records.values()
            if (workspace_id is None or record.workspace_id == workspace_id)
            and (conversation_id is None or record.conversation_id == conversation_id)
            and (owner_user_id is None or record.owner_user_id == owner_user_id)
            and (scope is None or value(record.scope) == value(scope))
            and (status is None or value(record.status) == value(status))
        )

    def mark_records_superseded(self, memory_ids):
        flipped = 0
        for memory_id in memory_ids:
            record = self.records.get(memory_id)
            if record is not None and record.status is MemoryRecordStatus.ACTIVE:
                import dataclasses

                self.records[memory_id] = dataclasses.replace(
                    record, status=MemoryRecordStatus.SUPERSEDED
                )
                flipped += 1
        return flipped

    def write_retrieval_event(self, trace):
        self.traces.append(trace)
        return trace

    def list_retrieval_events(self, workspace_id=None, conversation_id=None):
        return tuple(self.traces)


def _workspace(**overrides):
    payload = {
        "workspace_id": "tw_promo",
        "owner_user_id": "local-user",
        "title": "Da Nang trip",
        "destination_scope": "Da Nang",
        "date_window": None,
        "planning_status": "planning",
        "created_at": MOMENT,
        "updated_at": MOMENT,
    }
    payload.update(overrides)
    return TripWorkspace(**payload)


def _conversation(workspace_id="tw_promo", **overrides):
    payload = {
        "conversation_id": "cv_promo",
        "workspace_id": workspace_id,
        "title": None,
        "created_at": MOMENT,
        "updated_at": MOMENT,
    }
    payload.update(overrides)
    return Conversation(**payload)


def _message(conversation_id="cv_promo", **overrides):
    payload = {
        "message_id": "ms_promo",
        "conversation_id": conversation_id,
        "sequence": 1,
        "role": MessageRole.USER,
        "content": PREFERENCE_TEXT,
        "source": MessageSource.UI,
        "trace_visibility": TraceVisibility.INCLUDED,
        "created_at": MOMENT,
    }
    payload.update(overrides)
    return Message(**payload)


def _candidate(**overrides):
    payload = {
        "candidate_id": generate_memory_candidate_id(),
        "run_id": "mer_promo",
        "workspace_id": "tw_promo",
        "conversation_id": "cv_promo",
        "source_message_id": "ms_promo",
        "source_sequence": 1,
        "proposed_scope": MemoryScope.USER,
        "proposed_type": MemoryType.PREFERENCE,
        "status": MemoryCandidateStatus.ACCEPTED,
        "confidence": 0.8,
        "sensitivity_label": SensitivityLabel.NONE,
        "text": PREFERENCE_TEXT,
        "evidence_summary": "signal=preference:ăn chay",
        "reason": PolicyReason.SUPPORTED_PREFERENCE,
        "created_at": MOMENT,
    }
    payload.update(overrides)
    return MemoryCandidate(**payload)


def _service(workspaces=None, conversations=None, messages=(), candidates=()):
    memory = FakeMemoryRepository()
    memory.candidates.extend(candidates)
    service = MemoryService(
        memory_repository=memory,
        conversation_repository=FakeConversationRepository(
            conversations if conversations is not None else (_conversation(),),
            messages,
        ),
        workspace_repository=FakeWorkspaceRepository(
            workspaces if workspaces is not None else (_workspace(),)
        ),
    )
    return service, memory


def _pipeline_candidate(content, sequence=1, **overrides):
    """An accepted candidate produced by the real R5 extractor and policy.

    `sequence` mirrors the source message sequence, exactly as the service
    maps it: candidate order must track message order for supersession age.
    """
    from backend.memory.models import MemorySourceMessage

    source = MemorySourceMessage(
        message_id="ms_pipe",
        conversation_id="cv_promo",
        workspace_id="tw_promo",
        sequence=sequence,
        role="user",
        source="ui",
        trace_visibility="included",
        content=content,
        created_at=MOMENT,
    )
    (draft,) = RuleBasedMemoryExtractor().extract([source])
    decided = MemoryPolicy().evaluate(draft)
    assert decided.status is MemoryCandidateStatus.ACCEPTED
    payload = {
        "candidate_id": generate_memory_candidate_id(),
        "run_id": "mer_pipe",
        "workspace_id": "tw_promo",
        "conversation_id": "cv_promo",
        "source_message_id": "ms_pipe",
        "source_sequence": sequence,
        "proposed_scope": decided.proposed_scope,
        "proposed_type": decided.proposed_type,
        "status": decided.status,
        "confidence": decided.confidence,
        "sensitivity_label": decided.sensitivity_label,
        "text": decided.text,
        "evidence_summary": decided.evidence_summary,
        "reason": decided.reason,
        "created_at": MOMENT,
    }
    payload.update(overrides)
    return MemoryCandidate(**payload)


def _pipeline_candidates(content, sequence=1, message_id="ms_pipe", **overrides):
    """Every accepted candidate the real R5 extractor produces from one message.

    R5 runs all six draft builders over a single message, so one sentence can
    yield a correction plus the inference it states. `_pipeline_candidate`
    asserts a single draft and cannot express that, which is exactly why the
    same-message supersession case needs its own helper.
    """
    from backend.memory.models import MemorySourceMessage

    created_at = overrides.pop("created_at", MOMENT)
    source = MemorySourceMessage(
        message_id=message_id,
        conversation_id="cv_promo",
        workspace_id="tw_promo",
        sequence=sequence,
        role="user",
        source="ui",
        trace_visibility="included",
        content=content,
        created_at=created_at,
    )
    candidates = []
    for draft in RuleBasedMemoryExtractor().extract([source]):
        decided = MemoryPolicy().evaluate(draft)
        if decided.status is not MemoryCandidateStatus.ACCEPTED:
            continue
        payload = {
            "candidate_id": generate_memory_candidate_id(),
            "run_id": "mer_pipe",
            "workspace_id": "tw_promo",
            "conversation_id": "cv_promo",
            "source_message_id": message_id,
            "source_sequence": sequence,
            "proposed_scope": decided.proposed_scope,
            "proposed_type": decided.proposed_type,
            "status": decided.status,
            "confidence": decided.confidence,
            "sensitivity_label": decided.sensitivity_label,
            "text": decided.text,
            "evidence_summary": decided.evidence_summary,
            "reason": decided.reason,
            "created_at": created_at,
        }
        payload.update(overrides)
        candidates.append(MemoryCandidate(**payload))
    return candidates


# 1. Promotion of the three reasons that have an R5 producer.


def test_promotes_produced_preference_constraint_correction():
    # All three share user scope except the workspace constraint; the
    # user-scope correction therefore suppresses the older user-scope
    # preference while the workspace constraint survives. This is the
    # specified coarse rule, not test noise.
    service, memory = _service(
        messages=(
            _message(message_id="ms_pipe"),
            _message(message_id="ms_two", sequence=2),
            _message(message_id="ms_three", sequence=3),
        ),
        candidates=(
            _pipeline_candidate(PREFERENCE_TEXT),
            _pipeline_candidate(
                CONSTRAINT_TEXT,
                sequence=2,
                source_message_id="ms_two",
                proposed_scope=MemoryScope.WORKSPACE,
            ),
            _pipeline_candidate(
                CORRECTION_TEXT, sequence=3, source_message_id="ms_three"
            ),
        ),
    )
    result = service.promote_workspace("tw_promo", "cv_promo")

    assert result.promoted_count == 3
    assert result.skipped_count == 0
    assert len(result.promoted_memory_ids) == 3
    records = {
        record.memory_type.value: record
        for record in memory.list_records(workspace_id="tw_promo")
    }
    assert set(records) == {"preference", "constraint", "correction"}
    assert records["preference"].status is MemoryRecordStatus.SUPERSEDED
    assert records["constraint"].status is MemoryRecordStatus.ACTIVE
    assert records["correction"].status is MemoryRecordStatus.ACTIVE
    assert records["correction"].supersedes_memory_id == records["preference"].memory_id
    assert all(record.memory_id.startswith("mem_") for record in records.values())


def test_promotion_floor_is_075():
    assert MEMORY_PROMOTION_MIN_CONFIDENCE == 0.75


# 2. Skip reasons for ineligible candidates.


def test_skips_non_accepted_provenance_and_sensitivity():
    from backend.memory.models import MemoryCandidateStatus as Status

    cases = [
        ({"status": Status.REJECTED}, PromotionSkipReason.NOT_ACCEPTED),
        ({"status": Status.NEEDS_USER_ACTION}, PromotionSkipReason.NOT_ACCEPTED),
        ({"status": Status.INVALID}, PromotionSkipReason.NOT_ACCEPTED),
        (
            {"proposed_scope": MemoryScope.NONE},
            PromotionSkipReason.SCOPE_NOT_PROMOTABLE,
        ),
        ({"proposed_type": MemoryType.NONE}, PromotionSkipReason.TYPE_NOT_PROMOTABLE),
        (
            {"proposed_type": MemoryType.SAFETY_NOTE},
            PromotionSkipReason.TYPE_NOT_PROMOTABLE,
        ),
        ({"confidence": 0.5}, PromotionSkipReason.BELOW_MIN_CONFIDENCE),
        (
            {"sensitivity_label": SensitivityLabel.SECRET},
            PromotionSkipReason.SENSITIVITY_NOT_PROMOTABLE,
        ),
        (
            {"sensitivity_label": SensitivityLabel.SENSITIVE},
            PromotionSkipReason.SENSITIVITY_NOT_PROMOTABLE,
        ),
        (
            {"sensitivity_label": SensitivityLabel.UNSAFE},
            PromotionSkipReason.SENSITIVITY_NOT_PROMOTABLE,
        ),
        (
            {"reason": PolicyReason.UNSUPPORTED},
            PromotionSkipReason.REASON_NOT_PROMOTABLE,
        ),
    ]
    for index, (override, reason) in enumerate(cases):
        service, memory = _service(
            messages=tuple(
                _message(message_id=f"ms_{item}", sequence=item + 1)
                for item in range(len(cases))
            ),
            candidates=(_candidate(source_message_id=f"ms_{index}", **override),),
        )
        result = service.promote_workspace("tw_promo", "cv_promo")
        assert result.promoted_count == 0, override
        assert result.skipped_count == 1, override
        counts = dict((item.reason, item.count) for item in result.skip_reasons)
        assert counts.get(reason) == 1, override
    assert memory.records == {}


def test_skips_unresolved_provenance():
    service, memory = _service(
        messages=(),
        candidates=(_candidate(source_message_id="ms_gone"),),
    )
    result = service.promote_workspace("tw_promo", "cv_promo")
    assert result.promoted_count == 0
    assert dict((item.reason, item.count) for item in result.skip_reasons) == {
        PromotionSkipReason.PROVENANCE_UNRESOLVED: 1
    }


def test_duplicate_promotion_skips_second_run():
    candidate = _candidate()
    service, memory = _service(messages=(_message(),), candidates=(candidate,))
    first = service.promote_workspace("tw_promo", "cv_promo")
    assert first.promoted_count == 1
    second = service.promote_workspace("tw_promo", "cv_promo")
    assert second.promoted_count == 0
    assert dict((item.reason, item.count) for item in second.skip_reasons) == {
        PromotionSkipReason.DUPLICATE_ACTIVE_RECORD: 1
    }
    assert len(memory.records) == 1


# 3. No-producer allow-list reasons stay forward-compatible.


def test_no_producer_reasons_promote_from_direct_fixtures():
    profile = _candidate(
        proposed_type=MemoryType.PROFILE_FACT,
        reason=PolicyReason.SUPPORTED_PROFILE_FACT,
    )
    decision = _candidate(
        source_message_id="ms_two",
        proposed_scope=MemoryScope.WORKSPACE,
        proposed_type=MemoryType.DECISION,
        reason=PolicyReason.SUPPORTED_TRIP_DECISION,
        text="Đã chốt đi Bà Nà vào ngày hai.",
        evidence_summary="signal=decision:chốt",
    )
    service, _ = _service(
        messages=(
            _message(),
            _message(
                conversation_id="cv_promo", sequence=2, message_id="ms_two", content="x"
            ),
        ),
        candidates=(profile, decision),
    )
    result = service.promote_workspace("tw_promo", "cv_promo")
    assert result.promoted_count == 2


def test_real_pipeline_yields_neither_no_producer_reason():
    from backend.memory.models import MemorySourceMessage

    policy = MemoryPolicy()
    extractor = RuleBasedMemoryExtractor()
    contents = [
        PREFERENCE_TEXT,
        CONSTRAINT_TEXT,
        CORRECTION_TEXT,
        "Tôi tên là An, sinh năm 1990.",
        "Hôm nay trời đẹp quá.",
        "Có lẽ tôi thích đi biển, nhưng chưa chắc đâu.",
        "Trong chat này thì tôi thích đi biển.",
    ]
    seen = set()
    for content in contents:
        source = MemorySourceMessage(
            message_id="ms_x",
            conversation_id="cv_promo",
            workspace_id="tw_promo",
            sequence=1,
            role="user",
            source="ui",
            trace_visibility="included",
            content=content,
            created_at=MOMENT,
        )
        for draft in extractor.extract([source]):
            decided = policy.evaluate(draft)
            if decided.status is MemoryCandidateStatus.ACCEPTED:
                seen.add(decided.reason)
    assert PolicyReason.SUPPORTED_PROFILE_FACT not in seen
    assert PolicyReason.SUPPORTED_TRIP_DECISION not in seen


# 4. Correction supersession in all three target cases.


def _promote_preference(
    service, memory, text=PREFERENCE_TEXT, message_id="ms_old", sequence=1
):
    from backend.memory.models import MemorySourceMessage

    source = MemorySourceMessage(
        message_id=message_id,
        conversation_id="cv_promo",
        workspace_id="tw_promo",
        sequence=sequence,
        role="user",
        source="ui",
        trace_visibility="included",
        content=text,
        created_at=MOMENT - timedelta(days=1),
    )
    (draft,) = RuleBasedMemoryExtractor().extract([source])
    decided = MemoryPolicy().evaluate(draft)
    candidate = MemoryCandidate(
        candidate_id=generate_memory_candidate_id(),
        run_id="mer_old",
        workspace_id="tw_promo",
        conversation_id="cv_promo",
        source_message_id=message_id,
        source_sequence=sequence,
        proposed_scope=decided.proposed_scope,
        proposed_type=decided.proposed_type,
        status=decided.status,
        confidence=decided.confidence,
        sensitivity_label=decided.sensitivity_label,
        text=decided.text,
        evidence_summary=decided.evidence_summary,
        reason=decided.reason,
        created_at=MOMENT - timedelta(days=1),
    )
    memory.candidates.append(candidate)
    result = service.promote_workspace("tw_promo", "cv_promo")
    assert result.promoted_count == 1
    return result


def test_correction_with_no_targets_promotes_standalone():
    service, memory = _service(
        messages=(
            _message(),
            _message(
                message_id="ms_new",
                sequence=2,
                content=CORRECTION_TEXT,
            ),
        ),
        candidates=(),
    )
    correction = _pipeline_candidate(
        CORRECTION_TEXT, sequence=2, source_message_id="ms_new", created_at=MOMENT
    )
    memory.candidates.append(correction)
    result = service.promote_workspace("tw_promo", "cv_promo")

    assert result.promoted_count == 1
    (record,) = memory.list_records(workspace_id="tw_promo")
    assert record.memory_type.value == "correction"
    assert record.supersedes_memory_id is None


def test_correction_supersedes_single_older_target():
    service, memory = _service(
        messages=(
            _message(message_id="ms_old"),
            _message(message_id="ms_new", sequence=2, content=CORRECTION_TEXT),
        ),
        candidates=(),
    )
    _promote_preference(service, memory)
    (old,) = memory.list_records(workspace_id="tw_promo")
    correction = _pipeline_candidate(
        CORRECTION_TEXT, sequence=2, source_message_id="ms_new", created_at=MOMENT
    )
    memory.candidates.append(correction)
    result = service.promote_workspace("tw_promo", "cv_promo")

    assert result.promoted_count == 1
    assert memory.records[old.memory_id].status is MemoryRecordStatus.SUPERSEDED
    (new,) = [
        record
        for record in memory.list_records(workspace_id="tw_promo")
        if record.memory_type.value == "correction"
    ]
    assert new.supersedes_memory_id == old.memory_id


def test_repromotion_after_supersede_skips_known_record():
    # The superseded record still owns its source candidate id, so a rerun
    # must report a superseded duplicate rather than attempt a reinsert.
    service, memory = _service(
        messages=(
            _message(message_id="ms_old"),
            _message(message_id="ms_new", sequence=2, content=CORRECTION_TEXT),
        ),
        candidates=(),
    )
    _promote_preference(service, memory)
    correction = _pipeline_candidate(
        CORRECTION_TEXT, sequence=2, source_message_id="ms_new", created_at=MOMENT
    )
    memory.candidates.append(correction)
    service.promote_workspace("tw_promo", "cv_promo")

    result = service.promote_workspace("tw_promo", "cv_promo")

    assert result.promoted_count == 0
    assert result.skipped_count == 2
    counts = dict((item.reason, item.count) for item in result.skip_reasons)
    assert counts.get(PromotionSkipReason.DUPLICATE_SUPERSEDED_RECORD) == 1
    assert counts.get(PromotionSkipReason.DUPLICATE_ACTIVE_RECORD) == 1


def test_correction_does_not_suppress_same_message_sibling():
    # One sentence yields a correction and the preference it states. They
    # share the message-time age key exactly, so the tie-suppressing rule
    # would bury the preference the user just expressed unless same-message
    # siblings are excluded from the target set.
    service, memory = _service(
        messages=(_message(message_id="ms_same", content=SIBLING_CORRECTION_TEXT),),
        candidates=tuple(
            _pipeline_candidates(SIBLING_CORRECTION_TEXT, message_id="ms_same")
        ),
    )
    result = service.promote_workspace("tw_promo", "cv_promo")

    records = {
        record.memory_type.value: record
        for record in memory.list_records(workspace_id="tw_promo")
    }
    assert set(records) == {"correction", "preference"}
    assert result.promoted_count == 2
    assert records["preference"].status is MemoryRecordStatus.ACTIVE
    assert records["correction"].status is MemoryRecordStatus.ACTIVE
    assert records["correction"].supersedes_memory_id is None


def test_correction_suppresses_every_ambiguous_target():
    service, memory = _service(
        messages=(
            _message(message_id="ms_old"),
            _message(message_id="ms_b", sequence=2, content="Tôi thích đi biển."),
            _message(message_id="ms_new", sequence=3, content=CORRECTION_TEXT),
        ),
        candidates=(),
    )
    _promote_preference(service, memory)
    _promote_preference(
        service, memory, text="Tôi thích đi biển.", message_id="ms_b", sequence=2
    )
    olds = memory.list_records(
        workspace_id="tw_promo", status=MemoryRecordStatus.ACTIVE
    )
    assert len(olds) == 2
    correction = _pipeline_candidate(
        CORRECTION_TEXT, sequence=3, source_message_id="ms_new", created_at=MOMENT
    )
    memory.candidates.append(correction)
    result = service.promote_workspace("tw_promo", "cv_promo")

    assert result.promoted_count == 1
    assert all(
        memory.records[item.memory_id].status is MemoryRecordStatus.SUPERSEDED
        for item in olds
    )
    counts = dict((item.reason, item.count) for item in result.skip_reasons)
    # A multi-target correction still promotes, so its fan-out is an
    # informational count on the result, never a skip reason, and the skip
    # accounting must reconcile exactly with the skipped count.
    assert PromotionSkipReason.CORRECTION_SUPERSEDES_MULTIPLE not in counts
    assert result.multi_target_correction_count == 1
    assert sum(counts.values()) == result.skipped_count
    (new,) = [
        record
        for record in memory.list_records(workspace_id="tw_promo")
        if record.memory_type.value == "correction"
    ]
    oldest = min(olds, key=lambda item: (item.created_at, item.source_sequence))
    assert new.supersedes_memory_id == oldest.memory_id


def test_older_correction_does_not_suppress_newer_inference():
    service, memory = _service(
        messages=(
            _message(message_id="ms_old", content=CORRECTION_TEXT),
            _message(message_id="ms_new", sequence=2, content=PREFERENCE_TEXT),
        ),
        candidates=(),
    )
    correction = _pipeline_candidate(
        CORRECTION_TEXT, sequence=1, source_message_id="ms_old", created_at=MOMENT
    )
    preference = _pipeline_candidate(
        PREFERENCE_TEXT, sequence=2, source_message_id="ms_new", created_at=MOMENT
    )
    memory.candidates.extend([correction, preference])
    result = service.promote_workspace("tw_promo", "cv_promo")

    assert result.promoted_count == 2
    assert all(
        record.status is MemoryRecordStatus.ACTIVE
        for record in memory.list_records(workspace_id="tw_promo")
    )


def test_correction_never_crosses_scope_boundaries():
    service, memory = _service(
        messages=(
            _message(message_id="ms_old"),
            _message(message_id="ms_new", sequence=2, content=CORRECTION_TEXT),
        ),
        candidates=(),
    )
    _promote_preference(service, memory)
    (user_old,) = memory.list_records(workspace_id="tw_promo")
    # A workspace-scope record must survive a user-scope correction.
    service._memory.create_records([_workspace_scoped_record()])
    correction = _pipeline_candidate(
        CORRECTION_TEXT, sequence=2, source_message_id="ms_new", created_at=MOMENT
    )
    memory.candidates.append(correction)
    result = service.promote_workspace("tw_promo", "cv_promo")
    assert result.promoted_count == 1
    assert memory.records[user_old.memory_id].status is MemoryRecordStatus.SUPERSEDED
    assert memory.records["mem_ws"].status is MemoryRecordStatus.ACTIVE


def _workspace_scoped_record():
    from backend.memory.models import MemoryRecord

    return MemoryRecord(
        memory_id="mem_ws",
        source_candidate_id="mc_ws",
        workspace_id="tw_promo",
        conversation_id="cv_promo",
        source_message_id="ms_ws",
        source_sequence=1,
        owner_user_id="local-user",
        scope=MemoryRecordScope.WORKSPACE,
        scope_id="tw_promo",
        memory_type="constraint",
        status=MemoryRecordStatus.ACTIVE,
        text="Ngân sách tối đa 20 triệu.",
        confidence=0.85,
        sensitivity_label=SensitivityLabel.NONE,
        supersedes_memory_id=None,
        created_at=MOMENT - timedelta(days=1),
        updated_at=MOMENT - timedelta(days=1),
        expires_at=None,
    )


def test_user_correction_supersedes_record_from_another_trip():
    other_workspace = _workspace(workspace_id="tw_other")
    other_conversation = _conversation(
        workspace_id="tw_other", conversation_id="cv_other"
    )
    service, memory = _service(
        workspaces=(_workspace(), other_workspace),
        conversations=(_conversation(), other_conversation),
        messages=(
            _message(message_id="ms_old"),
            _message(
                conversation_id="cv_other",
                message_id="ms_other",
                content=PREFERENCE_TEXT,
            ),
            _message(message_id="ms_new", sequence=2, content=CORRECTION_TEXT),
        ),
        candidates=(),
    )
    _promote_preference(service, memory)
    # Move the promoted preference into the other trip to simulate history.
    (old,) = memory.list_records(workspace_id="tw_promo")
    import dataclasses

    memory.records[old.memory_id] = dataclasses.replace(
        old, workspace_id="tw_other", conversation_id="cv_other"
    )
    correction = _pipeline_candidate(
        CORRECTION_TEXT, sequence=2, source_message_id="ms_new", created_at=MOMENT
    )
    memory.candidates.append(correction)
    result = service.promote_workspace("tw_promo", "cv_promo")
    assert result.promoted_count == 1
    assert memory.records[old.memory_id].status is MemoryRecordStatus.SUPERSEDED


# 5. Service-level provenance and hygiene.


def test_promotion_rejects_unknown_scope_and_blank_ids():
    service, memory = _service()
    with pytest.raises(WorkspaceNotFoundError):
        service.promote_workspace("tw_missing")
    with pytest.raises(ConversationNotFoundError):
        service.promote_workspace("tw_promo", "cv_missing")
    other = _conversation(workspace_id="tw_other", conversation_id="cv_other")
    skewed, _ = _service(conversations=(other,))
    with pytest.raises(MemoryScopeMismatchError):
        skewed.promote_workspace("tw_promo", "cv_other")
    with pytest.raises(MemoryValidationError):
        service.promote_workspace("  ")
    assert memory.promotion_runs == {}


def test_promotion_errors_carry_no_raw_content():
    service, _ = _service(
        workspaces=(_workspace(), _workspace(workspace_id="tw_other")),
        messages=(_message(content="sk-test-ZZZ999"),),
    )
    with pytest.raises(MemoryScopeMismatchError) as excinfo:
        service.promote_workspace("tw_other", "cv_promo")
    assert "sk-test-ZZZ999" not in str(excinfo.value)


def test_promotion_result_counts_are_accurate():
    service, memory = _service(
        messages=(_message(),),
        candidates=(
            _candidate(),
            _candidate(
                candidate_id=generate_memory_candidate_id(),
                source_message_id="ms_two",
                status=MemoryCandidateStatus.REJECTED,
            ),
        ),
    )
    result = service.promote_workspace("tw_promo", "cv_promo")
    assert result.promotion_run_id.startswith("mpr_")
    assert (result.source_candidate_count, result.promoted_count) == (2, 1)
    assert result.skipped_count == 1
    assert len(memory.promotion_runs) == 1
