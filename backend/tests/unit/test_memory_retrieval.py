"""Unit tests for R6 deterministic memory retrieval.

The retrieval service reads active records through the repository interface
and ranks them with deterministic lexical overlap. Fakes hold records only;
no test needs a real database.

No test here touches a model provider, Chroma, Docker, or the network.
"""

from datetime import datetime, timedelta, timezone

from backend.memory.models import (
    MemoryRecord,
    MemoryRecordScope,
    MemoryRecordStatus,
    MemoryRecordType,
    MemorySelectionReason,
    SensitivityLabel,
    generate_memory_record_id,
)
from backend.memory.retrieval import MEMORY_MAX_SELECTED, MemoryRetrievalService

MOMENT = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)


class FakeRecordRepository:
    def __init__(self, records=()):
        self._records = {item.memory_id: item for item in records}

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
            for record in self._records.values()
            if (workspace_id is None or record.workspace_id == workspace_id)
            and (conversation_id is None or record.conversation_id == conversation_id)
            and (owner_user_id is None or record.owner_user_id == owner_user_id)
            and (scope is None or value(record.scope) == value(scope))
            and (status is None or value(record.status) == value(status))
        )


def _record(**overrides) -> MemoryRecord:
    payload = {
        "memory_id": generate_memory_record_id(),
        "source_candidate_id": "mc_example",
        "workspace_id": "tw_probe",
        "conversation_id": "cv_probe",
        "source_message_id": "ms_example",
        "source_sequence": 1,
        "owner_user_id": "local-user",
        "scope": MemoryRecordScope.USER,
        "scope_id": "local-user",
        "memory_type": MemoryRecordType.PREFERENCE,
        "status": MemoryRecordStatus.ACTIVE,
        "text": "Người dùng ăn chay trường.",
        "confidence": 0.8,
        "sensitivity_label": SensitivityLabel.NONE,
        "supersedes_memory_id": None,
        "created_at": MOMENT,
        "updated_at": MOMENT,
        "expires_at": None,
    }
    payload.update(overrides)
    return MemoryRecord(**payload)


def _select(records, query="ăn chay", **overrides):
    service = MemoryRetrievalService(FakeRecordRepository(records))
    return service.select_memories(
        owner_user_id="local-user",
        workspace_id="tw_probe",
        conversation_id="cv_probe",
        query=query,
        now=NOW,
        **overrides,
    )


# 1. Scope isolation across owner, workspace, and conversation.


def test_user_workspace_and_conversation_scopes_are_selected():
    records = (
        _record(),
        _record(
            memory_id=generate_memory_record_id(),
            source_candidate_id="mc_two",
            scope=MemoryRecordScope.WORKSPACE,
            scope_id="tw_probe",
            memory_type=MemoryRecordType.CONSTRAINT,
            text="Ngân sách tối đa 20 triệu.",
        ),
        _record(
            memory_id=generate_memory_record_id(),
            source_candidate_id="mc_three",
            scope=MemoryRecordScope.CONVERSATION,
            scope_id="cv_probe",
            memory_type=MemoryRecordType.EPISODE,
            text="Hôm nay ở Đà Nẵng.",
        ),
    )
    selected = _select(records, query="ăn chay ngân sách Đà Nẵng")
    assert {item.memory_id for item in selected} == {item.memory_id for item in records}


def test_foreign_scopes_are_never_selected():
    records = (
        _record(owner_user_id="other-user", scope_id="other-user"),
        _record(
            memory_id=generate_memory_record_id(),
            source_candidate_id="mc_two",
            workspace_id="tw_other",
            scope=MemoryRecordScope.WORKSPACE,
            scope_id="tw_other",
        ),
        _record(
            memory_id=generate_memory_record_id(),
            source_candidate_id="mc_three",
            conversation_id="cv_other",
            scope=MemoryRecordScope.CONVERSATION,
            scope_id="cv_other",
        ),
    )
    assert _select(records, query="ăn chay") == ()


# 2. Lifecycle and sensitivity filtering.


def test_inactive_and_expired_records_are_excluded():
    statuses = [
        MemoryRecordStatus.SUPERSEDED,
        MemoryRecordStatus.EXPIRED,
        MemoryRecordStatus.ARCHIVED,
        MemoryRecordStatus.DELETION_REQUESTED,
        MemoryRecordStatus.DELETED,
    ]
    records = tuple(
        _record(
            memory_id=generate_memory_record_id(),
            source_candidate_id=f"mc_{index}",
            status=status,
        )
        for index, status in enumerate(statuses)
    )
    assert _select(records) == ()
    assert _select([_record(expires_at=NOW - timedelta(seconds=1))]) == ()
    assert len(_select([_record(expires_at=NOW + timedelta(days=1))])) == 1


def test_sensitive_secret_and_unsafe_records_are_excluded():
    records = tuple(
        _record(
            memory_id=generate_memory_record_id(),
            source_candidate_id=f"mc_{index}",
            sensitivity_label=label,
        )
        for index, label in enumerate(
            [
                SensitivityLabel.PERSONAL,
                SensitivityLabel.SENSITIVE,
                SensitivityLabel.SECRET,
                SensitivityLabel.UNSAFE,
            ]
        )
    )
    selected = _select(records)
    assert [item.memory_id for item in selected] == [records[0].memory_id]


# 3. Deterministic lexical ranking and correction priority.


def test_lexical_ranking_prefers_stronger_overlap():
    weak = _record(text="Tôi ăn phở mỗi sáng.")
    strong = _record(
        memory_id=generate_memory_record_id(),
        source_candidate_id="mc_two",
        text="Tôi ăn chay trường mỗi ngày.",
    )
    (first, second) = _select([weak, strong], query="ăn chay trường")
    assert first.memory_id == strong.memory_id
    assert first.reason is MemorySelectionReason.LEXICAL_MATCH
    assert first.score == 1.0
    assert second.score < first.score


def test_active_correction_is_selected_without_overlap():
    correction = _record(
        memory_type=MemoryRecordType.CORRECTION,
        text="Đổi sang đi tàu hỏa.",
    )
    (selected,) = _select([correction], query="khách sạn ở Hội An")
    assert selected.reason is MemorySelectionReason.ACTIVE_CORRECTION


def test_zero_overlap_selects_nothing_without_correction():
    assert _select([_record()], query="khách sạn ở Hội An") == ()


def test_max_selected_caps_deterministic_order():
    records = tuple(
        _record(
            memory_id=f"mem_{index:04d}",
            source_candidate_id=f"mc_{index}",
            text="Tôi ăn chay.",
        )
        for index in range(7)
    )
    selected = _select(records, max_selected=2)
    assert [item.memory_id for item in selected] == ["mem_0000", "mem_0001"]
    assert MEMORY_MAX_SELECTED == 5
    assert len(_select(records)) == 5


def test_empty_query_selects_only_corrections():
    correction = _record(
        memory_type=MemoryRecordType.CORRECTION,
        text="Đổi sang đi tàu hỏa.",
    )
    assert _select([_record()], query="  ") == ()
    assert len(_select([correction, _record()], query="  ")) == 1
