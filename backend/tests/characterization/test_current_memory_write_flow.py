"""Characterization of the current R5/R6 memory write flow.

Freezes present behavior as executable evidence for the standalone
conversation foundation slice. No production module is modified by these
tests; they document the flow from source message to candidate to record
to chat context as it exists at BASE 5f28341.

Map covered here:
- accepted preference extraction (extractor + policy)
- trace-excluded rejection (policy gate)
- manual promotion (service extraction + promotion)
- broad correction behavior (current scope-wide supersession, as-is)
- separate promotion repository calls (non-atomic, as-is)
- gate-off chat compatibility (unbound turn unchanged)
- bound-turn persistence (user persisted before generation, assistant after)
"""

from datetime import datetime, timedelta, timezone

from backend.conversations.models import (
    Conversation,
    ConversationRetentionState,
    Message,
    MessageRole,
    MessageSource,
    TraceVisibility,
)
from backend.conversations.service import ConversationService
from backend.memory.extraction import RuleBasedMemoryExtractor
from backend.memory.models import (
    MemoryCandidateStatus,
    MemoryRecordStatus,
    MemorySourceMessage,
    PolicyReason,
)
from backend.memory.policy import MemoryPolicy
from backend.memory.service import MemoryService
from backend.orchestration.conversation_orchestrator import ConversationOrchestrator
from backend.workspaces.models import TripWorkspace

MOMENT = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
PREFERENCE_TEXT = "Tôi ăn chay trường, hãy nhớ giúp tôi."
CORRECTION_TEXT = "Thực ra tôi đổi sang đi tàu hỏa, sửa lại giúp tôi."
WORKSPACE_ID = "tw_char"
OWNER_ID = "local-user"


class FakeWorkspaceRepository:
    def __init__(self, workspaces=()):
        self._workspaces = {w.workspace_id: w for w in workspaces}

    def get(self, workspace_id):
        return self._workspaces.get(workspace_id)


class FakeConversationRepository:
    """In-memory conversation store supporting extraction + chat paths."""

    def __init__(self, conversations=(), messages=(), journal=None):
        self._conversations = {c.conversation_id: c for c in conversations}
        self._messages = {m.message_id: m for m in messages}
        self.journal = journal

    def get(self, conversation_id):
        return self._conversations.get(conversation_id)

    def get_message(self, message_id):
        return self._messages.get(message_id)

    def list_messages(self, conversation_id, after_sequence, limit):
        selected = [
            m
            for m in self._messages.values()
            if m.conversation_id == conversation_id
            and (after_sequence is None or m.sequence > after_sequence)
        ]
        selected.sort(key=lambda m: m.sequence)
        return tuple(selected[:limit])

    def list_by_workspace(self, workspace_id, include_deletion=False):
        return tuple(
            c for c in self._conversations.values() if c.workspace_id == workspace_id
        )

    def append_message(self, draft, message_id):
        if self.journal is not None:
            role = getattr(draft.role, "value", draft.role)
            self.journal.append("append:user" if role == "user" else "append:assistant")
        sequence = (
            sum(
                1
                for m in self._messages.values()
                if m.conversation_id == draft.conversation_id
            )
            + 1
        )
        stored = Message(
            message_id=message_id,
            conversation_id=draft.conversation_id,
            sequence=sequence,
            role=draft.role,
            content=draft.content,
            source=draft.source,
            trace_visibility=draft.trace_visibility,
            created_at=draft.created_at,
        )
        self._messages[message_id] = stored
        return stored

    def create(self, conversation):
        self._conversations[conversation.conversation_id] = conversation
        return conversation


class FakeMemoryRepository:
    """In-memory memory store recording promotion call order."""

    def __init__(self):
        self.runs = {}
        self.candidates = []
        self.records = {}
        self.promotion_runs = {}
        self.calls = []

    def create_run(self, run):
        self.runs[run.run_id] = run
        return run

    def create_candidates(self, candidates):
        ordered = tuple(candidates)
        self.candidates.extend(ordered)
        return ordered

    def list_runs(self, workspace_id, conversation_id=None):
        return tuple(
            r
            for r in self.runs.values()
            if r.workspace_id == workspace_id
            and (conversation_id is None or r.conversation_id == conversation_id)
        )

    def list_candidates(self, run_id=None, workspace_id=None, conversation_id=None):
        return tuple(
            c
            for c in self.candidates
            if (run_id is None or c.run_id == run_id)
            and (workspace_id is None or c.workspace_id == workspace_id)
            and (conversation_id is None or c.conversation_id == conversation_id)
        )

    def create_promotion_run(self, run):
        self.calls.append("create_promotion_run")
        self.promotion_runs[run.promotion_run_id] = run
        return run

    def create_records(self, records):
        self.calls.append("create_records")
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
            r
            for r in self.records.values()
            if (workspace_id is None or r.workspace_id == workspace_id)
            and (conversation_id is None or r.conversation_id == conversation_id)
            and (owner_user_id is None or r.owner_user_id == owner_user_id)
            and (scope is None or value(r.scope) == value(scope))
            and (status is None or value(r.status) == value(status))
        )

    def mark_records_superseded(self, memory_ids):
        self.calls.append("mark_records_superseded")
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


class StubRAG:
    def __init__(self, journal=None):
        self.answer_calls = []
        self.journal = journal

    def generate_answer(self, message, top_k=None):
        self.answer_calls.append((message, top_k))
        if self.journal is not None:
            self.journal.append("generate_answer")
        return {"reply": "stub reply", "model": "stub-model", "citations": []}


def _workspace(workspace_id=WORKSPACE_ID):
    return TripWorkspace(
        workspace_id=workspace_id,
        owner_user_id=OWNER_ID,
        title="Characterization trip",
        destination_scope=None,
        date_window=None,
        planning_status="idea",
        created_at=MOMENT,
        updated_at=MOMENT,
    )


def _conversation(conversation_id, workspace_id=WORKSPACE_ID):
    return Conversation(
        conversation_id=conversation_id,
        owner_user_id=OWNER_ID,
        workspace_id=workspace_id,
        title=None,
        created_at=MOMENT,
        updated_at=MOMENT,
        retention_state=ConversationRetentionState.ACTIVE,
    )


def _message(message_id, conversation_id, content, sequence, created_at=MOMENT):
    return Message(
        message_id=message_id,
        conversation_id=conversation_id,
        sequence=sequence,
        role=MessageRole.USER,
        content=content,
        source=MessageSource.UI,
        trace_visibility=TraceVisibility.INCLUDED,
        created_at=created_at,
    )


def _source(content, trace_visibility="included"):
    return MemorySourceMessage(
        message_id="ms_char",
        conversation_id="cv_char",
        workspace_id=WORKSPACE_ID,
        sequence=1,
        role="user",
        source="ui",
        trace_visibility=trace_visibility,
        content=content,
        created_at=MOMENT,
    )


def _service(conversations, messages, memory=None, workspace=None):
    memory = memory if memory is not None else FakeMemoryRepository()
    service = MemoryService(
        memory_repository=memory,
        conversation_repository=FakeConversationRepository(conversations, messages),
        workspace_repository=FakeWorkspaceRepository(
            [workspace if workspace is not None else _workspace()]
        ),
    )
    return service, memory


# 1. Accepted preference extraction characterizes the current accept path.


def test_accepted_preference_extraction_characterizes_current_accept():
    (draft,) = RuleBasedMemoryExtractor().extract([_source(PREFERENCE_TEXT)])
    decided = MemoryPolicy().evaluate(draft)

    assert decided.status is MemoryCandidateStatus.ACCEPTED
    assert decided.reason is PolicyReason.SUPPORTED_PREFERENCE


# 2. Trace-excluded rejection characterizes the current trace gate.


def test_trace_excluded_rejection_characterizes_current_gate():
    (draft,) = RuleBasedMemoryExtractor().extract(
        [_source(PREFERENCE_TEXT, trace_visibility="excluded")]
    )
    decided = MemoryPolicy().evaluate(draft)

    assert decided.status is MemoryCandidateStatus.REJECTED
    assert decided.reason is PolicyReason.TRACE_EXCLUDED


# 3. Manual promotion characterizes the current extract-then-promote path.


def test_manual_promotion_persists_one_active_record():
    service, memory = _service(
        conversations=[_conversation("cv_char")],
        messages=[_message("ms_char", "cv_char", PREFERENCE_TEXT, 1)],
    )

    run = service.run_conversation_extraction(WORKSPACE_ID, "cv_char", "manual")
    assert run.candidate_count >= 1
    assert run.accepted_count >= 1

    result = service.promote_workspace(WORKSPACE_ID, "cv_char")

    assert result.promoted_count == 1
    assert result.skipped_count == 0
    (record,) = memory.list_records(workspace_id=WORKSPACE_ID)
    assert record.status is MemoryRecordStatus.ACTIVE
    assert record.owner_user_id == OWNER_ID


# 4. Broad correction behavior documents current scope-wide supersession as-is.


def test_broad_correction_supersedes_scope_wide_as_is():
    old_at = MOMENT - timedelta(days=1)
    service, memory = _service(
        conversations=[_conversation("cv_one"), _conversation("cv_two")],
        messages=[
            _message("ms_old1", "cv_one", PREFERENCE_TEXT, 1, created_at=old_at),
            _message("ms_old2", "cv_two", PREFERENCE_TEXT, 1, created_at=old_at),
            _message("ms_new", "cv_one", CORRECTION_TEXT, 2, created_at=MOMENT),
        ],
    )

    service.run_conversation_extraction(WORKSPACE_ID, "cv_one", "manual")
    service.run_conversation_extraction(WORKSPACE_ID, "cv_two", "manual")
    result = service.promote_workspace(WORKSPACE_ID)

    # Current behavior: one user-scope correction suppresses every older
    # same-owner user-scope record (scope_id is the owner), not just the
    # record in its own conversation. Frozen here as-is.
    assert result.promoted_count == 3
    records = list(memory.list_records(workspace_id=WORKSPACE_ID))
    corrections = [r for r in records if r.memory_type.value == "correction"]
    preferences = [r for r in records if r.memory_type.value == "preference"]
    assert len(corrections) == 1
    assert len(preferences) == 2
    assert all(r.status is MemoryRecordStatus.SUPERSEDED for r in preferences)
    assert corrections[0].status is MemoryRecordStatus.ACTIVE


# 5. Separate promotion repository calls characterize the non-atomic window as-is.


def test_promotion_uses_separate_repository_calls_non_atomic_as_is():
    old_at = MOMENT - timedelta(days=1)
    service, memory = _service(
        conversations=[_conversation("cv_char")],
        messages=[
            _message("ms_old", "cv_char", PREFERENCE_TEXT, 1, created_at=old_at),
            _message("ms_new", "cv_char", CORRECTION_TEXT, 2, created_at=MOMENT),
        ],
    )
    service.run_conversation_extraction(WORKSPACE_ID, "cv_char", "manual")

    memory.calls.clear()
    service.promote_workspace(WORKSPACE_ID, "cv_char")

    # Current behavior: record insert, supersession flip, and promotion-run
    # insert are three separate repository calls, not one atomic unit of
    # work. Frozen here as-is.
    assert memory.calls == [
        "create_records",
        "mark_records_superseded",
        "create_promotion_run",
    ]


# 6. Gate-off chat compatibility characterizes the unbound R4/R5 path.


def test_gate_off_chat_compatibility_preserves_unbound_behavior():
    rag = StubRAG()
    orchestrator = ConversationOrchestrator(
        rag_service=rag,
        conversation_service_provider=lambda: (_ for _ in ()).throw(
            AssertionError("unbound turn must not resolve conversations")
        ),
        memory_enabled=False,
        memory_provider=lambda: (_ for _ in ()).throw(
            AssertionError("gate-off turn must not resolve memory")
        ),
    )

    outcome = orchestrator.handle_turn("Nên đi Đà Nẵng vào tháng mấy?")

    assert outcome.reply == "stub reply"
    assert outcome.conversation is None
    assert outcome.memory is None
    assert len(rag.answer_calls) == 1
    assert rag.answer_calls[0][1] == 4


# 7. Bound-turn persistence characterizes user-before-generation ordering.


def test_bound_turn_persists_user_and_assistant_messages():
    journal: list = []
    conversations = FakeConversationRepository(
        [
            Conversation(
                conversation_id="cv_bound",
                owner_user_id=OWNER_ID,
                workspace_id=WORKSPACE_ID,
                title=None,
                created_at=MOMENT,
                updated_at=MOMENT,
                retention_state=ConversationRetentionState.ACTIVE,
            )
        ],
        [],
        journal=journal,
    )
    workspaces = FakeWorkspaceRepository([_workspace()])
    conversation_service = ConversationService(conversations, workspaces)
    rag = StubRAG(journal=journal)
    orchestrator = ConversationOrchestrator(
        rag_service=rag,
        conversation_service_provider=lambda: conversation_service,
        memory_enabled=False,
    )

    outcome = orchestrator.handle_turn("Xin chào", conversation_id="cv_bound")

    assert outcome.conversation is not None
    assert outcome.conversation.persisted is True
    assert outcome.conversation.user_message_id is not None
    assert outcome.conversation.assistant_message_id is not None
    stored = conversations.list_messages("cv_bound", None, 10)
    assert [m.sequence for m in stored] == [1, 2]
    assert stored[0].role is MessageRole.USER
    assert stored[1].role is MessageRole.ASSISTANT
    # Ordering proof: the user turn is persisted before generation runs,
    # and the assistant turn is persisted afterwards.
    assert journal == ["append:user", "generate_answer", "append:assistant"]
