"""Conversation storage interface and repository error types.

Per ADR 0021 conversations are standalone and owned directly by authenticated users.
Route handlers, the conversation service, and the orchestrator must not
embed table DDL, SQL statements, database path creation, or connection
management.

The interface takes `after_sequence` rather than `after_message_id`, because the
service resolves a caller cursor to its stored position before delegating. The
repository therefore never has to interpret an identifier.
"""

from __future__ import annotations

from typing import Protocol

from backend.conversations.models import (
    Conversation,
    ConversationRetentionState,
    Message,
    MessageDraft,
    OutboxIntent,
    TransitionResult,
)


class ConversationRepositoryError(Exception):
    """Base class for conversation storage failures."""


class ConversationAlreadyExistsError(ConversationRepositoryError):
    """A conversation with the same identity already exists in storage."""


class MessageAlreadyExistsError(ConversationRepositoryError):
    """A message with the same identity already exists in storage.

    Distinct from `MessageSequenceConflictError`: this reports a collision on the
    server-generated `message_id`, which the service retries once with a fresh
    identity, whereas a sequence conflict reports a contested turn position.
    """


class MessageSequenceConflictError(ConversationRepositoryError):
    """A message already occupies the allocated position in this conversation.

    Raised instead of overwriting or reordering a turn, because later provenance
    depends on turn order being a stored fact.
    """


class ConversationStorageError(ConversationRepositoryError):
    """Storage could not complete the requested conversation operation.

    Messages raised as this type are safe for a controlled HTTP 500 response.
    They must not carry local filesystem paths, full SQL text, credentials, or
    message content.
    """


class ConversationGoneError(ConversationRepositoryError):
    """The parent conversation is missing or no longer active.

    Raised instead of writing into a tombstoned conversation when a delete
    lands between the service-level check and the storage transaction. The
    service maps this to `ConversationNotFoundError` so callers observe the
    same absent-resource contract as a missing conversation.
    """


class ConversationRepository(Protocol):
    """Persistence boundary for conversation and message records."""

    def create(self, conversation: Conversation) -> Conversation:
        """Persist a new conversation and return the stored record.

        Raises:
            ConversationAlreadyExistsError: The conversation identity is used.
            ConversationStorageError: Storage failed for another reason.
        """
        ...

    def create_with_initial_turn(
        self,
        conversation: Conversation,
        message: MessageDraft,
        message_id: str,
        assistant_message_id: str,
        outbox_event: OutboxIntent | dict | None = None,
    ) -> tuple[Conversation, Message, Message]:
        """Atomically persist a new conversation and its first turn.

        The conversation, the user message, the pending assistant row and the
        outbox event commit in one transaction, so auto-creation cannot leave an
        orphaned conversation, a user message with no reply slot, or a live
        extraction event over an unanswered range (ADR 0023).

        Returns `(conversation, user_message, pending_assistant_message)`.

        Raises:
            ConversationAlreadyExistsError: The conversation identity is used.
            MessageAlreadyExistsError: A message identity is used.
            ConversationStorageError: Storage failed for another reason.
        """
        ...

    def get(self, conversation_id: str, owner_user_id: str) -> Conversation | None:
        """Return the owner-scoped conversation, or None when no record exists."""
        ...

    def list_by_owner(
        self, owner_user_id: str, include_deletion: bool = False
    ) -> tuple[Conversation, ...]:
        """Return conversations directly owned by one user in governed order.

        Per ADR 0021 conversations are owned directly by owner_user_id.
        Ordering is `created_at` descending, then `conversation_id` ascending.
        Records in tombstoned or deletion retention states are excluded unless
        `include_deletion` is true.
        """
        ...

    def delete(self, conversation_id: str, owner_user_id: str) -> bool:
        """Tombstone one owner-scoped conversation and cancel its outbox work.

        Returns True if the conversation existed and was tombstoned, False otherwise.

        Raises:
            ConversationStorageError: Storage failed.
        """
        ...

    def get_deletion_epoch(self, conversation_id: str, owner_user_id: str) -> int:
        """Return the conversation deletion epoch, reading tombstoned rows too."""
        ...

    def append_message(
        self,
        message: MessageDraft,
        message_id: str,
        owner_user_id: str,
        outbox_event: OutboxIntent | dict | None = None,
    ) -> Message:
        """Persist one message under a server-generated identity.

        `message_id` is generated by the service, which also owns the single
        retry on a collision, so identity generation stays in one layer for both
        conversations and messages. `MessageDraft` therefore carries neither the
        identity nor the position.

        The adapter allocates `sequence` and advances the parent conversation's
        `updated_at` inside one transaction, so a failed insert leaves neither
        the position nor the parent timestamp changed.

        Raises:
            MessageAlreadyExistsError: The message identity is already used.
            MessageSequenceConflictError: The allocated position is taken.
            ConversationStorageError: Storage failed for another reason.
        """
        ...

    def append_turn(
        self,
        conversation_id: str,
        owner_user_id: str,
        user_content: str,
        assistant_placeholder: str = "",
        outbox_event: OutboxIntent | dict | None = None,
    ) -> tuple[Message, Message]:
        """Allocate one turn in one transaction under one parent-row lock.

        The user message, the pending assistant row and the outbox event commit
        together, and both sequences are allocated together, so turn adjacency
        holds under concurrent turns (ADR 0023). This is the only path that
        allocates a user/assistant pair.

        Identity is generated by the adapter rather than passed in, because the
        two identities and the two sequences must be allocated inside the same
        transaction to stay correlated.

        Returns `(user_message, pending_assistant_message)`.

        Raises:
            ConversationGoneError: The conversation is missing or not active.
            MessageAlreadyExistsError: A generated identity is already used.
            MessageSequenceConflictError: The allocated position is taken.
            ConversationStorageError: Storage failed for another reason.
        """
        ...

    def complete_turn(
        self,
        conversation_id: str,
        message_id: str,
        owner_user_id: str,
        content: str,
    ) -> TransitionResult:
        """Set content and status on a pending assistant row.

        Guarded by `status = 'pending'`, so a duplicate call is a no-op rather
        than an overwrite. Fails closed when the conversation is tombstoned or
        its `deletion_epoch` has moved.

        Returns `TransitionResult`, whose `applied` is `True` only when *this* call
        performed the transition. A caller must branch on that rather than on the
        returned row: the row is returned unchanged when another writer won, so
        reporting success on it would claim a reply the database does not hold.

        Raises:
            ConversationGoneError: The conversation is gone, or the row is absent.
            ConversationStorageError: Storage failed.
        """
        ...

    def fail_turn(
        self, conversation_id: str, message_id: str, owner_user_id: str
    ) -> TransitionResult:
        """Mark a pending assistant row failed. Idempotent.

        Never overwrites a completed row. The row carries no content, so a
        failed turn cannot hold a partial reply or a provider error string.

        Returns `TransitionResult` for the same reason `complete_turn` does: the
        caller must be able to tell "I failed this turn" from "it was already
        terminal, so there was nothing to fail".

        Raises:
            ConversationGoneError: The conversation is gone, or the row is absent.
            ConversationStorageError: Storage failed.
        """
        ...

    def get_message(self, message_id: str, owner_user_id: str) -> Message | None:
        """Return one stored owner-scoped message, or None when no record exists.

        The service uses this to resolve a caller's `after_message_id` cursor to
        a stored `sequence` and to reject a cursor that belongs to a different
        conversation, which is why the repository never interprets an identifier
        during a page read.
        """
        ...

    def list_messages(
        self,
        conversation_id: str,
        owner_user_id: str,
        after_sequence: int | None,
        limit: int,
        until_sequence: int | None = None,
    ) -> tuple[Message, ...]:
        """Return up to `limit` messages in `(after_sequence, until_sequence]`.

        Messages are ordered by `sequence` ascending, which is transcript
        reading order. The read is scoped to `conversation_id`, so a position
        resolved elsewhere cannot widen the result set.

        `until_sequence` bounds the read from above. A range extraction event
        belongs to one turn; without an upper bound it read every later message
        in the conversation and attributed them to its own provenance.
        """
        ...
