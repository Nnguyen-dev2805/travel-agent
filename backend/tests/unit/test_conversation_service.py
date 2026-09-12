"""Unit tests for the conversation service.

The service owns validation, identity generation, timestamping, existence
checks, cursor resolution, and owner authorization. It depends on the
conversation repository interface and domain value contracts only.

Per ADR 0021 conversations are standalone and owned directly by authenticated users
with zero workspace dependency.

No test here touches a database, a model provider, Chroma, or the network.
"""

import ast
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

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
    MessageStatus,
    TraceVisibility,
)
from backend.conversations.repository import (
    ConversationAlreadyExistsError,
    ConversationGoneError,
    ConversationStorageError,
    MessageAlreadyExistsError,
    MessageSequenceConflictError,
)
from backend.conversations.service import (
    ConversationNotFoundError,
    ConversationService,
)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

DEFAULT_OWNER = "local-user"


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
        self.deletion_epochs: dict[str, int] = {}
        self.sabotage_after_get = False

    @property
    def writes(self) -> list[tuple]:
        return [
            call
            for call in self.calls
            if call[0] in {
                "create",
                "create_with_initial_turn",
                "append_message",
                "delete",
            }
        ]

    def create(self, conversation: Conversation) -> Conversation:
        self.calls.append(("create", conversation.conversation_id))
        if self.remaining_identity_conflicts > 0:
            self.remaining_identity_conflicts -= 1
            raise ConversationAlreadyExistsError("identity already used")
        self.conversations[conversation.conversation_id] = conversation
        return conversation

    def create_with_initial_turn(
        self,
        conversation: Conversation,
        message: MessageDraft,
        message_id: str,
        assistant_message_id: str,
        outbox_event: dict | None = None,
    ) -> tuple[Conversation, Message, Message]:
        self.calls.append(
            ("create_with_initial_turn", conversation.conversation_id, message_id)
        )
        if self.remaining_identity_conflicts > 0:
            self.remaining_identity_conflicts -= 1
            raise ConversationAlreadyExistsError("identity already used")
        if self.remaining_message_identity_conflicts > 0:
            self.remaining_message_identity_conflicts -= 1
            raise MessageAlreadyExistsError("message identity already used")
        self.conversations[conversation.conversation_id] = conversation
        stored = Message(
            message_id=message_id,
            conversation_id=conversation.conversation_id,
            sequence=1,
            role=message.role,
            content=message.content,
            source=message.source,
            trace_visibility=message.trace_visibility,
            created_at=message.created_at,
            status=MessageStatus.COMPLETE,
        )
        pending = Message(
            message_id=assistant_message_id,
            conversation_id=conversation.conversation_id,
            sequence=2,
            role=MessageRole.ASSISTANT,
            content="",
            source=MessageSource.MODEL,
            trace_visibility=TraceVisibility.EXCLUDED,
            created_at=message.created_at,
            status=MessageStatus.PENDING,
        )
        self.messages.extend((stored, pending))
        return conversation, stored, pending

    def get(
        self, conversation_id: str, owner_user_id: str | None = None
    ) -> Conversation | None:
        self.calls.append(("get", conversation_id))
        stored = self.conversations.get(conversation_id)
        if stored is not None and self.sabotage_after_get:
            # Simulate a concurrent delete landing after this read: the
            # caller keeps a stale active copy while storage is tombstoned.
            self.delete(conversation_id, owner_user_id)
        return stored

    def list_by_owner(
        self, owner_user_id: str, include_deletion: bool = False
    ) -> tuple[Conversation, ...]:
        self.calls.append(("list_by_owner", owner_user_id))
        if self.list_order is not None:
            return self.list_order
        results = []
        for record in self.conversations.values():
            if record.owner_user_id != owner_user_id:
                continue
            if not include_deletion:
                ret = (
                    record.retention_state.value
                    if isinstance(record.retention_state, ConversationRetentionState)
                    else str(record.retention_state)
                )
                if ret in ("tombstoned", "deleted", "deletion_requested"):
                    continue
            results.append(record)
        return tuple(results)

    def delete(self, conversation_id: str, owner_user_id: str | None = None) -> bool:
        self.calls.append(("delete", conversation_id))
        conv = self.conversations.get(conversation_id)
        if conv is None:
            return False
        ret = (
            conv.retention_state.value
            if isinstance(conv.retention_state, ConversationRetentionState)
            else str(conv.retention_state)
        )
        if ret == ConversationRetentionState.TOMBSTONED.value:
            return False
        epoch = self.deletion_epochs.get(conversation_id, 0) + 1
        self.deletion_epochs[conversation_id] = epoch
        tombstoned = Conversation(
            conversation_id=conv.conversation_id,
            owner_user_id=conv.owner_user_id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=datetime.now(timezone.utc),
            retention_state=ConversationRetentionState.TOMBSTONED,
            deletion_epoch=epoch,
        )
        self.conversations[conversation_id] = tombstoned
        return True

    def get_deletion_epoch(
        self, conversation_id: str, owner_user_id: str | None = None
    ) -> int:
        self.calls.append(("get_deletion_epoch", conversation_id))
        return self.deletion_epochs.get(conversation_id, 0)

    def get_message(
        self, message_id: str, owner_user_id: str | None = None
    ) -> Message | None:
        self.calls.append(("get_message", message_id))
        for stored in self.messages:
            if stored.message_id == message_id:
                return stored
        return None

    def append_message(
        self,
        message: MessageDraft,
        message_id: str,
        owner_user_id: str | None = None,
        outbox_event: dict | None = None,
    ) -> Message:
        self.calls.append(("append_message", message.conversation_id, message_id))
        parent = self.conversations.get(message.conversation_id)
        if parent is not None:
            retention = (
                parent.retention_state.value
                if isinstance(parent.retention_state, ConversationRetentionState)
                else str(parent.retention_state)
            )
            if retention != ConversationRetentionState.ACTIVE.value:
                raise ConversationGoneError("Parent conversation is no longer active.")
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
        self,
        conversation_id: str,
        owner_user_id: str | None = None,
        after_sequence: int | None = None,
        limit: int = 50,
        until_sequence: int | None = None,
    ) -> tuple[Message, ...]:
        self.calls.append(("list_messages", conversation_id, after_sequence, limit))
        selected = [
            stored
            for stored in self.messages
            if stored.conversation_id == conversation_id
            and (after_sequence is None or stored.sequence > after_sequence)
            and (until_sequence is None or stored.sequence <= until_sequence)
        ]
        selected.sort(key=lambda stored: stored.sequence)
        return tuple(selected[:limit])


@pytest.fixture
def repository() -> FakeConversationRepository:
    return FakeConversationRepository()


@pytest.fixture
def service(repository: FakeConversationRepository) -> ConversationService:
    return ConversationService(conversation_repository=repository)


def _seeded_conversation(
    service: ConversationService,
    title: str | None = "Da Nang food plan",
    owner_user_id: str = DEFAULT_OWNER,
) -> Conversation:
    return service.create_conversation(
        owner_user_id=owner_user_id,
        title=title,
    )


# 1. Creation returns the repository record with governed identity and defaults.


def test_create_returns_the_repository_record_with_governed_defaults(service):
    conversation = _seeded_conversation(service)

    assert conversation.conversation_id.startswith("cv_")
    assert conversation.owner_user_id == "local-user"
    assert conversation.title == "Da Nang food plan"
    assert conversation.retention_state is ConversationRetentionState.ACTIVE
    assert conversation.created_at == conversation.updated_at
    assert conversation.created_at.utcoffset().total_seconds() == 0
    assert not hasattr(conversation, "workspace_id")


def test_create_accepts_conversation_create_object(service):
    conversation = service.create_conversation(
        ConversationCreate(owner_user_id="user-42", title="Trip to Hue")
    )
    assert conversation.owner_user_id == "user-42"
    assert conversation.title == "Trip to Hue"
    assert conversation.retention_state is ConversationRetentionState.ACTIVE


def test_create_persists_through_the_repository(service, repository):
    conversation = _seeded_conversation(service)
    assert repository.conversations[conversation.conversation_id] == conversation


def test_an_invalid_title_writes_nothing(repository, service):
    with pytest.raises(ConversationValidationError):
        service.create_conversation(owner_user_id="local-user", title="t" * 121)

    assert repository.writes == []


def test_create_rejects_a_non_contract_input_without_writing(service, repository):
    with pytest.raises(ConversationValidationError):
        service.create_conversation(12345)  # type: ignore

    assert repository.writes == []


def test_create_rejects_blank_owner_without_writing(service, repository):
    with pytest.raises(ConversationValidationError):
        service.create_conversation(owner_user_id="   ")

    assert repository.writes == []


# 2. Duplicate identity collision on create is retried once.


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


# 3. Reading conversations: absence, owner-scoping, and retention hiding.


def test_get_returns_none_for_a_missing_conversation(service):
    assert service.get_conversation("cv_absent", DEFAULT_OWNER) is None


def test_get_returns_the_stored_conversation(service):
    conversation = _seeded_conversation(service)
    assert (
        service.get_conversation(conversation.conversation_id, DEFAULT_OWNER)
        == conversation
    )


def test_get_rejects_a_blank_identifier(service):
    with pytest.raises(ConversationValidationError):
        service.get_conversation("   ", DEFAULT_OWNER)


def test_get_rejects_a_blank_owner(service):
    conversation = _seeded_conversation(service)
    with pytest.raises(ConversationValidationError):
        service.get_conversation(conversation.conversation_id, "   ")


def test_get_conversation_with_matching_owner(service):
    conv = _seeded_conversation(service, owner_user_id="alice")
    assert service.get_conversation(conv.conversation_id, owner_user_id="alice") == conv


def test_get_conversation_with_foreign_owner_returns_none(service):
    conv = _seeded_conversation(service, owner_user_id="alice")
    assert service.get_conversation(conv.conversation_id, owner_user_id="bob") is None


def test_get_conversation_hides_tombstoned_records(service, repository):
    conv = _seeded_conversation(service, owner_user_id="alice")
    repository.delete(conv.conversation_id, "alice")

    assert service.get_conversation(conv.conversation_id, "alice") is None


# 4. Listing conversations by owner.


def test_list_returns_repository_order_without_resorting(service, repository):
    first = _seeded_conversation(service, title="First")
    second = _seeded_conversation(service, title="Second")
    repository.list_order = (second, first)

    listed = service.list_conversations("local-user")

    assert listed == (second, first)
    assert isinstance(listed, tuple)


def test_list_returns_empty_tuple_for_user_with_no_conversations(service):
    assert service.list_conversations("nobody") == ()


def test_list_conversations_excludes_other_owners(service):
    _seeded_conversation(service, title="Alice conv", owner_user_id="alice")
    _seeded_conversation(service, title="Bob conv", owner_user_id="bob")

    alice_list = service.list_conversations("alice")
    assert len(alice_list) == 1
    assert alice_list[0].title == "Alice conv"

    bob_list = service.list_conversations("bob")
    assert len(bob_list) == 1
    assert bob_list[0].title == "Bob conv"


def test_list_conversations_rejects_blank_owner(service):
    with pytest.raises(ConversationValidationError):
        service.list_conversations("   ")


# 5. Conversation deletion (tombstoning).


def test_delete_conversation_tombstones_and_hides_conversation(service):
    conv = _seeded_conversation(service, owner_user_id="alice")

    service.delete_conversation(conv.conversation_id, "alice")

    # Conversation is now absent from public get and list
    assert service.get_conversation(conv.conversation_id, "alice") is None
    assert service.list_conversations("alice") == ()


def test_delete_conversation_bumps_the_deletion_epoch(service, repository):
    conv = _seeded_conversation(service, owner_user_id="alice")

    service.delete_conversation(conv.conversation_id, "alice")

    assert service.get_deletion_epoch(conv.conversation_id, "alice") == 1


def test_append_after_direct_tombstone_reports_not_found(service, repository):
    """A delete landing after the owner check fails closed as absence."""
    conv = _seeded_conversation(service, owner_user_id="alice")
    repository.sabotage_after_get = True

    with pytest.raises(ConversationNotFoundError):
        service.append_message(
            conversation_id=conv.conversation_id,
            role=MessageRole.USER,
            content="too late",
            owner_user_id="alice",
        )

    assert repository.messages == []


def test_delete_conversation_for_foreign_owner_raises_not_found(service):
    conv = _seeded_conversation(service, owner_user_id="alice")

    with pytest.raises(ConversationNotFoundError):
        service.delete_conversation(conv.conversation_id, "bob")


def test_delete_conversation_for_missing_conversation_raises_not_found(service):
    with pytest.raises(ConversationNotFoundError):
        service.delete_conversation("cv_missing", "alice")


def test_delete_already_tombstoned_conversation_raises_not_found(service):
    conv = _seeded_conversation(service, owner_user_id="alice")
    service.delete_conversation(conv.conversation_id, "alice")

    with pytest.raises(ConversationNotFoundError):
        service.delete_conversation(conv.conversation_id, "alice")


# 6. Message append with validation, time, ordering, and retry.


def test_append_to_a_missing_conversation_raises_and_writes_nothing(
    service, repository
):
    with pytest.raises(ConversationNotFoundError):
        service.append_message(
            conversation_id="cv_absent",
            role=MessageRole.USER,
            content="xin chào",
            owner_user_id=DEFAULT_OWNER,
        )

    assert repository.writes == []


def test_append_with_matching_owner_succeeds(service):
    conv = _seeded_conversation(service, owner_user_id="alice")
    msg = service.append_message(
        conversation_id=conv.conversation_id,
        role=MessageRole.USER,
        content="xin chào",
        owner_user_id="alice",
    )
    assert msg.sequence == 1
    assert msg.content == "xin chào"


def test_append_with_foreign_owner_raises_not_found(service, repository):
    conv = _seeded_conversation(service, owner_user_id="alice")
    writes_before = len(repository.writes)

    with pytest.raises(ConversationNotFoundError):
        service.append_message(
            conversation_id=conv.conversation_id,
            role=MessageRole.USER,
            content="xin chào",
            owner_user_id="bob",
        )

    assert len(repository.writes) == writes_before


@pytest.mark.parametrize("content", ["", "   ", None])
def test_append_with_invalid_content_writes_nothing(service, repository, content):
    conversation = _seeded_conversation(service)
    writes_before = len(repository.writes)

    with pytest.raises(ConversationValidationError):
        service.append_message(
            conversation_id=conversation.conversation_id,
            role=MessageRole.USER,
            content=content,
            owner_user_id=DEFAULT_OWNER,
        )

    assert len(repository.writes) == writes_before


def test_append_with_a_restricted_role_is_accepted_at_the_service_layer(service):
    conversation = _seeded_conversation(service)

    stored = service.append_message(
        conversation_id=conversation.conversation_id,
        role=MessageRole.ASSISTANT,
        content="Tháng 3 tới tháng 8 là đẹp nhất.",
        owner_user_id=DEFAULT_OWNER,
        source=MessageSource.MODEL,
    )

    assert stored.role is MessageRole.ASSISTANT
    assert stored.source is MessageSource.MODEL


def test_append_sets_created_at_and_leaves_sequence_to_the_repository(service):
    conversation = _seeded_conversation(service)
    before = datetime.now(timezone.utc)

    stored = service.append_message(
        conversation_id=conversation.conversation_id,
        role=MessageRole.USER,
        content="xin chào",
        owner_user_id=DEFAULT_OWNER,
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
        owner_user_id=DEFAULT_OWNER,
    )
    second = service.append_message(
        conversation_id=conversation.conversation_id,
        role=MessageRole.USER,
        content="hai",
        owner_user_id=DEFAULT_OWNER,
    )

    assert (first.sequence, second.sequence) == (1, 2)


def test_duplicate_message_identity_is_retried_once_with_a_fresh_identity(
    service, repository
):
    conversation = _seeded_conversation(service)
    repository.remaining_message_identity_conflicts = 1

    stored = service.append_message(
        conversation_id=conversation.conversation_id,
        role=MessageRole.USER,
        content="xin chào",
        owner_user_id=DEFAULT_OWNER,
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
            owner_user_id=DEFAULT_OWNER,
        )

    assert len([call for call in repository.calls if call[0] == "append_message"]) == 2
    assert repository.messages == []


def test_sequence_collision_is_retried_once_then_succeeds(service, repository):
    conversation = _seeded_conversation(service)
    repository.remaining_sequence_conflicts = 1

    stored = service.append_message(
        conversation_id=conversation.conversation_id,
        role=MessageRole.USER,
        content="xin chào",
        owner_user_id=DEFAULT_OWNER,
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
            owner_user_id=DEFAULT_OWNER,
        )

    assert len([call for call in repository.calls if call[0] == "append_message"]) == 2
    assert repository.messages == []


def test_sequence_conflict_does_not_escape_as_a_repository_error(service, repository):
    conversation = _seeded_conversation(service)
    repository.remaining_sequence_conflicts = 1

    stored = service.append_message(
        conversation_id=conversation.conversation_id,
        role=MessageRole.USER,
        content="xin chào",
        owner_user_id=DEFAULT_OWNER,
    )

    assert stored.message_id.startswith("ms_")


# 7. History and Range reading.


def test_list_messages_for_a_missing_conversation_raises(service):
    with pytest.raises(ConversationNotFoundError):
        service.list_messages(
            MessageHistoryQuery(conversation_id="cv_absent"), DEFAULT_OWNER
        )


def test_list_messages_with_foreign_owner_raises_not_found(service):
    conv = _seeded_conversation(service, owner_user_id="alice")
    with pytest.raises(ConversationNotFoundError):
        service.list_messages(
            MessageHistoryQuery(conversation_id=conv.conversation_id),
            owner_user_id="bob",
        )


def test_list_messages_passes_the_resolved_cursor_and_limit_through(
    service, repository
):
    conversation = _seeded_conversation(service)
    first = service.append_message(
        conversation_id=conversation.conversation_id,
        role=MessageRole.USER,
        content="một",
        owner_user_id=DEFAULT_OWNER,
    )
    service.append_message(
        conversation_id=conversation.conversation_id,
        role=MessageRole.USER,
        content="hai",
        owner_user_id=DEFAULT_OWNER,
    )

    page = service.list_messages(
        MessageHistoryQuery(
            conversation_id=conversation.conversation_id,
            after_message_id=first.message_id,
            limit=10,
        ),
        DEFAULT_OWNER,
    )

    delegated = [call for call in repository.calls if call[0] == "list_messages"][-1]
    assert delegated == ("list_messages", conversation.conversation_id, 1, 10)
    assert [message.content for message in page] == ["hai"]


def test_list_messages_without_a_cursor_delegates_none(service, repository):
    conversation = _seeded_conversation(service)

    service.list_messages(
        MessageHistoryQuery(conversation_id=conversation.conversation_id),
        DEFAULT_OWNER,
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
        owner_user_id=DEFAULT_OWNER,
    )
    calls_before = len(
        [call for call in repository.calls if call[0] == "list_messages"]
    )

    with pytest.raises(ConversationValidationError):
        service.list_messages(
            MessageHistoryQuery(
                conversation_id=first.conversation_id,
                after_message_id=foreign.message_id,
            ),
            DEFAULT_OWNER,
        )

    assert (
        len([call for call in repository.calls if call[0] == "list_messages"])
        == calls_before
    )


def test_list_messages_rejects_an_unknown_cursor(service):
    conversation = _seeded_conversation(service)

    with pytest.raises(ConversationValidationError):
        service.list_messages(
            MessageHistoryQuery(
                conversation_id=conversation.conversation_id,
                after_message_id="ms_never_stored",
            ),
            DEFAULT_OWNER,
        )


def test_list_messages_requires_a_history_query_contract(service):
    with pytest.raises(ConversationValidationError):
        service.list_messages({"conversation_id": "cv_example"}, DEFAULT_OWNER)


def test_get_history_for_owner_succeeds(service):
    conv = _seeded_conversation(service, owner_user_id="alice")
    service.append_message(
        conversation_id=conv.conversation_id,
        role=MessageRole.USER,
        content="hello alice",
        owner_user_id="alice",
    )
    history = service.get_history(conv.conversation_id, "alice")
    assert len(history) == 1
    assert history[0].content == "hello alice"


def test_get_history_with_foreign_owner_raises_not_found(service):
    conv = _seeded_conversation(service, owner_user_id="alice")
    with pytest.raises(ConversationNotFoundError):
        service.get_history(conv.conversation_id, "bob")


def test_get_messages_in_range(service):
    conv = _seeded_conversation(service)
    service.append_message(conv.conversation_id, MessageRole.USER, "m1", DEFAULT_OWNER)
    service.append_message(conv.conversation_id, MessageRole.USER, "m2", DEFAULT_OWNER)

    messages = service.get_messages_in_range(
        conv.conversation_id, DEFAULT_OWNER, after_sequence=1, limit=5
    )
    assert len(messages) == 1
    assert messages[0].content == "m2"


def test_get_messages_in_range_requires_owner(service):
    conv = _seeded_conversation(service, owner_user_id="alice")
    with pytest.raises(ConversationNotFoundError):
        service.get_messages_in_range(conv.conversation_id, "bob")


def test_create_conversation_with_initial_turn(service, repository):
    conv, msg, pending = service.create_conversation_with_initial_turn(
        owner_user_id="alice",
        title="Trip to Da Nang",
        content="Hello Da Nang",
    )
    assert conv.owner_user_id == "alice"
    assert conv.title == "Trip to Da Nang"
    assert msg.conversation_id == conv.conversation_id
    assert msg.sequence == 1
    assert msg.role == MessageRole.USER
    assert msg.content == "Hello Da Nang"
    # The first turn also allocates the reply slot (ADR 0023), so a first-turn
    # failure has a row to mark rather than an orphan.
    assert pending.conversation_id == conv.conversation_id
    assert pending.sequence == 2
    assert pending.role == MessageRole.ASSISTANT
    assert pending.status is MessageStatus.PENDING
    assert pending.content == ""
    assert (
        "create_with_initial_turn",
        conv.conversation_id,
        msg.message_id,
    ) in repository.calls


# 8. Dependency boundary assertion.

FORBIDDEN_RUNTIME_MODULES = (
    "fastapi",
    "pydantic",
    "sqlite3",
    "chromadb",
    "openai",
    "backend.rag",
    "backend.app",
    "backend.storage",
    "backend.workspaces",
)


def test_service_module_declares_no_forbidden_direct_import():
    source_path = ROOT_DIR / "backend" / "conversations" / "service.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    runtime_imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
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
