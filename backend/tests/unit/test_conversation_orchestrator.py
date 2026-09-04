"""Unit tests for the conversation orchestrator.

The orchestrator owns turn ordering and the partial-failure policy for one chat
turn. It is exercised here against fakes that record call order, so ordering is
asserted as a sequence of observed calls rather than through mock call counts.

No test constructs FastAPI, SQLite, Chroma, a model provider, or the network.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.conversations.models import (
    Message,
    MessageRole,
    MessageSource,
    TraceVisibility,
    generate_message_id,
    utc_now,
)
from backend.conversations.repository import ConversationStorageError
from backend.conversations.service import ConversationNotFoundError
from backend.orchestration.conversation_orchestrator import (
    ConversationOrchestrator,
    TurnOutcome,
    TurnPersistence,
)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
CONVERSATION = "cv_example"
USER_MESSAGE = "Nên đi Đà Nẵng vào tháng mấy?"
GENERATED_REPLY = "Tháng 3 đến tháng 8 là đẹp nhất."


class FakeRAGService:
    """Stub `RAGService` facade that records the calls it receives."""

    def __init__(self, journal: list[str], failure: Exception | None = None) -> None:
        self._journal = journal
        self._failure = failure
        self.calls: list[tuple[str, int | None]] = []

    def generate_answer(self, user_message: str, top_k: int | None = None) -> dict:
        self._journal.append("generate_answer")
        self.calls.append((user_message, top_k))
        if self._failure is not None:
            raise self._failure
        return {
            "reply": GENERATED_REPLY,
            "model": "gpt-4o-mini",
            "citations": [
                {"title": "Đà Nẵng", "url": "https://vietnam.travel/da-nang"}
            ],
        }


class FakeConversationService:
    """Stub conversation service that records appended turns in order."""

    def __init__(
        self,
        journal: list[str],
        known_conversations: tuple[str, ...] = (CONVERSATION,),
    ) -> None:
        self._journal = journal
        self._known = set(known_conversations)
        self.appended: list[Message] = []
        self.failures: dict[MessageRole, Exception] = {}

    def append_message(
        self,
        conversation_id: str,
        role,
        content: str,
        source=None,
        trace_visibility=None,
    ) -> Message:
        resolved_role = MessageRole(role)
        self._journal.append(f"append_{resolved_role.value}")

        if conversation_id not in self._known:
            raise ConversationNotFoundError("The conversation does not exist.")

        failure = self.failures.get(resolved_role)
        if failure is not None:
            raise failure

        stored = Message(
            message_id=generate_message_id(),
            conversation_id=conversation_id,
            sequence=len(self.appended) + 1,
            role=resolved_role,
            content=content,
            source=source,
            trace_visibility=trace_visibility,
            created_at=utc_now(),
        )
        self.appended.append(stored)
        return stored


@pytest.fixture
def journal() -> list[str]:
    return []


@pytest.fixture
def rag(journal: list[str]) -> FakeRAGService:
    return FakeRAGService(journal)


@pytest.fixture
def conversations(journal: list[str]) -> FakeConversationService:
    return FakeConversationService(journal)


@pytest.fixture
def orchestrator(rag: FakeRAGService, conversations: FakeConversationService):
    return ConversationOrchestrator(
        rag_service=rag, conversation_service_provider=lambda: conversations
    )


# 1. An unbound turn never touches conversation storage.


def test_unbound_turn_generates_without_any_conversation_call(
    orchestrator, rag, journal
):
    outcome = orchestrator.handle_turn(message=USER_MESSAGE, conversation_id=None)

    assert isinstance(outcome, TurnOutcome)
    assert outcome.reply == GENERATED_REPLY
    assert outcome.model == "gpt-4o-mini"
    assert outcome.citations == [
        {"title": "Đà Nẵng", "url": "https://vietnam.travel/da-nang"}
    ]
    assert outcome.conversation is None
    assert journal == ["generate_answer"]
    assert rag.calls == [(USER_MESSAGE, 4)]


def test_unbound_turn_never_resolves_the_conversation_service(rag, conversations):
    resolved: list[str] = []

    def provider():
        resolved.append("resolved")
        return conversations

    orchestrator = ConversationOrchestrator(
        rag_service=rag, conversation_service_provider=provider
    )

    orchestrator.handle_turn(message=USER_MESSAGE, conversation_id=None)

    assert resolved == [], (
        "an unbound turn must not construct conversation storage, so an unbound "
        "caller cannot be broken by a storage failure"
    )


# 2. An unknown conversation stops the turn before generation.


def test_unknown_conversation_raises_and_never_calls_rag(orchestrator, rag, journal):
    with pytest.raises(ConversationNotFoundError):
        orchestrator.handle_turn(message=USER_MESSAGE, conversation_id="cv_absent")

    assert rag.calls == []
    assert "generate_answer" not in journal


# 3 and 4. The user turn is persisted before generation.


def test_user_turn_is_persisted_before_generation(orchestrator, journal):
    orchestrator.handle_turn(message=USER_MESSAGE, conversation_id=CONVERSATION)

    assert journal == ["append_user", "generate_answer", "append_assistant"]


def test_persisted_user_turn_carries_the_governed_role_and_source(
    orchestrator, conversations
):
    orchestrator.handle_turn(message=USER_MESSAGE, conversation_id=CONVERSATION)

    user_turn = conversations.appended[0]
    assert user_turn.role is MessageRole.USER
    assert user_turn.source is MessageSource.UI
    assert user_turn.content == USER_MESSAGE
    assert user_turn.trace_visibility is TraceVisibility.EXCLUDED


# 5. A user-turn write failure stops the turn before any model call.


def test_user_turn_write_failure_propagates_without_calling_rag(
    orchestrator, conversations, rag, journal
):
    conversations.failures[MessageRole.USER] = ConversationStorageError(
        "storage unavailable"
    )

    with pytest.raises(ConversationStorageError):
        orchestrator.handle_turn(message=USER_MESSAGE, conversation_id=CONVERSATION)

    assert rag.calls == [], "the caller must not be charged for an unrecorded turn"
    assert journal == ["append_user"]


# 6 and 7. A successful bound turn reports both identifiers.


def test_assistant_turn_is_persisted_with_the_model_source(orchestrator, conversations):
    orchestrator.handle_turn(message=USER_MESSAGE, conversation_id=CONVERSATION)

    assistant_turn = conversations.appended[1]
    assert assistant_turn.role is MessageRole.ASSISTANT
    assert assistant_turn.source is MessageSource.MODEL
    assert assistant_turn.content == GENERATED_REPLY


def test_successful_bound_turn_reports_persisted_true(orchestrator, conversations):
    outcome = orchestrator.handle_turn(
        message=USER_MESSAGE, conversation_id=CONVERSATION
    )

    assert isinstance(outcome.conversation, TurnPersistence)
    assert outcome.conversation.conversation_id == CONVERSATION
    assert outcome.conversation.persisted is True
    assert outcome.conversation.user_message_id == conversations.appended[0].message_id
    assert (
        outcome.conversation.assistant_message_id
        == conversations.appended[1].message_id
    )
    assert outcome.reply == GENERATED_REPLY


# 8. An assistant-turn write failure is reported, never hidden.


def test_assistant_turn_write_failure_returns_the_reply_with_persisted_false(
    orchestrator, conversations
):
    conversations.failures[MessageRole.ASSISTANT] = ConversationStorageError(
        "storage unavailable"
    )

    outcome = orchestrator.handle_turn(
        message=USER_MESSAGE, conversation_id=CONVERSATION
    )

    assert outcome.reply == GENERATED_REPLY
    assert outcome.conversation is not None
    assert outcome.conversation.persisted is False
    assert outcome.conversation.assistant_message_id is None
    assert outcome.conversation.user_message_id == conversations.appended[0].message_id
    assert len(conversations.appended) == 1


# 9. A generation failure leaves the persisted user turn intact.


def test_generation_failure_propagates_and_keeps_the_user_turn(
    rag, conversations, journal
):
    failing_rag = FakeRAGService(journal, failure=RuntimeError("model provider down"))
    orchestrator = ConversationOrchestrator(
        rag_service=failing_rag, conversation_service_provider=lambda: conversations
    )

    with pytest.raises(RuntimeError):
        orchestrator.handle_turn(message=USER_MESSAGE, conversation_id=CONVERSATION)

    assert len(conversations.appended) == 1
    assert conversations.appended[0].role is MessageRole.USER
    assert journal == ["append_user", "generate_answer"]


# 10. The orchestrator writes only `user` and `assistant`.


def test_orchestrator_never_writes_a_tool_turn(orchestrator, conversations, journal):
    orchestrator.handle_turn(message=USER_MESSAGE, conversation_id=CONVERSATION)
    orchestrator.handle_turn(
        message="Còn Hội An thì sao?", conversation_id=CONVERSATION
    )

    written_roles = {message.role for message in conversations.appended}
    assert written_roles == {MessageRole.USER, MessageRole.ASSISTANT}
    assert MessageRole.TOOL not in written_roles
    assert "append_tool" not in journal


def test_sequential_bound_turns_persist_four_ordered_messages(
    orchestrator, conversations
):
    orchestrator.handle_turn(message=USER_MESSAGE, conversation_id=CONVERSATION)
    orchestrator.handle_turn(
        message="Còn Hội An thì sao?", conversation_id=CONVERSATION
    )

    assert [message.sequence for message in conversations.appended] == [1, 2, 3, 4]
    assert [message.role.value for message in conversations.appended] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


# 11. The orchestration boundary, asserted against the import graph.

FORBIDDEN_RUNTIME_MODULES = (
    "fastapi",
    "sqlite3",
    "chromadb",
    "backend.app",
    "backend.rag.evaluation",
    "backend.storage",
    "backend.workspaces",
)


def test_orchestrator_module_declares_no_forbidden_direct_import():
    source_path = (
        ROOT_DIR / "backend" / "orchestration" / "conversation_orchestrator.py"
    )
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
    assert offending == set(), (
        f"the orchestrator imports a forbidden dependency: {offending}"
    )


def test_importing_the_orchestrator_loads_no_forbidden_module():
    code = (
        "import json, sys;"
        "import backend.orchestration.conversation_orchestrator;"
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
        f"importing the orchestrator loaded forbidden modules: {offending}"
    )


def test_orchestration_package_exports_the_orchestrator():
    import backend.orchestration as orchestration_package

    for name in ("ConversationOrchestrator", "TurnOutcome", "TurnPersistence"):
        assert hasattr(orchestration_package, name)
