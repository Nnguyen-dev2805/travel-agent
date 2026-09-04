"""Unit tests for the R5 memory service.

The service owns provenance checks, extraction orchestration, run-count
accuracy, and controlled errors. Repository collaborators are in-memory
fakes; the extractor and policy are the real deterministic implementations
unless a test needs a failing extractor.

No test here touches a real database, a model provider, Chroma, or the
network. No test asserts on message or candidate content inside an error.
"""

from datetime import datetime, timezone

import pytest

from backend.conversations.models import (
    Conversation,
    ConversationRetentionState,
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
from backend.memory.models import (
    MemoryCandidateStatus,
    MemoryExtractionTrigger,
    MemoryRunStatus,
    MemoryValidationError,
    PolicyReason,
)
from backend.memory.repository import MemoryAlreadyExistsError
from backend.memory.service import (
    MemoryRunNotFoundError,
    MemoryScopeMismatchError,
    MemoryService,
    MemoryServiceError,
)
from backend.workspaces.models import TripWorkspace, generate_workspace_id

MOMENT = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
SECRET_TEXT = "API key của tôi là sk-test-ZZZ999, đừng quên nhé."


class FakeWorkspaceRepository:
    def __init__(self, workspaces=()):
        self._workspaces = {item.workspace_id: item for item in workspaces}

    def get(self, workspace_id):
        return self._workspaces.get(workspace_id)

    def list_by_owner(self, owner_user_id):
        raise AssertionError("out of scope for memory service tests")


class FakeConversationRepository:
    def __init__(self, conversations=(), messages=()):
        self._conversations = {item.conversation_id: item for item in conversations}
        self._messages = {}
        for message in messages:
            self._messages.setdefault(message.conversation_id, []).append(message)

    def get(self, conversation_id):
        return self._conversations.get(conversation_id)

    def list_by_workspace(self, workspace_id):
        raise AssertionError("out of scope for memory service tests")

    def append_message(self, message, message_id):
        raise AssertionError("memory service never appends messages")

    def get_message(self, message_id):
        raise AssertionError("out of scope for memory service tests")

    def list_messages(self, conversation_id, after_sequence, limit):
        stored = self._messages.get(conversation_id, [])
        visible = [
            item
            for item in stored
            if after_sequence is None or item.sequence > after_sequence
        ]
        return tuple(visible[:limit])


class FakeMemoryRepository:
    def __init__(self):
        self.runs = {}
        self.candidates = []

    def create_run(self, run):
        if run.run_id in self.runs:
            raise MemoryAlreadyExistsError("duplicate run")
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
            candidate
            for candidate in self.candidates
            if (run_id is None or candidate.run_id == run_id)
            and (workspace_id is None or candidate.workspace_id == workspace_id)
            and (
                conversation_id is None or candidate.conversation_id == conversation_id
            )
        )


class _BoomExtractor:
    extractor_id = "boom-v0"

    def extract(self, messages):
        raise RuntimeError("boom")


def _workspace(**overrides):
    payload = {
        "workspace_id": "tw_service",
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


def _conversation(workspace_id="tw_service", **overrides):
    payload = {
        "conversation_id": "cv_service",
        "workspace_id": workspace_id,
        "title": None,
        "created_at": MOMENT,
        "updated_at": MOMENT,
    }
    payload.update(overrides)
    return Conversation(**payload)


def _message(
    conversation_id="cv_service", sequence=1, content="Tôi ăn chay trường.", **overrides
):
    payload = {
        "message_id": generate_message_id(),
        "conversation_id": conversation_id,
        "sequence": sequence,
        "role": MessageRole.USER,
        "content": content,
        "source": MessageSource.UI,
        "trace_visibility": TraceVisibility.INCLUDED,
        "created_at": MOMENT,
    }
    payload.update(overrides)
    return Message(**payload)


def _service(workspaces=None, conversations=None, messages=(), **overrides):
    if workspaces is None:
        workspaces = (_workspace(),)
    if conversations is None:
        conversations = (_conversation(),)
    memory = FakeMemoryRepository()
    service = MemoryService(
        memory_repository=memory,
        conversation_repository=FakeConversationRepository(conversations, messages),
        workspace_repository=FakeWorkspaceRepository(workspaces),
        **overrides,
    )
    return service, memory


# 1. Happy-path extraction persists shadow evidence with accurate counts.


def test_run_extraction_persists_accepted_preference():
    service, memory = _service(messages=(_message(),))
    run = service.run_conversation_extraction("tw_service", "cv_service", "manual")

    assert run.status is MemoryRunStatus.COMPLETED
    assert run.trigger.value == "manual"
    assert (run.candidate_count, run.accepted_count) == (1, 1)
    assert (run.rejected_count, run.needs_user_action_count, run.invalid_count) == (
        0,
        0,
        0,
    )
    (candidate,) = memory.candidates
    assert candidate.run_id == run.run_id
    assert candidate.workspace_id == "tw_service"
    assert candidate.conversation_id == "cv_service"
    assert candidate.source_message_id.startswith("ms_")
    assert candidate.source_sequence == 1
    assert candidate.status is MemoryCandidateStatus.ACCEPTED
    assert candidate.reason is PolicyReason.SUPPORTED_PREFERENCE


def test_run_counts_mix_accepted_and_rejected():
    service, memory = _service(
        messages=(
            _message(sequence=1, content="Tôi ăn chay trường."),
            _message(sequence=2, content=SECRET_TEXT),
            _message(sequence=3, content="Hôm nay trời đẹp quá."),
        )
    )
    run = service.run_conversation_extraction("tw_service", "cv_service", "manual")

    assert run.status is MemoryRunStatus.COMPLETED_WITH_REJECTIONS
    assert run.candidate_count == 3
    assert run.accepted_count == 1
    assert run.rejected_count == 2
    assert run.invalid_count == 0
    assert len(memory.candidates) == 3


def test_excluded_trace_messages_become_rejected_candidates():
    service, memory = _service(
        messages=(
            _message(
                content="Tôi thích đi biển.", trace_visibility=TraceVisibility.EXCLUDED
            ),
        )
    )
    run = service.run_conversation_extraction("tw_service", "cv_service", "manual")

    assert run.status is MemoryRunStatus.COMPLETED_WITH_REJECTIONS
    assert (run.candidate_count, run.rejected_count) == (1, 1)
    (candidate,) = memory.candidates
    assert candidate.reason is PolicyReason.TRACE_EXCLUDED


def test_no_messages_completes_with_zero_counts():
    service, memory = _service(messages=())
    run = service.run_conversation_extraction("tw_service", "cv_service", "manual")

    assert run.status is MemoryRunStatus.COMPLETED
    assert run.candidate_count == 0
    assert memory.candidates == []


def test_assistant_messages_are_system_generated():
    service, memory = _service(
        messages=(
            _message(
                role=MessageRole.ASSISTANT,
                source=MessageSource.MODEL,
                content="Tôi sẽ nhớ bạn ăn chay.",
            ),
        )
    )
    run = service.run_conversation_extraction("tw_service", "cv_service", "manual")

    assert run.rejected_count == 1
    (candidate,) = memory.candidates
    assert candidate.reason is PolicyReason.SYSTEM_GENERATED


# 2. Provenance failures close without writing candidates.


def test_missing_workspace_writes_nothing():
    service, memory = _service(workspaces=())
    with pytest.raises(WorkspaceNotFoundError):
        service.run_conversation_extraction("tw_missing", "cv_service", "manual")
    assert memory.runs == {}
    assert memory.candidates == []


def test_missing_conversation_writes_nothing():
    service, memory = _service(conversations=())
    with pytest.raises(ConversationNotFoundError):
        service.run_conversation_extraction("tw_service", "cv_missing", "manual")
    assert memory.runs == {}


def test_workspace_conversation_mismatch_writes_nothing():
    other = _conversation(workspace_id="tw_other", conversation_id="cv_other")
    service, memory = _service(conversations=(other,))
    with pytest.raises(MemoryScopeMismatchError):
        service.run_conversation_extraction("tw_service", "cv_other", "manual")
    assert memory.runs == {}


def test_blank_identifiers_are_rejected():
    service, _ = _service()
    with pytest.raises(MemoryValidationError):
        service.run_conversation_extraction("  ", "cv_service", "manual")
    with pytest.raises(MemoryValidationError):
        service.run_conversation_extraction("tw_service", "", "manual")


def test_invalid_trigger_is_rejected():
    service, memory = _service()
    with pytest.raises(MemoryValidationError):
        service.run_conversation_extraction("tw_service", "cv_service", "automatic")
    assert memory.runs == {}


def test_non_active_conversation_is_rejected():
    archived = _conversation()
    object.__setattr__(archived, "retention_state", ConversationRetentionState.ARCHIVED)
    service, memory = _service(conversations=(archived,))
    with pytest.raises(MemoryValidationError):
        service.run_conversation_extraction("tw_service", "cv_service", "manual")
    assert memory.runs == {}


def test_extraction_failure_persists_a_failed_run():
    service, memory = _service(messages=(_message(),), extractor=_BoomExtractor())
    with pytest.raises(MemoryServiceError):
        service.run_conversation_extraction("tw_service", "cv_service", "manual")
    (run,) = memory.runs.values()
    assert run.status is MemoryRunStatus.FAILED
    assert run.candidate_count == 0
    assert run.failure_reason == "extraction_failed"
    assert memory.candidates == []


def test_controlled_errors_carry_no_raw_content():
    service, _ = _service(
        workspaces=(_workspace(), _workspace(workspace_id="tw_other")),
        messages=(_message(content=SECRET_TEXT),),
    )
    with pytest.raises(MemoryScopeMismatchError) as excinfo:
        service.run_conversation_extraction("tw_other", "cv_service", "manual")
    assert "sk-test-ZZZ999" not in str(excinfo.value)

    failing, _ = _service(
        messages=(_message(content=SECRET_TEXT),), extractor=_BoomExtractor()
    )
    with pytest.raises(MemoryServiceError) as excinfo:
        failing.run_conversation_extraction("tw_service", "cv_service", "manual")
    assert "sk-test-ZZZ999" not in str(excinfo.value)
    assert "boom" not in str(excinfo.value)


# 3. Listing enforces the same provenance boundary.


def test_list_runs_returns_workspace_scoped_runs():
    empty = _conversation(conversation_id="cv_empty")
    service, _ = _service(
        conversations=(_conversation(), empty), messages=(_message(),)
    )
    run = service.run_conversation_extraction("tw_service", "cv_service", "manual")
    assert service.list_runs("tw_service") == (run,)
    assert service.list_runs("tw_service", "cv_service") == (run,)
    assert service.list_runs("tw_service", "cv_empty") == ()
    with pytest.raises(ConversationNotFoundError):
        service.list_runs("tw_service", "cv_missing")


def test_list_runs_rejects_unknown_workspace_and_mismatch():
    service, _ = _service()
    with pytest.raises(WorkspaceNotFoundError):
        service.list_runs("tw_missing")
    other = _conversation(workspace_id="tw_other", conversation_id="cv_other")
    skewed, _ = _service(conversations=(other,))
    with pytest.raises(MemoryScopeMismatchError):
        skewed.list_runs("tw_service", "cv_other")


def test_list_candidates_resolves_run_scope():
    service, _ = _service(
        workspaces=(_workspace(), _workspace(workspace_id="tw_other")),
        messages=(_message(),),
    )
    run = service.run_conversation_extraction("tw_service", "cv_service", "manual")
    (candidate,) = service.list_candidates("tw_service", "cv_service", run.run_id)
    assert candidate.candidate_id.startswith("mc_")
    with pytest.raises(MemoryRunNotFoundError):
        service.list_candidates("tw_service", "cv_service", "mer_missing")
    with pytest.raises(MemoryScopeMismatchError):
        service.list_candidates("tw_other", None, run.run_id)


def test_list_candidates_without_run_id_returns_workspace_evidence():
    service, _ = _service(messages=(_message(),))
    service.run_conversation_extraction("tw_service", "cv_service", "manual")
    assert len(service.list_candidates("tw_service")) == 1


def test_evaluation_trigger_is_recorded():
    service, _ = _service(messages=(_message(),))
    run = service.run_conversation_extraction(
        "tw_service", "cv_service", MemoryExtractionTrigger.EVALUATION
    )
    assert run.trigger is MemoryExtractionTrigger.EVALUATION
