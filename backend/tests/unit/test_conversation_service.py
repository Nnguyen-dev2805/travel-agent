"""Unit tests for the conversation service use cases.

The service owns validation, identity generation, timestamps, and existence
checks. It is exercised here against in-memory fakes only, so it is reviewable
without FastAPI, SQLite, a model provider, Chroma, or the network.
"""

import ast
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.conversations.models import (
    Conversation,
    ConversationCreate,
    ConversationRetentionState,
    ConversationValidationError,
    Message,
    MessageDraft,
    MessageHistoryQuery,
    MessageRole,
    MessageSource,
    TraceVisibility,
)
from backend.conversations.repository import (
    ConversationAlreadyExistsError,
    ConversationStorageError,
    MessageAlreadyExistsError,
    MessageSequenceConflictError,
)
from backend.conversations.service import (
    ConversationNotFoundError,
    ConversationService,
    WorkspaceNotFoundError,
)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
EXISTING_WORKSPACE = "tw_existing"
MISSING_WORKSPACE = "tw_missing"


class FakeWorkspaceRepository:
    """Minimal `WorkspaceRepository` stand-in that only answers existence."""

    def __init__(self, existing: tuple[str, ...] = (EXISTING_WORKSPACE,)) -> None:
        self._existing = set(existing)
        self.calls: list[tuple[str, str]] = []

    def get(self, workspace_id: str):
        self.calls.append(("get", workspace_id))
        if workspace_id not in self._existing:
            return None
        return SimpleNamespace(workspace_id=workspace_id)

    def create(self, workspace):  # pragma: no cover - must never be reached
        raise AssertionError("the conversation service must not create workspaces")

    def list_by_owner(self, owner_user_id):  # pragma: no cover - never reached
        raise AssertionError("the conversation service must not list workspaces")


class FakeConversationRepository:
    """In-memory conversation repository that records the calls it receives."""

    def __init__(self) -> None:
        self.conversations: dict[str, Conversation] = {}
        self.messages: list[Message] = []
        self.calls: list[tuple] = []
        self.list_order: tuple[Conversation, ...] | None = None
        self.remaining_identity_conflicts = 0
        self.remaining_message_identity_conflicts = 0
        self.remaining_sequence_conflicts = 0

    @property
    def writes(self) -> list[tuple]:
        return [call for call in self.calls if call[0] in {"create", "append_message"}]

    def create(self, conversation: Conversation) -> Conversation:
        self.calls.append(("create", conversation.conversation_id))
        if self.remaining_identity_conflicts > 0:
            self.remaining_identity_conflicts -= 1
            raise ConversationAlreadyExistsError("identity already used")
        self.conversations[conversation.conversation_id] = conversation
        return conversation

    def get(self, conversation_id: str) -> Conversation | None:
        self.calls.append(("get", conversation_id))
        return self.conversations.get(conversation_id)

    def list_by_workspace(self, workspace_id: str) -> tuple[Conversation, ...]:
        self.calls.append(("list_by_workspace", workspace_id))
        if self.list_order is not None:
            return self.list_order
        return tuple(
            record
            for record in self.conversations.values()
            if record.workspace_id == workspace_id
        )

    def get_message(self, message_id: str) -> Message | None:
        self.calls.append(("get_message", message_id))
        for stored in self.messages:
            if stored.message_id == message_id:
                return stored
        return None

    def append_message(self, message: MessageDraft, message_id: str) -> Message:
        self.calls.append(("append_message", message.conversation_id, message_id))
        if self.remaining_message_identity_conflicts > 0:
            self.remaining_message_identity_conflicts -= 1
            raise MessageAlreadyExistsError("message identity already used")
        if self.remaining_sequence_conflicts > 0:
            self.remaining_sequence_conflicts -= 1
            raise MessageSequenceConflictError("turn position already taken")
        sequence = (
            sum(
                1
                for stored in self.messages
                if stored.conversation_id == message.conversation_id
            )
            + 1
        )
        stored = Message(
            message_id=message_id,
            conversation_id=message.conversation_id,
            sequence=sequence,
            role=message.role,
            content=message.content,
            source=message.source,
            trace_visibility=message.trace_visibility,
            created_at=message.created_at,
        )
        self.messages.append(stored)
        return stored

    def list_messages(
        self, conversation_id: str, after_sequence: int | None, limit: int
    ) -> tuple[Message, ...]:
        self.calls.append(("list_messages", conversation_id, after_sequence, limit))
        selected = [
            stored
            for stored in self.messages
            if stored.conversation_id == conversation_id
            and (after_sequence is None or stored.sequence > after_sequence)
        ]
        selected.sort(key=lambda stored: stored.sequence)
        return tuple(selected[:limit])


@pytest.fixture
def workspaces() -> FakeWorkspaceRepository:
    return FakeWorkspaceRepository()


@pytest.fixture
def repository() -> FakeConversationRepository:
    return FakeConversationRepository()


@pytest.fixture
def service(
    repository: FakeConversationRepository, workspaces: FakeWorkspaceRepository
) -> ConversationService:
    return ConversationService(
        conversation_repository=repository, workspace_repository=workspaces
    )


def _seeded_conversation(
    service: ConversationService, title: str | None = "Da Nang food plan"
) -> Conversation:
    return service.create_conversation(
        ConversationCreate(workspace_id=EXISTING_WORKSPACE, title=title)
    )


# 1. A missing parent workspace stops creation before any write.


def test_create_under_a_missing_workspace_raises_and_writes_nothing(
    service, repository, workspaces
):
    with pytest.raises(WorkspaceNotFoundError):
        service.create_conversation(ConversationCreate(workspace_id=MISSING_WORKSPACE))

    assert repository.writes == []
    assert workspaces.calls == [("get", MISSING_WORKSPACE)]


# 2. Creation returns the repository record with governed identity and defaults.


def test_create_returns_the_repository_record_with_governed_defaults(service):
    conversation = _seeded_conversation(service)

    assert conversation.conversation_id.startswith("cv_")
    assert conversation.workspace_id == EXISTING_WORKSPACE
    assert conversation.title == "Da Nang food plan"
    assert conversation.retention_state is ConversationRetentionState.ACTIVE
    assert conversation.created_at == conversation.updated_at
    assert conversation.created_at.utcoffset().total_seconds() == 0


def test_create_persists_through_the_repository(service, repository):
    conversation = _seeded_conversation(service)
    assert repository.conversations[conversation.conversation_id] == conversation


# 3. Invalid input never reaches storage.


def test_an_invalid_title_writes_nothing(repository, service):
    with pytest.raises(ConversationValidationError):
        ConversationCreate(workspace_id=EXISTING_WORKSPACE, title="t" * 121)

    assert repository.writes == []


def test_create_rejects_a_non_contract_input_without_writing(service, repository):
    with pytest.raises(ConversationValidationError):
        service.create_conversation({"workspace_id": EXISTING_WORKSPACE})

    assert repository.writes == []


# 4 and 5. Listing verifies the workspace and preserves repository order.


def test_list_for_a_missing_workspace_raises_before_any_list_call(
    service, repository, workspaces
):
    with pytest.raises(WorkspaceNotFoundError):
        service.list_conversations(MISSING_WORKSPACE)

    assert [call for call in repository.calls if call[0] == "list_by_workspace"] == []
    assert workspaces.calls == [("get", MISSING_WORKSPACE)]


def test_list_returns_repository_order_without_resorting(service, repository):
    first = _seeded_conversation(service, title="First")
    second = _seeded_conversation(service, title="Second")
    repository.list_order = (second, first)

    listed = service.list_conversations(EXISTING_WORKSPACE)

    assert listed == (second, first)
    assert isinstance(listed, tuple)


def test_list_returns_an_empty_tuple_for_a_workspace_with_no_conversations(service):
    assert service.list_conversations(EXISTING_WORKSPACE) == ()


# 6. Reading one conversation reports absence rather than raising.


def test_get_returns_none_for_a_missing_conversation(service):
    assert service.get_conversation("cv_absent") is None


def test_get_returns_the_stored_conversation(service):
    conversation = _seeded_conversation(service)
    assert service.get_conversation(conversation.conversation_id) == conversation


def test_get_rejects_a_blank_identifier(service):
    with pytest.raises(ConversationValidationError):
        service.get_conversation("   ")


# 7 and 8. Appending validates existence and content before any write.


def test_append_to_a_missing_conversation_raises_and_writes_nothing(
    service, repository
):
    with pytest.raises(ConversationNotFoundError):
        service.append_message(
            conversation_id="cv_absent", role=MessageRole.USER, content="xin chào"
        )

    assert repository.writes == []


@pytest.mark.parametrize("content", ["", "   ", None])
def test_append_with_invalid_content_writes_nothing(service, repository, content):
    conversation = _seeded_conversation(service)
    writes_before = len(repository.writes)

    with pytest.raises(ConversationValidationError):
        service.append_message(
            conversation_id=conversation.conversation_id,
            role=MessageRole.USER,
            content=content,
        )

    assert len(repository.writes) == writes_before


def test_append_with_a_restricted_role_is_accepted_at_the_service_layer(service):
    """The public role restriction belongs to the route, not the service.

    The orchestrator writes `assistant` turns through this same service, so the
    service must not refuse the role that the public route rejects.
    """
    conversation = _seeded_conversation(service)

    stored = service.append_message(
        conversation_id=conversation.conversation_id,
        role=MessageRole.ASSISTANT,
        content="Tháng 3 tới tháng 8 là đẹp nhất.",
        source=MessageSource.MODEL,
    )

    assert stored.role is MessageRole.ASSISTANT
    assert stored.source is MessageSource.MODEL


# 9. The service owns time; the repository owns position.


def test_append_sets_created_at_and_leaves_sequence_to_the_repository(service):
    conversation = _seeded_conversation(service)
    before = datetime.now(timezone.utc)

    stored = service.append_message(
        conversation_id=conversation.conversation_id,
        role=MessageRole.USER,
        content="xin chào",
    )

    after = datetime.now(timezone.utc)
    assert before <= stored.created_at <= after
    assert stored.created_at.utcoffset().total_seconds() == 0
    assert stored.sequence == 1
    assert stored.message_id.startswith("ms_")
    assert stored.source is MessageSource.UI
    assert stored.trace_visibility is TraceVisibility.EXCLUDED


def test_append_increments_the_repository_assigned_sequence(service):
    conversation = _seeded_conversation(service)

    first = service.append_message(
        conversation_id=conversation.conversation_id,
        role=MessageRole.USER,
        content="một",
    )
    second = service.append_message(
        conversation_id=conversation.conversation_id,
        role=MessageRole.USER,
        content="hai",
    )

    assert (first.sequence, second.sequence) == (1, 2)


# 10 and 11. A generated identity collision is retried exactly once.


def test_duplicate_conversation_identity_is_retried_once_with_a_fresh_identity(
    service, repository
):
    repository.remaining_identity_conflicts = 1

    conversation = _seeded_conversation(service)

    attempted = [call[1] for call in repository.calls if call[0] == "create"]
    assert len(attempted) == 2, "exactly one retry"
    assert attempted[0] != attempted[1], "the retry must use a fresh identity"
    assert conversation.conversation_id == attempted[1]


def test_second_conversation_identity_collision_fails_closed(service, repository):
    repository.remaining_identity_conflicts = 2

    with pytest.raises(ConversationStorageError):
        _seeded_conversation(service)

    assert len([call for call in repository.calls if call[0] == "create"]) == 2
    assert repository.conversations == {}


def test_duplicate_message_identity_is_retried_once_with_a_fresh_identity(
    service, repository
):
    conversation = _seeded_conversation(service)
    repository.remaining_message_identity_conflicts = 1

    stored = service.append_message(
        conversation_id=conversation.conversation_id,
        role=MessageRole.USER,
        content="xin chào",
    )

    attempted = [call[2] for call in repository.calls if call[0] == "append_message"]
    assert len(attempted) == 2
    assert attempted[0] != attempted[1]
    assert stored.message_id == attempted[1]


def test_second_message_identity_collision_fails_closed(service, repository):
    conversation = _seeded_conversation(service)
    repository.remaining_message_identity_conflicts = 2

    with pytest.raises(ConversationStorageError):
        service.append_message(
            conversation_id=conversation.conversation_id,
            role=MessageRole.USER,
            content="xin chào",
        )

    assert len([call for call in repository.calls if call[0] == "append_message"]) == 2
    assert repository.messages == []


def test_sequence_collision_is_retried_once_then_succeeds(service, repository):
    """A contested turn position must be retried, not surfaced immediately.

    The adapter re-reads `MAX(sequence)` on every attempt, so one retry is enough
    to re-allocate a position that another writer took between the read and the
    insert.
    """
    conversation = _seeded_conversation(service)
    repository.remaining_sequence_conflicts = 1

    stored = service.append_message(
        conversation_id=conversation.conversation_id,
        role=MessageRole.USER,
        content="xin chào",
    )

    attempts = [call for call in repository.calls if call[0] == "append_message"]
    assert len(attempts) == 2, "exactly one retry"
    assert stored.sequence == 1
    assert len(repository.messages) == 1


def test_second_sequence_collision_fails_closed_without_partial_write(
    service, repository
):
    conversation = _seeded_conversation(service)
    repository.remaining_sequence_conflicts = 2

    with pytest.raises(ConversationStorageError):
        service.append_message(
            conversation_id=conversation.conversation_id,
            role=MessageRole.USER,
            content="xin chào",
        )

    assert len([call for call in repository.calls if call[0] == "append_message"]) == 2
    assert repository.messages == []


def test_sequence_conflict_does_not_escape_as_a_repository_error(service, repository):
    """The route must never map a retried position conflict to a raw conflict.

    A caller that hits a single position conflict gets a stored turn, so
    `MessageSequenceConflictError` must not reach the route layer at all.
    """
    conversation = _seeded_conversation(service)
    repository.remaining_sequence_conflicts = 1

    stored = service.append_message(
        conversation_id=conversation.conversation_id,
        role=MessageRole.USER,
        content="xin chào",
    )

    assert stored.message_id.startswith("ms_")


# 12 and 13. History verifies existence and delegates resolved paging.


def test_list_messages_for_a_missing_conversation_raises(service):
    with pytest.raises(ConversationNotFoundError):
        service.list_messages(MessageHistoryQuery(conversation_id="cv_absent"))


def test_list_messages_passes_the_resolved_cursor_and_limit_through(
    service, repository
):
    conversation = _seeded_conversation(service)
    first = service.append_message(
        conversation_id=conversation.conversation_id,
        role=MessageRole.USER,
        content="một",
    )
    service.append_message(
        conversation_id=conversation.conversation_id,
        role=MessageRole.USER,
        content="hai",
    )

    page = service.list_messages(
        MessageHistoryQuery(
            conversation_id=conversation.conversation_id,
            after_message_id=first.message_id,
            limit=10,
        )
    )

    delegated = [call for call in repository.calls if call[0] == "list_messages"][-1]
    assert delegated == ("list_messages", conversation.conversation_id, 1, 10)
    assert [message.content for message in page] == ["hai"]


def test_list_messages_without_a_cursor_delegates_none(service, repository):
    conversation = _seeded_conversation(service)

    service.list_messages(
        MessageHistoryQuery(conversation_id=conversation.conversation_id)
    )

    delegated = [call for call in repository.calls if call[0] == "list_messages"][-1]
    assert delegated == ("list_messages", conversation.conversation_id, None, 50)


def test_list_messages_rejects_a_cursor_from_another_conversation(service, repository):
    first = _seeded_conversation(service, title="First")
    second = _seeded_conversation(service, title="Second")
    foreign = service.append_message(
        conversation_id=second.conversation_id,
        role=MessageRole.USER,
        content="thuộc hội thoại khác",
    )
    calls_before = len(
        [call for call in repository.calls if call[0] == "list_messages"]
    )

    with pytest.raises(ConversationValidationError):
        service.list_messages(
            MessageHistoryQuery(
                conversation_id=first.conversation_id,
                after_message_id=foreign.message_id,
            )
        )

    assert (
        len([call for call in repository.calls if call[0] == "list_messages"])
        == calls_before
    ), "an invalid cursor must be rejected before any page is read"


def test_list_messages_rejects_an_unknown_cursor(service):
    conversation = _seeded_conversation(service)

    with pytest.raises(ConversationValidationError):
        service.list_messages(
            MessageHistoryQuery(
                conversation_id=conversation.conversation_id,
                after_message_id="ms_never_stored",
            )
        )


def test_list_messages_requires_a_history_query_contract(service):
    with pytest.raises(ConversationValidationError):
        service.list_messages({"conversation_id": "cv_example"})


# 14. The service's dependency boundary, asserted against the import graph.

FORBIDDEN_RUNTIME_MODULES = (
    "fastapi",
    "pydantic",
    "sqlite3",
    "chromadb",
    "openai",
    "backend.rag",
    "backend.app",
    "backend.storage",
)


def test_service_module_declares_no_forbidden_direct_import():
    """Read the module's import statements from its AST, not its raw text."""
    source_path = ROOT_DIR / "backend" / "conversations" / "service.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    runtime_imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            # `if TYPE_CHECKING:` blocks never execute at runtime.
            continue
        if isinstance(node, ast.Import):
            runtime_imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            runtime_imports.add(node.module)

    offending = {
        name
        for name in runtime_imports
        for forbidden in FORBIDDEN_RUNTIME_MODULES
        if name == forbidden or name.startswith(f"{forbidden}.")
    }
    assert offending == set(), f"service.py imports a forbidden dependency: {offending}"


def test_importing_the_service_loads_no_forbidden_module():
    """Import the service in a clean interpreter and inspect the real graph."""
    code = (
        "import json, sys;"
        "import backend.conversations.service;"
        "print(json.dumps(sorted(sys.modules)))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=ROOT_DIR,
        check=True,
    )
    loaded = set(json.loads(result.stdout))

    offending = {
        name
        for name in loaded
        for forbidden in FORBIDDEN_RUNTIME_MODULES
        if name == forbidden or name.startswith(f"{forbidden}.")
    }
    assert offending == set(), (
        f"importing the conversation service loaded forbidden modules: {offending}"
    )
