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
        return user, pending

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

    assert journal == ["append_user", "generate_answer", "complete_turn"]


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
    assert journal == ["append_user", "generate_answer", "fail_turn"]
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

        user = SimpleNamespace(message_id="ms_user", conversation_id=conversation_id)
        pending = SimpleNamespace(
            message_id="ms_pending", conversation_id=conversation_id
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
