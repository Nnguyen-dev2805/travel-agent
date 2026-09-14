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
    MessageStatus,
    OutboxIntent,
    TraceVisibility,
    TransitionResult,
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
OWNER = "local-user"


def _principal(owner: str = OWNER, mode: str = "authenticated"):
    from types import SimpleNamespace

    return SimpleNamespace(owner_user_id=owner, auth_mode=mode)


def _real_principal(owner: str = OWNER):
    """A genuine AuthenticatedPrincipal, so enum-vs-string drift is visible."""
    from backend.security.models import AuthenticatedPrincipal, AuthMode

    return AuthenticatedPrincipal(
        owner_user_id=owner,
        auth_mode=AuthMode.AUTHENTICATED,
        credential_label="local_token",
    )


DEFAULT_PRINCIPAL = _principal()


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
        self.outbox_events: list[tuple[str, str, Any]] = []
        self.outbox_by_turn: dict[tuple[str, str], str] = {}

    def create_conversation(self, owner_user_id: str = OWNER, title: str | None = None):
        from types import SimpleNamespace

        new_id = f"cv_{len(self._known) + 1}"
        self._known.add(new_id)
        self._journal.append("create_conversation")
        return SimpleNamespace(
            conversation_id=new_id,
            owner_user_id=owner_user_id,
            title=title,
        )

    def get_recent_messages_before(
        self,
        conversation_id: str,
        owner_user_id: str = OWNER,
        before_sequence: int | None = None,
        limit: int = 50,
    ) -> tuple[Message, ...]:
        """The bounded recent-dialogue window over the turns this double recorded.

        Journalled, so a test can prove the read happens before generation rather
        than after.
        """
        self._journal.append("get_recent_messages_before")
        eligible = [
            message
            for message in self.appended
            if message.conversation_id == conversation_id
            and (before_sequence is None or message.sequence < before_sequence)
        ]
        eligible.sort(key=lambda message: message.sequence)
        return tuple(eligible[-limit:])

    def create_conversation_with_initial_turn(
        self,
        owner_user_id: str = OWNER,
        title: str | None = None,
        content: str = "",
        role: MessageRole | str = MessageRole.USER,
        source: MessageSource | str | None = MessageSource.UI,
        trace_visibility: TraceVisibility | str | None = None,
        outbox_event: OutboxIntent | dict | None = None,
    ):
        from types import SimpleNamespace

        resolved_role = MessageRole(role)
        # The first turn writes the user row and the reply slot together, so
        # either role failing fails the whole turn.
        self._fail_if_role_fails(MessageRole.USER, MessageRole.ASSISTANT)

        new_id = f"cv_{len(self._known) + 1}"
        self._known.add(new_id)
        self._journal.append("create_conversation")
        self._journal.append(f"append_{resolved_role.value}")
        conv = SimpleNamespace(
            conversation_id=new_id,
            owner_user_id=owner_user_id,
            title=title,
        )
        stored = Message(
            message_id=generate_message_id(),
            conversation_id=new_id,
            sequence=1,
            role=resolved_role,
            content=content,
            source=source,
            trace_visibility=trace_visibility,
            created_at=utc_now(),
            status=MessageStatus.COMPLETE,
        )
        pending = Message(
            message_id=generate_message_id(),
            conversation_id=new_id,
            sequence=2,
            role=MessageRole.ASSISTANT,
            content="",
            source=MessageSource.MODEL,
            trace_visibility=TraceVisibility.EXCLUDED,
            created_at=utc_now(),
            status=MessageStatus.PENDING,
        )
        self.appended.extend((stored, pending))
        if outbox_event is not None:
            self.outbox_events.append((new_id, stored.message_id, outbox_event))
            self.outbox_by_turn[(new_id, stored.message_id)] = f"outbox_{stored.message_id}"
        return conv, stored, pending

    def append_turn(
        self,
        conversation_id: str,
        owner_user_id: str = OWNER,
        user_content: str = "",
        assistant_placeholder: str = "",
        outbox_event=None,
    ) -> tuple[Message, Message]:
        self._journal.append("append_user")
        if conversation_id not in self._known:
            raise ConversationNotFoundError("The conversation does not exist.")
        self._fail_if_role_fails(MessageRole.USER, MessageRole.ASSISTANT)

        base = len(self.appended) + 1
        user = Message(
            message_id=generate_message_id(),
            conversation_id=conversation_id,
            sequence=base,
            role=MessageRole.USER,
            content=user_content,
            source=MessageSource.UI,
            trace_visibility=TraceVisibility.EXCLUDED,
            created_at=utc_now(),
            status=MessageStatus.COMPLETE,
        )
        pending = Message(
            message_id=generate_message_id(),
            conversation_id=conversation_id,
            sequence=base + 1,
            role=MessageRole.ASSISTANT,
            content=assistant_placeholder,
            source=MessageSource.MODEL,
            trace_visibility=TraceVisibility.EXCLUDED,
            created_at=utc_now(),
            status=MessageStatus.PENDING,
        )
        self.appended.extend((user, pending))
        if outbox_event is not None:
            self.outbox_events.append((conversation_id, user.message_id, outbox_event))
            self.outbox_by_turn[(conversation_id, user.message_id)] = f"outbox_{user.message_id}"
        return user, pending

    def get_turn_outbox_id(
        self,
        conversation_id: str,
        message_id: str,
        owner_user_id: str = OWNER,
    ) -> str | None:
        self._journal.append("get_turn_outbox_id")
        return self.outbox_by_turn.get((conversation_id, message_id))

    def complete_turn(
        self,
        conversation_id: str,
        message_id: str,
        owner_user_id: str = OWNER,
        content: str = "",
    ) -> Message:
        self._journal.append("complete_turn")
        if conversation_id not in self._known:
            raise ConversationNotFoundError("The conversation does not exist.")
        failure = self.failures.get(MessageRole.ASSISTANT)
        if failure is not None:
            raise failure
        return self._transition_turn(message_id, MessageStatus.COMPLETE, content)

    def fail_turn(
        self,
        conversation_id: str,
        message_id: str,
        owner_user_id: str = OWNER,
    ) -> Message:
        self._journal.append("fail_turn")
        if conversation_id not in self._known:
            raise ConversationNotFoundError("The conversation does not exist.")
        return self._transition_turn(message_id, MessageStatus.FAILED, "")

    def _fail_if_role_fails(self, *roles: MessageRole) -> None:
        for role in roles:
            failure = self.failures.get(role)
            if failure is not None:
                raise failure

    def _transition_turn(
        self, message_id: str, status: MessageStatus, content: str
    ) -> TransitionResult:
        """Mirror the adapter's guard *and* its result shape.

        `applied=False` on the already-terminal path is the whole point: the row
        comes back unchanged, so the row alone cannot tell the caller whether it
        wrote anything.
        """
        for index, stored in enumerate(self.appended):
            if stored.message_id != message_id:
                continue
            if stored.status is not MessageStatus.PENDING:
                return TransitionResult(message=stored, applied=False)
            updated = Message(
                message_id=stored.message_id,
                conversation_id=stored.conversation_id,
                sequence=stored.sequence,
                role=stored.role,
                content=content,
                source=stored.source,
                trace_visibility=stored.trace_visibility,
                created_at=stored.created_at,
                status=status,
            )
            self.appended[index] = updated
            return TransitionResult(message=updated, applied=True)
        raise ConversationNotFoundError("The conversation does not exist.")

    def get_conversation(self, conversation_id: str, owner_user_id: str = OWNER):
        from types import SimpleNamespace

        if conversation_id not in self._known:
            return None
        return SimpleNamespace(
            conversation_id=conversation_id, owner_user_id=owner_user_id
        )

    def append_message(
        self,
        conversation_id: str,
        role,
        content: str,
        owner_user_id: str = OWNER,
        source=None,
        trace_visibility=None,
        outbox_event=None,
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


# 1. Turn 1 auto-creates conversation for authenticated principal.


def test_first_turn_without_conversation_id_auto_creates_conversation(
    orchestrator, rag, journal
):
    outcome = orchestrator.handle_turn(
        message=USER_MESSAGE, conversation_id=None, principal=DEFAULT_PRINCIPAL
    )

    assert isinstance(outcome, TurnOutcome)
    assert outcome.reply == GENERATED_REPLY
    assert outcome.model == "gpt-4o-mini"
    assert outcome.citations == [
        {"title": "Đà Nẵng", "url": "https://vietnam.travel/da-nang"}
    ]
    assert outcome.conversation is not None
    assert outcome.conversation.persisted is True
    assert outcome.conversation.conversation_id.startswith("cv_")
    assert journal == [
        "create_conversation",
        "append_user",
        "get_recent_messages_before",
        "generate_answer",
        "complete_turn",
    ]
    assert rag.calls == [(USER_MESSAGE, 4)]


def test_first_turn_without_principal_raises_conversation_not_found(orchestrator, rag):
    from backend.conversations.service import ConversationNotFoundError

    with pytest.raises(ConversationNotFoundError):
        orchestrator.handle_turn(
            message=USER_MESSAGE, conversation_id=None, principal=None
        )
    assert rag.calls == []


# 2. An unknown conversation stops the turn before generation.


def test_unknown_conversation_raises_and_never_calls_rag(orchestrator, rag, journal):
    from backend.security.models import CrossOwnerAccessError

    with pytest.raises(CrossOwnerAccessError):
        orchestrator.handle_turn(
            message=USER_MESSAGE,
            conversation_id="cv_absent",
            principal=DEFAULT_PRINCIPAL,
        )

    assert rag.calls == []
    assert "generate_answer" not in journal


# 3 and 4. The user turn is persisted before generation.


def test_user_turn_is_persisted_before_generation(orchestrator, journal):
    orchestrator.handle_turn(
        message=USER_MESSAGE,
        conversation_id=CONVERSATION,
        principal=DEFAULT_PRINCIPAL,
    )

    # The recent-dialogue read now sits between phase one and generation: the
    # turn's own rows must be committed before its context is reconstructed, and
    # the read happens before generation so the state is available to it.
    assert journal == [
        "append_user",
        "get_recent_messages_before",
        "generate_answer",
        "complete_turn",
    ]


def test_persisted_user_turn_carries_the_governed_role_and_source(
    orchestrator, conversations
):
    orchestrator.handle_turn(
        message=USER_MESSAGE,
        conversation_id=CONVERSATION,
        principal=DEFAULT_PRINCIPAL,
    )

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
        orchestrator.handle_turn(
            message=USER_MESSAGE,
            conversation_id=CONVERSATION,
            principal=DEFAULT_PRINCIPAL,
        )

    assert rag.calls == [], "the caller must not be charged for an unrecorded turn"
    assert journal == ["append_user"]


# 6 and 7. A successful bound turn reports both identifiers.


def test_assistant_turn_is_persisted_with_the_model_source(orchestrator, conversations):
    orchestrator.handle_turn(
        message=USER_MESSAGE,
        conversation_id=CONVERSATION,
        principal=DEFAULT_PRINCIPAL,
    )

    assistant_turn = conversations.appended[1]
    assert assistant_turn.role is MessageRole.ASSISTANT
    assert assistant_turn.source is MessageSource.MODEL
    assert assistant_turn.content == GENERATED_REPLY


def test_successful_bound_turn_reports_persisted_true(orchestrator, conversations):
    outcome = orchestrator.handle_turn(
        message=USER_MESSAGE,
        conversation_id=CONVERSATION,
        principal=DEFAULT_PRINCIPAL,
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


def test_assistant_row_write_failure_fails_the_turn_before_generation(
    orchestrator, conversations, journal
):
    """A turn whose reply slot cannot be written fails the whole turn.

    Before ADR 0023 the assistant row was appended after generation, so a failed
    write still produced an outcome with `persisted=False` — a degraded success
    the caller could not distinguish from a real one. The turn now allocates
    both rows before generation, so the failure propagates and no model call is
    made for a reply that could not be stored. This test previously asserted the
    `persisted=False` outcome and was changed with the contract.
    """
    conversations.failures[MessageRole.ASSISTANT] = ConversationStorageError(
        "storage unavailable"
    )

    with pytest.raises(ConversationStorageError):
        orchestrator.handle_turn(
            message=USER_MESSAGE,
            conversation_id=CONVERSATION,
            principal=DEFAULT_PRINCIPAL,
        )

    assert "generate_answer" not in journal, "no model call for an unrecorded turn"
    assert conversations.appended == [], "a failed turn writes no partial rows"


# 9. A generation failure records a failed turn instead of an orphan (ADR 0023).


def test_generation_failure_propagates_and_records_a_failed_turn(
    rag, conversations, journal
):
    failing_rag = FakeRAGService(journal, failure=RuntimeError("model provider down"))
    orchestrator = ConversationOrchestrator(
        rag_service=failing_rag, conversation_service_provider=lambda: conversations
    )

    with pytest.raises(RuntimeError) as excinfo:
        orchestrator.handle_turn(
            message=USER_MESSAGE,
            conversation_id=CONVERSATION,
            principal=DEFAULT_PRINCIPAL,
        )

    # The turn is recorded, not orphaned: a complete user row and a failed reply
    # slot that carries no content and no provider error string.
    assert [message.role for message in conversations.appended] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]
    assert [message.status for message in conversations.appended] == [
        MessageStatus.COMPLETE,
        MessageStatus.FAILED,
    ]
    assert conversations.appended[1].content == ""
    assert journal == [
        "append_user",
        "get_recent_messages_before",
        "generate_answer",
        "fail_turn",
    ]
    # The failure carries the conversation id so a first-turn failure can tell
    # the client which conversation to continue (defect C2).
    assert excinfo.value.conversation_id == CONVERSATION


# 10. The orchestrator writes only `user` and `assistant`.


def test_orchestrator_never_writes_a_tool_turn(orchestrator, conversations, journal):
    orchestrator.handle_turn(
        message=USER_MESSAGE,
        conversation_id=CONVERSATION,
        principal=DEFAULT_PRINCIPAL,
    )
    orchestrator.handle_turn(
        message="Còn Hội An thì sao?",
        conversation_id=CONVERSATION,
        principal=DEFAULT_PRINCIPAL,
    )

    written_roles = {message.role for message in conversations.appended}
    assert written_roles == {MessageRole.USER, MessageRole.ASSISTANT}
    assert MessageRole.TOOL not in written_roles
    assert "append_tool" not in journal


def test_sequential_bound_turns_persist_four_ordered_messages(
    orchestrator, conversations
):
    orchestrator.handle_turn(
        message=USER_MESSAGE,
        conversation_id=CONVERSATION,
        principal=DEFAULT_PRINCIPAL,
    )
    orchestrator.handle_turn(
        message="Còn Hội An thì sao?",
        conversation_id=CONVERSATION,
        principal=DEFAULT_PRINCIPAL,
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


# 12. Authenticated bound turns resolve the conversation owner first.


class _AuthConversations:
    """Owner-scoped conversation service double.

    Mirrors the repository contract: a read scoped to one owner never returns
    another owner's conversation, so the orchestrator cannot even observe it.
    """

    def __init__(self):
        self.appended: list = []

    def get_recent_messages_before(
        self,
        conversation_id: str,
        owner_user_id: str = "owner_a",
        before_sequence: int | None = None,
        limit: int = 50,
    ) -> tuple:
        """No prior dialogue in these fixtures; the auth assertions do not need it."""
        return ()

    def get_conversation(self, conversation_id: str, owner_user_id: str):
        from types import SimpleNamespace

        owners = {"cv_mine": "owner_a", "cv_theirs": "owner_b"}
        if owners.get(conversation_id) != owner_user_id:
            return None
        return SimpleNamespace(
            conversation_id=conversation_id,
            owner_user_id=owner_user_id,
        )

    def append_message(
        self, conversation_id: str, role, content: str, owner_user_id: str, **kwargs
    ):
        from types import SimpleNamespace

        message = SimpleNamespace(message_id="ms_test", conversation_id=conversation_id)
        self.appended.append(message)
        return message

    def append_turn(
        self,
        conversation_id: str,
        owner_user_id: str,
        user_content: str = "",
        assistant_placeholder: str = "",
        outbox_event=None,
    ):
        """Allocate the user row and the pending reply slot together."""
        from types import SimpleNamespace

        user = SimpleNamespace(
            message_id="ms_user", conversation_id=conversation_id, sequence=1
        )
        pending = SimpleNamespace(
            message_id="ms_pending", conversation_id=conversation_id, sequence=2
        )
        self.appended.append(user)
        return user, pending

    def complete_turn(
        self,
        conversation_id: str,
        message_id: str,
        owner_user_id: str,
        content: str = "",
    ):
        # A real `Message`, not a `SimpleNamespace`: the orchestrator now reads the
        # returned status, and a message always has one — `Message.__post_init__`
        # coerces an absent status to COMPLETE. A double that omits the field is
        # standing in for something that cannot exist.
        message = Message(
            message_id=message_id,
            conversation_id=conversation_id,
            sequence=2,
            role=MessageRole.ASSISTANT,
            content=content,
            source=MessageSource.MODEL,
            trace_visibility=TraceVisibility.EXCLUDED,
            created_at=utc_now(),
            status=MessageStatus.COMPLETE,
        )
        self.appended.append(message)
        return TransitionResult(message=message, applied=True)

    def fail_turn(self, conversation_id: str, message_id: str, owner_user_id: str):
        from types import SimpleNamespace

        message = SimpleNamespace(message_id=message_id, conversation_id=conversation_id)
        self.appended.append(message)
        return TransitionResult(message=message, applied=True)


def _auth_orchestrator():
    conversations = _AuthConversations()
    orchestrator = ConversationOrchestrator(
        rag_service=FakeRAGService([]),
        conversation_service_provider=lambda: conversations,
    )
    return orchestrator, conversations


def test_authenticated_principal_denies_foreign_conversation():
    from backend.security.models import CrossOwnerAccessError

    orchestrator, conversations = _auth_orchestrator()

    with pytest.raises(CrossOwnerAccessError):
        orchestrator.handle_turn(
            "hi", "cv_theirs", principal=_principal("owner_a", "authenticated")
        )
    assert conversations.appended == []


def test_authenticated_principal_denies_missing_conversation():
    from backend.security.models import CrossOwnerAccessError

    orchestrator, conversations = _auth_orchestrator()

    with pytest.raises(CrossOwnerAccessError):
        orchestrator.handle_turn(
            "hi", "cv_missing", principal=_principal("owner_a", "authenticated")
        )
    assert conversations.appended == []


def test_authenticated_principal_allows_own_conversation():
    orchestrator, conversations = _auth_orchestrator()

    outcome = orchestrator.handle_turn(
        "hi", "cv_mine", principal=_principal("owner_a", "authenticated")
    )

    assert outcome.reply == GENERATED_REPLY
    assert len(conversations.appended) == 2


def test_missing_principal_is_denied():
    """Owner is mandatory; an unauthenticated bound turn is not a legacy path."""
    orchestrator, conversations = _auth_orchestrator()

    with pytest.raises(ConversationNotFoundError):
        orchestrator.handle_turn("hi", "cv_theirs")

    assert conversations.appended == []


def test_non_authenticated_principal_is_denied():
    """Compatibility mode is removed; a non-authenticated principal has no scoped access."""
    orchestrator, conversations = _auth_orchestrator()

    with pytest.raises(ConversationNotFoundError):
        orchestrator.handle_turn(
            "hi", "cv_theirs", principal=_principal("owner_a", "compatibility")
        )

    assert conversations.appended == []


def test_real_authenticated_principal_allows_own_conversation():
    """The auth-mode branch must match a genuine principal, not just strings."""
    orchestrator, conversations = _auth_orchestrator()

    outcome = orchestrator.handle_turn(
        "hi", "cv_mine", principal=_real_principal("owner_a")
    )

    assert outcome.reply == GENERATED_REPLY
    assert len(conversations.appended) == 2


def test_real_authenticated_principal_denies_foreign_conversation():
    from backend.security.models import CrossOwnerAccessError

    orchestrator, conversations = _auth_orchestrator()

    with pytest.raises(CrossOwnerAccessError):
        orchestrator.handle_turn(
            "hi", "cv_theirs", principal=_real_principal("owner_a")
        )
    assert conversations.appended == []


# --- a terminal turn written by another actor is not this turn's reply ---------


class _AnotherWriterWon(FakeConversationService):
    """`complete_turn` reports that another actor moved the row first.

    The repository is deliberately idempotent — "a row that is no longer pending is
    returned unchanged, so a retry cannot overwrite a completed turn" — and its
    adapter returns `TransitionResult(applied=False)` on that path. This double
    reproduces the result shape, including the row the other writer left behind.

    Three foreign states matter and they are not the same:

    * `failed` — the reply is nowhere.
    * `complete` with *different content* — the reply is nowhere either, and this is
      the case a status-only check accepts by mistake: the row says `complete`, so a
      caller reading only the status reports success while the database holds
      someone else's answer.
    * `pending` — a storage layer that silently did nothing, the worst case to
      report success on.

    Nothing currently writes the first two, which is exactly why the seam has to be
    closed now: the orchestrator's job is to not report a reply the database does
    not contain, and the only way to prove that is to hand it one.
    """

    def __init__(self, journal, *, status, content="", applied=False):
        super().__init__(journal)
        self._status = status
        self._content = content
        self._applied = applied

    def complete_turn(
        self,
        conversation_id: str,
        message_id: str,
        owner_user_id: str = OWNER,
        content: str = "",
    ) -> TransitionResult:
        self._journal.append("complete_turn")
        return TransitionResult(
            message=Message(
                message_id=message_id,
                conversation_id=conversation_id,
                sequence=2,
                role=MessageRole.ASSISTANT,
                content=self._content,
                source=MessageSource.MODEL,
                trace_visibility=TraceVisibility.EXCLUDED,
                created_at=utc_now(),
                status=self._status,
            ),
            applied=self._applied,
        )


def _handle_with_foreign_transition(rag, journal, **kwargs):
    conversations = _AnotherWriterWon(journal, **kwargs)
    orchestrator = ConversationOrchestrator(
        rag_service=rag, conversation_service_provider=lambda: conversations
    )
    return orchestrator.handle_turn(
        message=USER_MESSAGE,
        conversation_id=None,
        principal=DEFAULT_PRINCIPAL,
    )


@pytest.mark.parametrize(
    ("status", "content"),
    [
        (MessageStatus.FAILED, ""),
        (MessageStatus.COMPLETE, "Một câu trả lời khác hoàn toàn."),
        (MessageStatus.PENDING, ""),
    ],
    ids=["failed-by-another-actor", "completed-with-other-content", "no-op-storage"],
)
def test_a_transition_this_request_did_not_apply_is_never_reported_as_persisted(
    rag, journal, status, content
):
    """`applied` is the fact; the returned row is not.

    The middle case is the one a status-only check accepts: the row is `complete`,
    so a caller reading the status sees success — while the database holds a
    different reply and the client is handed this request's.
    """
    from backend.orchestration.conversation_orchestrator import (
        TurnTerminalWithoutContentError,
    )

    with pytest.raises(TurnTerminalWithoutContentError):
        _handle_with_foreign_transition(rag, journal, status=status, content=content)


def test_an_identical_content_from_another_writer_is_still_not_this_reply(rag, journal):
    """The rejected fix, made explicit.

    Comparing `assistant_message.content` against the generated reply would accept
    this case, because the two are equal — and two turns legitimately producing the
    same text is not a hypothetical. `applied` is what makes the answer independent
    of the text.
    """
    from backend.orchestration.conversation_orchestrator import (
        TurnTerminalWithoutContentError,
    )

    with pytest.raises(TurnTerminalWithoutContentError):
        _handle_with_foreign_transition(
            rag, journal, status=MessageStatus.COMPLETE, content=GENERATED_REPLY
        )


def test_the_control_a_completed_turn_is_still_reported_as_persisted(rag, journal):
    """Without this, the test above would pass if the path broke for any reason."""
    conversations = FakeConversationService(journal)
    orchestrator = ConversationOrchestrator(
        rag_service=rag, conversation_service_provider=lambda: conversations
    )

    outcome = orchestrator.handle_turn(
        message=USER_MESSAGE,
        conversation_id=None,
        principal=DEFAULT_PRINCIPAL,
    )

    assert outcome.conversation.persisted is True
    assert outcome.reply == GENERATED_REPLY


# 13. Task 4: Stage-1 understanding / routing / planning is wired but shadow-only.


#: An ambiguous speech act, so the planner proposes `NONE` rather than `RAG_ONLY`.
AMBIGUOUS_MESSAGE = "nhớ là tôi thích cà phê, nhưng quên chuyện cũ đi"

#: An obvious explicit remember, which the gate corroborates and routes to the
#: Memory branch — where Stage 1 still has no handler.
REMEMBER_MESSAGE = "nhớ là tôi thích cà phê muối"


def _stage_one_orchestrator(rag, journal, **kwargs):
    conversations = FakeConversationService(journal)
    return ConversationOrchestrator(
        rag_service=rag,
        conversation_service_provider=lambda: conversations,
        **kwargs,
    )


def test_a_stage_one_none_proposal_still_executes_the_rag_generation_path(rag, journal):
    """The load-bearing Stage-1 rollout assertion (`plan v0.7:478-480`).

    An ambiguous reading makes the planner propose `NONE`. If that proposal were
    authoritative, retrieval would be skipped and the turn would answer without
    grounding — on the authority of a component that has not passed its hard
    gate. While `CONTEXT_PLANNER_ENFORCEMENT_ENABLED` is false the existing RAG
    path must run exactly as before.
    """
    orchestrator = _stage_one_orchestrator(rag, journal)

    outcome = orchestrator.handle_turn(
        message=AMBIGUOUS_MESSAGE,
        conversation_id=None,
        principal=DEFAULT_PRINCIPAL,
    )

    assert rag.calls, "the RAG generation path was skipped by a shadow proposal"
    assert "generate_answer" in journal
    assert outcome.reply == GENERATED_REPLY
    assert outcome.conversation.persisted is True


def test_the_recent_dialogue_window_is_read_before_generation(rag, journal):
    """Context is reconstructed from committed turns, then generation runs."""
    orchestrator = _stage_one_orchestrator(rag, journal)

    orchestrator.handle_turn(
        message=USER_MESSAGE, conversation_id=None, principal=DEFAULT_PRINCIPAL
    )

    assert "get_recent_messages_before" in journal
    assert journal.index("get_recent_messages_before") < journal.index("generate_answer")


def test_the_outcome_carries_an_internal_disposition(rag, journal):
    """`TurnOutcome` gains the disposition without changing the Chat schema."""
    from backend.orchestration.turn_models import TurnDisposition

    orchestrator = _stage_one_orchestrator(rag, journal)

    outcome = orchestrator.handle_turn(
        message=USER_MESSAGE, conversation_id=None, principal=DEFAULT_PRINCIPAL
    )

    assert outcome.disposition is TurnDisposition.ANSWERED


def test_a_recognized_explicit_action_still_answers_normally_in_stage_one(rag, journal):
    """Task 4 proves understanding quality; it does not execute a mutation.

    The remember is recognized and the gate corroborates it, but the handler that
    would write Memory is Task 8. Stage 1 must therefore keep the normal answer
    path and write nothing.
    """
    orchestrator = _stage_one_orchestrator(rag, journal)

    outcome = orchestrator.handle_turn(
        message=REMEMBER_MESSAGE,
        conversation_id=None,
        principal=DEFAULT_PRINCIPAL,
    )

    assert outcome.reply == GENERATED_REPLY
    assert outcome.memory is None, "Stage 1 has no Memory mutation surface"


def test_an_enforcing_planner_is_injectable_without_changing_the_default(rag, journal):
    """The rollout gate is a composition-root decision, so it must be injectable.

    The orchestrator cannot read settings itself — `backend.app` is a forbidden
    direct import for this module — so the composition root passes the planner.
    Injecting one must not change the shadow default for callers that do not.
    """
    from backend.orchestration.context_planner import ContextPlanner

    conversations = FakeConversationService(journal)
    orchestrator = ConversationOrchestrator(
        rag_service=rag,
        conversation_service_provider=lambda: conversations,
        context_planner=ContextPlanner(enforcement_enabled=True),
    )

    outcome = orchestrator.handle_turn(
        message=AMBIGUOUS_MESSAGE,
        conversation_id=None,
        principal=DEFAULT_PRINCIPAL,
    )

    # Even with enforcement on, Stage 1 still answers through the existing path:
    # the planner has no Memory source to switch to, and Task 10 owns execution.
    assert outcome.reply == GENERATED_REPLY
    assert rag.calls


def test_a_context_read_failure_fails_the_turn_instead_of_stranding_it(rag, journal):
    """The Stage-1 read must sit inside the turn's failure handler.

    A storage error while reconstructing context is a failure of this turn. Left
    outside the handler it would skip `_fail_turn` and strand the `PENDING`
    assistant row this turn had just written, which is exactly the orphan the
    two-phase design exists to prevent.
    """
    from backend.conversations.repository import ConversationStorageError

    class _FailingWindow(FakeConversationService):
        def get_recent_messages_before(self, *args, **kwargs):
            raise ConversationStorageError("window read failed")

    conversations = _FailingWindow(journal)
    orchestrator = ConversationOrchestrator(
        rag_service=rag, conversation_service_provider=lambda: conversations
    )

    with pytest.raises(ConversationStorageError):
        orchestrator.handle_turn(
            message=USER_MESSAGE,
            conversation_id=CONVERSATION,
            principal=DEFAULT_PRINCIPAL,
        )

    assert "fail_turn" in journal, "the pending assistant row was stranded"
    assert not rag.calls, "generation ran for a turn that had already failed"


# 14. Task 4 review fixes 4 and 5.


def test_inspect_returns_a_controlled_unavailable_outcome(rag, journal):
    """Stage 1 recognizes inspect but cannot deliver it; the read path is Stage 3.

    Answering with an ordinary RAG reply would masquerade as a successful
    inspection of Memory that does not exist (`spec:397-401`).
    """
    from backend.orchestration.conversation_orchestrator import (
        INSPECT_UNAVAILABLE_REPLY,
    )
    from backend.orchestration.turn_models import TurnDisposition

    orchestrator = _stage_one_orchestrator(rag, journal)

    outcome = orchestrator.handle_turn(
        message="bạn nhớ gì về tôi?",
        conversation_id=None,
        principal=DEFAULT_PRINCIPAL,
    )

    assert not rag.calls, "inspect was answered by the RAG path"
    assert outcome.reply == INSPECT_UNAVAILABLE_REPLY
    assert outcome.reply != GENERATED_REPLY
    assert outcome.citations == []
    assert outcome.disposition is TurnDisposition.INCOMPLETE
    assert outcome.conversation.persisted is True


def test_an_ordinary_query_still_uses_the_rag_path(rag, journal):
    """The control for the test above: the inspect branch must not swallow queries."""
    orchestrator = _stage_one_orchestrator(rag, journal)

    outcome = orchestrator.handle_turn(
        message=USER_MESSAGE,
        conversation_id=None,
        principal=DEFAULT_PRINCIPAL,
    )

    assert rag.calls
    assert outcome.reply == GENERATED_REPLY


def test_a_dialogue_state_invariant_failure_is_not_a_user_validation_error(rag, journal):
    """A mixed-conversation window is a server-side invariant failure, not user input.

    `ConversationValidationError` is mapped to HTTP 422 by the chat route, so
    letting it escape would answer a bug in our own composition with a
    client-error status.
    """
    from backend.conversations.models import ConversationValidationError
    from backend.conversations.repository import ConversationRepositoryError

    class _MixedConversationWindow(FakeConversationService):
        def get_recent_messages_before(
            self, conversation_id, owner_user_id=OWNER, before_sequence=None, limit=50
        ):
            def _row(sequence, conversation, role, content, source):
                return Message(
                    message_id=generate_message_id(),
                    conversation_id=conversation,
                    sequence=sequence,
                    role=role,
                    content=content,
                    source=source,
                    created_at=utc_now(),
                    status=MessageStatus.COMPLETE,
                )

            return (
                _row(1, "cv_one", MessageRole.USER, "a", MessageSource.UI),
                _row(2, "cv_two", MessageRole.ASSISTANT, "b", MessageSource.MODEL),
            )

    conversations = _MixedConversationWindow(journal)
    orchestrator = ConversationOrchestrator(
        rag_service=rag, conversation_service_provider=lambda: conversations
    )

    with pytest.raises(ConversationRepositoryError) as excinfo:
        orchestrator.handle_turn(
            message=USER_MESSAGE,
            conversation_id=CONVERSATION,
            principal=DEFAULT_PRINCIPAL,
        )

    assert not isinstance(excinfo.value, ConversationValidationError), (
        "this would surface to the user as a 422"
    )
    assert "fail_turn" in journal
    assert not rag.calls


# ---------------------------------------------------------------------------
# Task 5: the Stage-1 turn produces a typed, non-authoritative proposal.
# ---------------------------------------------------------------------------


def test_a_normal_query_proposes_background_eligibility(rag, journal):
    """The ordinary turn is the one source condition that may be eligible.

    `spec:442`. Orchestration states the *reason*; the module derives the
    outcome, so this also proves the mapping is applied at the call site rather
    than the caller asserting an outcome of its own.
    """
    from backend.memory.source_handling import (
        MemoryFamily,
        SourceHandlingProposal,
        SourceHandlingProposalOutcome,
        SourceHandlingReason,
    )

    orchestrator = _stage_one_orchestrator(rag, journal)

    outcome = orchestrator.handle_turn(
        message=USER_MESSAGE, conversation_id=None, principal=DEFAULT_PRINCIPAL
    )

    proposal = outcome.source_handling
    assert isinstance(proposal, SourceHandlingProposal)
    assert proposal.family is MemoryFamily.SEMANTIC
    assert proposal.outcome is SourceHandlingProposalOutcome.BACKGROUND_ELIGIBLE
    assert proposal.reason_code is SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE


def test_the_proposal_is_keyed_by_the_persisted_user_message(rag, journal):
    """The proposal names the source it is evidence about, and nothing else.

    `spec:484-486`: Task 5 keys the proposal by the already-known source message
    identity. A proposal that carried no identity, or a fabricated one, could
    not be bound to a real outbox row in Stage 2.
    """
    orchestrator = _stage_one_orchestrator(rag, journal)

    outcome = orchestrator.handle_turn(
        message=USER_MESSAGE, conversation_id=None, principal=DEFAULT_PRINCIPAL
    )

    assert (
        outcome.source_handling.source_message_id
        == outcome.conversation.user_message_id
    )


def test_an_explicit_remember_proposes_a_blocked_source(rag, journal):
    """An explicit Memory command must not double as inference permission.

    `ADR 0038:61-64`. The handler that would write Memory is Task 8, so in
    Stage 1 the turn is only *recognized*; the source-handling consequence is
    already decided, and it is a refusal.
    """
    from backend.memory.source_handling import (
        SourceHandlingProposalOutcome,
        SourceHandlingReason,
    )

    orchestrator = _stage_one_orchestrator(rag, journal)

    outcome = orchestrator.handle_turn(
        message=REMEMBER_MESSAGE, conversation_id=None, principal=DEFAULT_PRINCIPAL
    )

    assert outcome.source_handling.outcome is (
        SourceHandlingProposalOutcome.BACKGROUND_BLOCKED
    )
    assert outcome.source_handling.reason_code is SourceHandlingReason.EXPLICIT_ACTION


def test_an_ambiguous_turn_proposes_a_blocked_source(rag, journal):
    """An unresolvable reading is refused, not guessed into eligibility."""
    from backend.memory.source_handling import (
        SourceHandlingProposalOutcome,
        SourceHandlingReason,
    )

    orchestrator = _stage_one_orchestrator(rag, journal)

    outcome = orchestrator.handle_turn(
        message=AMBIGUOUS_MESSAGE, conversation_id=None, principal=DEFAULT_PRINCIPAL
    )

    assert outcome.source_handling.outcome is (
        SourceHandlingProposalOutcome.BACKGROUND_BLOCKED
    )
    assert outcome.source_handling.reason_code is SourceHandlingReason.AMBIGUOUS_INTENT


def test_the_proposal_is_never_an_authoritative_record(rag, journal):
    """Orchestration may propose; only the Stage-2 seam may persist.

    `spec:486-490`. If orchestration ever built a `SourceHandlingRecord` it would
    have to invent `source_outbox_id`, which is the storage identity the plan
    forbids this task from obtaining.
    """
    from backend.memory.source_handling import SourceHandlingRecord

    orchestrator = _stage_one_orchestrator(rag, journal)

    outcome = orchestrator.handle_turn(
        message=USER_MESSAGE, conversation_id=None, principal=DEFAULT_PRINCIPAL
    )

    assert not isinstance(outcome.source_handling, SourceHandlingRecord)
    assert not hasattr(outcome.source_handling, "source_outbox_id")


def test_producing_a_proposal_does_not_add_a_storage_call(rag, journal):
    """The proposal is derived from the turn, not read back from anywhere.

    A Stage-1 implementation that looked the outbox row up would widen the
    Conversation API and move the Stage-2 binding boundary into Task 5.
    """
    orchestrator = _stage_one_orchestrator(rag, journal)

    orchestrator.handle_turn(
        message=USER_MESSAGE, conversation_id=None, principal=DEFAULT_PRINCIPAL
    )

    assert "get_outbox" not in journal
    assert "claim_event" not in journal
    assert not [entry for entry in journal if "outbox" in entry.lower()], journal


def test_the_proposal_does_not_change_the_answer(rag, journal):
    """The load-bearing rollout assertion: this task is evidence, not behaviour.

    `plan v0.6:481-483`. A source-handling proposal that altered the reply, the
    retrieval path, or the persistence result would be a behavioural change
    smuggled in under a contracts task.
    """
    orchestrator = _stage_one_orchestrator(rag, journal)

    outcome = orchestrator.handle_turn(
        message=USER_MESSAGE, conversation_id=None, principal=DEFAULT_PRINCIPAL
    )

    assert outcome.reply == GENERATED_REPLY
    assert outcome.conversation.persisted is True
    assert rag.calls, "retrieval was skipped"


def test_every_interaction_mode_has_a_source_handling_reason():
    """The reading -> reason mapping must be total over `InteractionMode`.

    This is an authority boundary, so it is checked by enumeration rather than
    by sampling. If a later stage adds a reading and does not classify it, this
    fails immediately — the alternative is that the new reading inherits
    whatever the implementation's final branch happens to return.
    """
    from backend.memory.source_handling import SourceHandlingReason
    from backend.orchestration.conversation_orchestrator import (
        _source_handling_reason_for,
    )
    from backend.orchestration.turn_models import InteractionMode

    mapped = {mode: _source_handling_reason_for(mode) for mode in InteractionMode}

    assert set(mapped) == set(InteractionMode)
    assert mapped[InteractionMode.NORMAL_QUERY] is (
        SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE
    )


def test_only_the_ordinary_query_reading_is_positive():
    """Exactly one reading may propose eligibility, and it is the plain query."""
    from backend.memory.source_handling import SourceHandlingReason
    from backend.orchestration.conversation_orchestrator import (
        _source_handling_reason_for,
    )
    from backend.orchestration.turn_models import InteractionMode

    positive = [
        mode
        for mode in InteractionMode
        if _source_handling_reason_for(mode)
        is SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE
    ]

    assert positive == [InteractionMode.NORMAL_QUERY]


def test_an_unknown_reading_fails_closed():
    """An unclassified reading must not inherit eligibility.

    The first version of this mapping ended in
    `return BACKGROUND_POLICY_ELIGIBLE`, so anything that was not explicit or
    ambiguous — including a value that is not an `InteractionMode` at all — was
    treated as an ordinary query. For an authority boundary the safe direction
    is refusal and the loud direction is an error: a reading that is silently
    blocked is a defect nobody notices until a family stops forming.
    """
    from backend.orchestration.conversation_orchestrator import (
        _source_handling_reason_for,
    )

    with pytest.raises(ValueError):
        _source_handling_reason_for("future_mode")


# ---------------------------------------------------------------------------
# Task 8: Stage 2 Explicit Memory Turns & Orchestrator Integration
# ---------------------------------------------------------------------------


def test_outbox_intent_created_when_explicit_actions_enabled_even_if_outbox_disabled(
    rag, conversations, journal
):
    """Owner Correction 1: Outbox intent created when explicit_actions_enabled OR outbox_enabled."""
    orchestrator = ConversationOrchestrator(
        rag_service=rag,
        conversation_service_provider=lambda: conversations,
        outbox_enabled=False,
        explicit_actions_enabled=True,
    )
    orchestrator.handle_turn(
        message="Hello",
        conversation_id=CONVERSATION,
        principal=DEFAULT_PRINCIPAL,
    )
    assert len(conversations.outbox_events) == 1
    conv_id, msg_id, outbox_intent = conversations.outbox_events[0]
    assert outbox_intent.event_type == "memory.extract.conversation_range"


def test_explicit_actions_disabled_runs_baseline_rag(rag, conversations, journal):
    """When explicit actions are disabled, explicit interaction mode runs baseline RAG."""
    orchestrator = ConversationOrchestrator(
        rag_service=rag,
        conversation_service_provider=lambda: conversations,
        outbox_enabled=False,
        explicit_actions_enabled=False,
    )
    outcome = orchestrator.handle_turn(
        message="Nhớ là tôi thích khách sạn yên tĩnh",
        conversation_id=CONVERSATION,
        principal=DEFAULT_PRINCIPAL,
    )
    assert "generate_answer" in journal
    assert "complete_turn" in journal
    assert outcome.reply == GENERATED_REPLY


def test_explicit_actions_inspect_returns_unavailable_and_records_noop(
    rag, conversations, journal
):
    """EXPLICIT_INSPECT returns unavailable reply, records EXPLICIT_NOOP source handling."""
    from backend.memory.source_handling import SourceHandlingOutcome, SourceHandlingRecord
    from backend.orchestration.conversation_orchestrator import INSPECT_UNAVAILABLE_REPLY

    recorded_records: list[SourceHandlingRecord] = []
    orchestrator = ConversationOrchestrator(
        rag_service=rag,
        conversation_service_provider=lambda: conversations,
        outbox_enabled=False,
        explicit_actions_enabled=True,
        source_handling_recorder=lambda owner, rec: recorded_records.append(rec) or True,
    )

    outcome = orchestrator.handle_turn(
        message="Xem ký ức của tôi",
        conversation_id=CONVERSATION,
        principal=DEFAULT_PRINCIPAL,
    )

    assert outcome.reply == INSPECT_UNAVAILABLE_REPLY
    assert "complete_turn" in journal
    assert "generate_answer" not in journal
    assert len(recorded_records) == 1
    assert recorded_records[0].outcome is SourceHandlingOutcome.EXPLICIT_NOOP


def test_explicit_actions_clarification_records_refused_and_completes_turn(
    rag, conversations, journal
):
    """Ambiguous or invalid explicit turn yields clarification and records EXPLICIT_REFUSED."""
    from backend.memory.explicit_actions import (
        ExplicitMemoryActionHandler,
        ExplicitMemoryProposal,
        ProposalOutcome,
    )
    from backend.memory.source_handling import SourceHandlingOutcome, SourceHandlingReason, SourceHandlingRecord

    recorded_records: list[SourceHandlingRecord] = []

    class FakeHandler:
        def propose(self, understanding, state, *, owner_user_id: str, **kwargs):
            return ExplicitMemoryProposal(
                outcome=ProposalOutcome.CLARIFICATION,
                clarification_prompt="Bạn có thể nói rõ hơn không?",
                reason="ambiguous",
            )

    orchestrator = ConversationOrchestrator(
        rag_service=rag,
        conversation_service_provider=lambda: conversations,
        outbox_enabled=False,
        explicit_actions_enabled=True,
        explicit_action_handler=FakeHandler(),
        source_handling_recorder=lambda owner, rec: recorded_records.append(rec) or True,
    )

    outcome = orchestrator.handle_turn(
        message="Hãy nhớ cho tôi",
        conversation_id=CONVERSATION,
        principal=DEFAULT_PRINCIPAL,
    )

    assert outcome.reply == "Bạn có thể nói rõ hơn không?"
    assert "complete_turn" in journal
    assert "generate_answer" not in journal
    assert len(recorded_records) == 1
    assert recorded_records[0].outcome is SourceHandlingOutcome.EXPLICIT_REFUSED
    assert recorded_records[0].reason_code is SourceHandlingReason.AMBIGUOUS_INTENT


def test_explicit_actions_mutation_commits_via_coordinator_without_complete_turn(
    rag, conversations, journal
):
    """Mutating explicit turn commits via coordinator and DOES NOT call complete_turn."""
    from backend.memory.explicit_actions import (
        ExplicitMemoryProposal,
        ProposalOutcome,
    )
    from backend.memory.commit_coordinators import (
        ExplicitMemoryCommitRequest,
        ExplicitMemoryCommitResult,
    )
    from backend.memory.write_pipeline.models import (
        MemoryChangeSet,
        MemoryOperation,
    )
    from backend.memory.write_pipeline.uow import MemoryWriteResult
    from backend.memory.source_handling import SourceHandlingOutcome

    captured_requests: list[ExplicitMemoryCommitRequest] = []

    class FakeCoordinator:
        def commit(self, request: ExplicitMemoryCommitRequest):
            journal.append("coordinator_commit")
            captured_requests.append(request)
            return ExplicitMemoryCommitResult(
                memory=MemoryWriteResult(
                    operation=MemoryOperation.ADD,
                    version_id="ver_1",
                    superseded_version_ids=(),
                    reference_version_id=None,
                    decision_id=None,
                    reason="test_add",
                ),
                transition=TransitionResult(
                    message=Message(
                        message_id=request.assistant_message_id,
                        conversation_id=request.conversation_id,
                        sequence=2,
                        role=MessageRole.ASSISTANT,
                        content=request.acknowledgement_text,
                        source=MessageSource.MODEL,
                        trace_visibility=TraceVisibility.EXCLUDED,
                        created_at=utc_now(),
                        status=MessageStatus.COMPLETE,
                    ),
                    applied=True,
                ),
            )

    change = MemoryChangeSet(
        operation=MemoryOperation.ADD,
        identity=None,
        new_version=None,
        superseded_version_ids=(),
        reference_version_id=None,
        reason="test_add",
    )

    class FakeHandler:
        def propose(self, understanding, state, *, owner_user_id: str, **kwargs):
            return ExplicitMemoryProposal(
                outcome=ProposalOutcome.MUTATION,
                canonical_key="travel.preference.hotel_atmosphere",
                change=change,
                expected_version_id=None,
                acknowledgement_text="Đã lưu sở thích khách sạn yên tĩnh!",
                reason="mutation",
            )

    orchestrator = ConversationOrchestrator(
        rag_service=rag,
        conversation_service_provider=lambda: conversations,
        outbox_enabled=False,
        explicit_actions_enabled=True,
        explicit_action_handler=FakeHandler(),
        explicit_memory_commit=FakeCoordinator(),
    )

    outcome = orchestrator.handle_turn(
        message="Nhớ là tôi thích khách sạn yên tĩnh",
        conversation_id=CONVERSATION,
        principal=DEFAULT_PRINCIPAL,
    )

    assert outcome.reply == "Đã lưu sở thích khách sạn yên tĩnh!"
    assert "coordinator_commit" in journal
    assert "complete_turn" not in journal, "Orchestrator MUST NOT call complete_turn for coordinator commits"
    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert req.idempotency_key.startswith("exp_")
    assert req.source_handling_record.source_outbox_id.startswith("outbox_")
    assert req.source_handling_record.outcome is SourceHandlingOutcome.EXPLICIT_APPLIED


def test_explicit_actions_stale_version_retries_once_and_succeeds(
    rag, conversations, journal
):
    """On StaleVersionError, orchestrator re-reads snapshot and retries commit once."""
    from backend.memory.commit_coordinators import (
        ExplicitMemoryCommitRequest,
        ExplicitMemoryCommitResult,
    )
    from backend.memory.explicit_actions import (
        ExplicitMemoryProposal,
        ProposalOutcome,
    )
    from backend.memory.write_pipeline.models import (
        MemoryChangeSet,
        MemoryOperation,
    )
    from backend.memory.write_pipeline.uow import MemoryWriteResult, StaleVersionError

    attempts = 0

    class RetryingCoordinator:
        def commit(self, request: ExplicitMemoryCommitRequest):
            nonlocal attempts
            attempts += 1
            journal.append("coordinator_commit")
            if attempts == 1:
                raise StaleVersionError("Version mismatch")
            return ExplicitMemoryCommitResult(
                memory=MemoryWriteResult(
                    operation=MemoryOperation.SUPERSEDE,
                    version_id="ver_2",
                    superseded_version_ids=("ver_old",),
                    reference_version_id=None,
                    decision_id=None,
                    reason="test_supersede",
                ),
                transition=TransitionResult(
                    message=Message(
                        message_id=request.assistant_message_id,
                        conversation_id=request.conversation_id,
                        sequence=2,
                        role=MessageRole.ASSISTANT,
                        content=request.acknowledgement_text,
                        source=MessageSource.MODEL,
                        trace_visibility=TraceVisibility.EXCLUDED,
                        created_at=utc_now(),
                        status=MessageStatus.COMPLETE,
                    ),
                    applied=True,
                ),
            )

    class FakeHandler:
        def propose(self, understanding, state, *, owner_user_id: str, **kwargs):
            return ExplicitMemoryProposal(
                outcome=ProposalOutcome.MUTATION,
                canonical_key="travel.preference.hotel_atmosphere",
                change=MemoryChangeSet(
                    operation=MemoryOperation.SUPERSEDE,
                    identity=None,
                    new_version=None,
                    superseded_version_ids=("ver_old",),
                    reference_version_id=None,
                    reason="test_supersede",
                ),
                expected_version_id="ver_old" if attempts == 0 else "ver_new",
                acknowledgement_text="Đã cập nhật!",
                reason="mutation",
            )

    orchestrator = ConversationOrchestrator(
        rag_service=rag,
        conversation_service_provider=lambda: conversations,
        outbox_enabled=False,
        explicit_actions_enabled=True,
        explicit_action_handler=FakeHandler(),
        explicit_memory_commit=RetryingCoordinator(),
    )

    outcome = orchestrator.handle_turn(
        message="Sửa lại là tôi thích khách sạn trung tâm",
        conversation_id=CONVERSATION,
        principal=DEFAULT_PRINCIPAL,
    )

    assert attempts == 2
    assert outcome.reply == "Đã cập nhật!"
    assert "complete_turn" not in journal


def test_explicit_actions_stale_version_exhausted_fails_turn(
    rag, conversations, journal
):
    """When StaleVersionError persists after retry, orchestrator fails turn cleanly."""
    from backend.memory.commit_coordinators import ExplicitMemoryCommitRequest
    from backend.memory.explicit_actions import (
        ExplicitMemoryProposal,
        ProposalOutcome,
    )
    from backend.memory.write_pipeline.models import (
        MemoryChangeSet,
        MemoryOperation,
    )
    from backend.memory.write_pipeline.uow import StaleVersionError

    class AlwaysStaleCoordinator:
        def commit(self, request: ExplicitMemoryCommitRequest):
            journal.append("coordinator_commit")
            raise StaleVersionError("Permanent conflict")

    class FakeHandler:
        def propose(self, understanding, state, *, owner_user_id: str, **kwargs):
            return ExplicitMemoryProposal(
                outcome=ProposalOutcome.MUTATION,
                canonical_key="travel.preference.hotel_atmosphere",
                change=MemoryChangeSet(
                    operation=MemoryOperation.SUPERSEDE,
                    identity=None,
                    new_version=None,
                    superseded_version_ids=(),
                    reference_version_id=None,
                    reason="test",
                ),
                expected_version_id="ver_old",
                acknowledgement_text="Đã cập nhật!",
                reason="mutation",
            )

    orchestrator = ConversationOrchestrator(
        rag_service=rag,
        conversation_service_provider=lambda: conversations,
        outbox_enabled=False,
        explicit_actions_enabled=True,
        explicit_action_handler=FakeHandler(),
        explicit_memory_commit=AlwaysStaleCoordinator(),
    )

    with pytest.raises(StaleVersionError):
        orchestrator.handle_turn(
            message="Sửa lại là tôi thích khách sạn trung tâm",
            conversation_id=CONVERSATION,
            principal=DEFAULT_PRINCIPAL,
        )

    assert "fail_turn" in journal


def test_explicit_actions_forget_commits_with_forget_applied_outcome(
    rag, conversations, journal
):
    """Revoke explicit turn commits via coordinator with FORGET_APPLIED outcome."""
    from backend.memory.explicit_actions import (
        ExplicitMemoryProposal,
        ProposalOutcome,
    )
    from backend.memory.commit_coordinators import (
        ExplicitMemoryCommitRequest,
        ExplicitMemoryCommitResult,
    )
    from backend.memory.write_pipeline.models import (
        MemoryChangeSet,
        MemoryOperation,
    )
    from backend.memory.write_pipeline.uow import MemoryWriteResult
    from backend.memory.source_handling import SourceHandlingOutcome

    captured_requests: list[ExplicitMemoryCommitRequest] = []

    class FakeCoordinator:
        def commit(self, request: ExplicitMemoryCommitRequest):
            journal.append("coordinator_commit")
            captured_requests.append(request)
            return ExplicitMemoryCommitResult(
                memory=MemoryWriteResult(
                    operation=MemoryOperation.REVOKE,
                    version_id=None,
                    superseded_version_ids=("ver_1",),
                    reference_version_id="ver_1",
                    decision_id=None,
                    reason="test_revoke",
                ),
                transition=TransitionResult(
                    message=Message(
                        message_id=request.assistant_message_id,
                        conversation_id=request.conversation_id,
                        sequence=2,
                        role=MessageRole.ASSISTANT,
                        content=request.acknowledgement_text,
                        source=MessageSource.MODEL,
                        trace_visibility=TraceVisibility.EXCLUDED,
                        created_at=utc_now(),
                        status=MessageStatus.COMPLETE,
                    ),
                    applied=True,
                ),
            )

    change = MemoryChangeSet(
        operation=MemoryOperation.REVOKE,
        identity=None,
        new_version=None,
        superseded_version_ids=("ver_1",),
        reference_version_id="ver_1",
        reason="test_revoke",
    )

    class FakeHandler:
        def propose(self, understanding, state, *, owner_user_id: str, **kwargs):
            return ExplicitMemoryProposal(
                outcome=ProposalOutcome.MUTATION,
                canonical_key="travel.preference.hotel_atmosphere",
                change=change,
                expected_version_id="ver_1",
                acknowledgement_text="Đã quên sở thích khách sạn yên tĩnh.",
                reason="mutation",
            )

    orchestrator = ConversationOrchestrator(
        rag_service=rag,
        conversation_service_provider=lambda: conversations,
        outbox_enabled=False,
        explicit_actions_enabled=True,
        explicit_action_handler=FakeHandler(),
        explicit_memory_commit=FakeCoordinator(),
    )

    outcome = orchestrator.handle_turn(
        message="Quên sở thích khách sạn yên tĩnh đi",
        conversation_id=CONVERSATION,
        principal=DEFAULT_PRINCIPAL,
    )

    assert outcome.reply == "Đã quên sở thích khách sạn yên tĩnh."
    assert "coordinator_commit" in journal
    assert "complete_turn" not in journal
    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert req.source_handling_record.outcome is SourceHandlingOutcome.FORGET_APPLIED
