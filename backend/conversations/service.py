"""Conversation use cases for authenticated chat.

The service owns validation, identity generation, timestamping, existence
checks, cursor resolution, and owner authorization. It depends on the
conversation contracts and the conversation repository interface only.

Per ADR 0021 conversations are standalone records owned directly by
`owner_user_id`. There are no workspace associations or fallback scopes.

`ConversationNotFoundError` exists so the route layer can map a missing or
foreign conversation to `404` without inspecting storage details or disclosing
ownership.

Message content passes through this module and is never logged.
"""

from __future__ import annotations

import logging

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
    OutboxIntent,
    TraceVisibility,
    TransitionResult,
    coerce_outbox_intent,
    generate_conversation_id,
    generate_message_id,
    require_text,
    utc_now,
)
from backend.conversations.repository import (
    ConversationAlreadyExistsError,
    ConversationGoneError,
    ConversationRepository,
    ConversationStorageError,
    MessageAlreadyExistsError,
    MessageSequenceConflictError,
)

logger = logging.getLogger("travel_agent_conversations")

MAX_IDENTITY_ATTEMPTS = 2
"""One initial attempt plus exactly one retry on a generated-identity collision."""

_HIDDEN_RETENTION_VALUES = frozenset(
    {
        ConversationRetentionState.DELETION_REQUESTED.value,
        ConversationRetentionState.DELETED.value,
        ConversationRetentionState.TOMBSTONED.value,
    }
)


class ConversationNotFoundError(Exception):
    """The referenced conversation does not exist or is not accessible."""


class ConversationService:
    """Create and inspect standalone conversation records behind approved contracts."""

    def __init__(
        self,
        conversation_repository: ConversationRepository,
    ) -> None:
        self._conversations = conversation_repository

    def create_conversation(
        self,
        owner_user_id: str | ConversationCreate,
        title: str | None = None,
    ) -> Conversation:
        """Create one standalone conversation owned directly by the user.

        Accepts either an owner identifier string or a `ConversationCreate` input.
        A generated-identity collision is retried exactly once with a fresh
        identity. A second collision raises `ConversationStorageError` rather
        than leaving a partial write or looping.

        Raises:
            ConversationValidationError: Input validation failed.
            ConversationStorageError: Identity generation collided twice or
                storage failed.
        """
        if isinstance(owner_user_id, ConversationCreate):
            owner = owner_user_id.owner_user_id
            conv_title = owner_user_id.title
            retention_state = owner_user_id.retention_state
        elif isinstance(owner_user_id, str):
            owner = require_text(owner_user_id, "owner_user_id")
            conv_title = title
            retention_state = ConversationRetentionState.ACTIVE
        else:
            raise ConversationValidationError(
                "create_conversation requires an owner_user_id string or ConversationCreate input."
            )

        moment = utc_now()
        for remaining in reversed(range(MAX_IDENTITY_ATTEMPTS)):
            candidate = Conversation(
                conversation_id=generate_conversation_id(),
                owner_user_id=owner,
                title=conv_title,
                created_at=moment,
                updated_at=moment,
                retention_state=retention_state,
            )
            try:
                created = self._conversations.create(candidate)
            except ConversationAlreadyExistsError:
                if remaining == 0:
                    raise ConversationStorageError(
                        "Could not allocate a unique conversation identity after "
                        f"{MAX_IDENTITY_ATTEMPTS} attempts."
                    ) from None
                continue

            logger.info(
                "conversation.create ok conversation_id=%s owner_user_id=%s",
                created.conversation_id,
                created.owner_user_id,
            )
            return created

        raise ConversationStorageError(
            "Conversation creation made no storage attempt because the configured "
            "identity attempt budget is not positive."
        )

    def create_conversation_with_initial_turn(
        self,
        owner_user_id: str,
        title: str | None,
        content: str,
        role: MessageRole | str = MessageRole.USER,
        source: MessageSource | str | None = MessageSource.UI,
        trace_visibility: TraceVisibility | str | None = None,
        outbox_event: OutboxIntent | dict | None = None,
    ) -> tuple[Conversation, Message, Message]:
        """Atomically create a standalone conversation and its first turn.

        The conversation, the user message, the pending assistant row and the
        outbox event commit in one transaction, so turn-1 auto-creation cannot
        leave an orphaned conversation, a user message with no reply slot, or a
        live extraction event over an unanswered range (ADR 0023).

        Returns `(conversation, user_message, pending_assistant_message)`.

        Raises:
            ConversationValidationError: Input validation failed.
            ConversationStorageError: Storage failed.
        """
        owner = require_text(owner_user_id, "owner_user_id")
        outbox_intent = coerce_outbox_intent(outbox_event)
        moment = utc_now()

        for remaining in reversed(range(MAX_IDENTITY_ATTEMPTS)):
            conv_id = generate_conversation_id()
            msg_id = generate_message_id()
            assistant_msg_id = generate_message_id()
            candidate = Conversation(
                conversation_id=conv_id,
                owner_user_id=owner,
                title=title,
                created_at=moment,
                updated_at=moment,
                retention_state=ConversationRetentionState.ACTIVE,
            )
            draft = MessageDraft(
                conversation_id=conv_id,
                role=role,
                content=content,
                source=source,
                trace_visibility=trace_visibility,
                created_at=moment,
            )
            try:
                stored_conv, stored_msg, stored_pending = (
                    self._conversations.create_with_initial_turn(
                        candidate,
                        draft,
                        msg_id,
                        assistant_msg_id,
                        outbox_event=outbox_intent,
                    )
                )
            except (ConversationAlreadyExistsError, MessageAlreadyExistsError):
                if remaining == 0:
                    raise ConversationStorageError(
                        "Could not allocate a unique conversation or message identity after "
                        f"{MAX_IDENTITY_ATTEMPTS} attempts."
                    ) from None
                continue

            logger.info(
                "conversation.create_with_initial_turn ok conversation_id=%s "
                "message_id=%s assistant_message_id=%s owner_user_id=%s",
                stored_conv.conversation_id,
                stored_msg.message_id,
                stored_pending.message_id,
                stored_conv.owner_user_id,
            )
            return stored_conv, stored_msg, stored_pending

        raise ConversationStorageError(
            "Conversation creation made no storage attempt because the configured "
            "identity attempt budget is not positive."
        )

    def get_conversation(
        self, conversation_id: str, owner_user_id: str
    ) -> Conversation | None:
        """Return one owner-scoped conversation, or None when absent or foreign.

        `owner_user_id` is mandatory: every conversation read is owner-scoped,
        so there is no internal ownerless seam. Foreign conversations read as
        absent to prevent enumeration, and conversations pending deletion,
        deleted, or tombstoned read as absent through normal product paths.

        Raises:
            ConversationValidationError: An identifier is blank.
        """
        identifier = require_text(conversation_id, "conversation_id")
        owner = require_text(owner_user_id, "owner_user_id")
        conversation = self._conversations.get(identifier, owner)
        if conversation is None:
            return None

        retention = (
            conversation.retention_state.value
            if isinstance(conversation.retention_state, ConversationRetentionState)
            else str(conversation.retention_state)
        )
        if retention in _HIDDEN_RETENTION_VALUES:
            return None

        if conversation.owner_user_id != owner:
            return None

        return conversation

    def list_conversations(self, owner_user_id: str) -> tuple[Conversation, ...]:
        """Return directly owned conversations in repository order.

        Ordering is owned by the repository and is not mutated here.

        Raises:
            ConversationValidationError: The owner identifier is blank.
        """
        owner = require_text(owner_user_id, "owner_user_id")
        return tuple(self._conversations.list_by_owner(owner))

    def append_message(
        self,
        conversation_id: str,
        role: MessageRole | str,
        content: str,
        owner_user_id: str,
        source: MessageSource | str | None = None,
        trace_visibility: TraceVisibility | str | None = None,
        outbox_event: OutboxIntent | dict | None = None,
    ) -> Message:
        """Append one message to an existing conversation.

        The service sets `created_at` and generates `message_id`; the repository
        assigns `sequence` inside its write transaction. The public role
        restriction is enforced by the route, not here, because the orchestrator
        writes `assistant` turns through this same method.

        When `owner_user_id` is supplied, the conversation must be owned by that
        user, failing closed with `ConversationNotFoundError` if absent or foreign.

        Two write conflicts are retried exactly once, then fail closed. A
        generated `message_id` collision is retried with a fresh identity. A
        contested turn position is retried too, because the repository re-reads
        the highest `sequence` on every attempt, so one retry re-allocates the
        position rather than reordering or overwriting a turn. Neither conflict
        reaches the route layer after a successful retry.

        Raises:
            ConversationValidationError: The draft violates the message contract.
            ConversationNotFoundError: The parent conversation does not exist or is foreign.
            ConversationStorageError: A conflict persisted through the retry
                budget, or storage failed.
        """
        self._require_conversation_for_owner(conversation_id, owner_user_id)

        outbox_intent = coerce_outbox_intent(outbox_event)

        draft = MessageDraft(
            conversation_id=conversation_id,
            role=role,
            content=content,
            source=source,
            trace_visibility=trace_visibility,
            created_at=utc_now(),
        )

        for remaining in reversed(range(MAX_IDENTITY_ATTEMPTS)):
            try:
                if outbox_intent is not None:
                    stored = self._conversations.append_message(
                        draft,
                        generate_message_id(),
                        owner_user_id,
                        outbox_event=outbox_intent,
                    )
                else:
                    stored = self._conversations.append_message(
                        draft, generate_message_id(), owner_user_id
                    )
            except ConversationGoneError as error:
                # A delete landed after the owner check. The conversation is
                # gone, so report absence rather than a storage failure.
                raise ConversationNotFoundError(
                    "The conversation does not exist."
                ) from error
            except (MessageAlreadyExistsError, MessageSequenceConflictError) as error:
                if remaining == 0:
                    raise ConversationStorageError(
                        "Could not persist the message after "
                        f"{MAX_IDENTITY_ATTEMPTS} attempts because a write "
                        "conflict persisted."
                    ) from error
                logger.info(
                    "conversation.append retry conversation_id=%s failure_class=%s",
                    conversation_id,
                    type(error).__name__,
                )
                continue

            return stored

        raise ConversationStorageError(
            "Message append made no storage attempt because the configured "
            "identity attempt budget is not positive."
        )

    def append_turn(
        self,
        conversation_id: str,
        owner_user_id: str,
        user_content: str,
        assistant_placeholder: str = "",
        outbox_event: OutboxIntent | dict | None = None,
    ) -> tuple[Message, Message]:
        """Open one turn: a user message and a pending assistant row together.

        The repository allocates both sequences and both identities inside one
        transaction under one parent-row lock, so a concurrent turn cannot
        separate the pair (ADR 0023). The assistant row is filled in later by
        `complete_turn`, or recorded by `fail_turn`.

        A generated-identity or sequence collision is retried exactly once, the
        same discipline `append_message` uses.

        Raises:
            ConversationValidationError: The content violates the message contract.
            ConversationNotFoundError: The conversation does not exist or is foreign.
            ConversationStorageError: A conflict persisted through the retry
                budget, or storage failed.
        """
        self._require_conversation_for_owner(conversation_id, owner_user_id)
        outbox_intent = coerce_outbox_intent(outbox_event)

        for remaining in reversed(range(MAX_IDENTITY_ATTEMPTS)):
            try:
                if outbox_intent is not None:
                    return self._conversations.append_turn(
                        conversation_id,
                        owner_user_id,
                        user_content,
                        assistant_placeholder,
                        outbox_event=outbox_intent,
                    )
                return self._conversations.append_turn(
                    conversation_id,
                    owner_user_id,
                    user_content,
                    assistant_placeholder,
                )
            except ConversationGoneError as error:
                # A delete landed after the owner check, so report absence
                # rather than a storage failure.
                raise ConversationNotFoundError(
                    "The conversation does not exist."
                ) from error
            except (MessageAlreadyExistsError, MessageSequenceConflictError) as error:
                if remaining == 0:
                    raise ConversationStorageError(
                        "Could not open the turn after "
                        f"{MAX_IDENTITY_ATTEMPTS} attempts because a write "
                        "conflict persisted."
                    ) from error
                logger.info(
                    "conversation.turn retry conversation_id=%s failure_class=%s",
                    conversation_id,
                    type(error).__name__,
                )
                continue

        raise ConversationStorageError(
            "Turn append made no storage attempt because the configured "
            "identity attempt budget is not positive."
        )

    def complete_turn(
        self,
        conversation_id: str,
        message_id: str,
        owner_user_id: str,
        content: str,
    ) -> TransitionResult:
        """Fill in a pending assistant row with the generated reply.

        Idempotent: a row that is no longer pending is returned unchanged, so a
        retry cannot overwrite a completed turn. Because of that, the result's
        `applied` flag — not the returned row — is what tells a caller whether its
        own reply was stored.

        Raises:
            ConversationValidationError: An identifier is blank.
            ConversationNotFoundError: The conversation is gone.
            ConversationStorageError: Storage failed.
        """
        identifier = require_text(conversation_id, "conversation_id")
        message = require_text(message_id, "message_id")
        owner = require_text(owner_user_id, "owner_user_id")
        try:
            return self._conversations.complete_turn(
                identifier, message, owner, content
            )
        except ConversationGoneError as error:
            raise ConversationNotFoundError(
                "The conversation does not exist."
            ) from error

    def fail_turn(
        self, conversation_id: str, message_id: str, owner_user_id: str
    ) -> TransitionResult:
        """Record that a turn failed generation, storing no content.

        Idempotent, and it never overwrites a completed row.

        Raises:
            ConversationValidationError: An identifier is blank.
            ConversationNotFoundError: The conversation is gone.
            ConversationStorageError: Storage failed.
        """
        identifier = require_text(conversation_id, "conversation_id")
        message = require_text(message_id, "message_id")
        owner = require_text(owner_user_id, "owner_user_id")
        try:
            return self._conversations.fail_turn(identifier, message, owner)
        except ConversationGoneError as error:
            raise ConversationNotFoundError(
                "The conversation does not exist."
            ) from error

    def list_messages(
        self,
        query: MessageHistoryQuery,
        owner_user_id: str,
    ) -> tuple[Message, ...]:
        """Return one page of message history in transcript order.

        The caller's `after_message_id` is resolved to its stored position here,
        so the repository receives `after_sequence` and never interprets an
        identifier. A cursor that does not exist, or that belongs to another
        conversation, is rejected instead of silently returning the whole
        transcript.

        When `owner_user_id` is supplied, the conversation must be owned by that
        user, failing closed with `ConversationNotFoundError` if absent or foreign.

        Raises:
            ConversationValidationError: The query is not a `MessageHistoryQuery`
                or its cursor is invalid.
            ConversationNotFoundError: The conversation does not exist or is foreign.
        """
        if not isinstance(query, MessageHistoryQuery):
            raise ConversationValidationError(
                "list_messages requires a MessageHistoryQuery input."
            )

        self._require_conversation_for_owner(query.conversation_id, owner_user_id)

        after_sequence = self._resolve_cursor(query, owner_user_id)

        return tuple(
            self._conversations.list_messages(
                query.conversation_id, owner_user_id, after_sequence, query.limit
            )
        )

    def get_history(
        self,
        conversation_id: str,
        owner_user_id: str,
        after_message_id: str | None = None,
        limit: int | None = None,
    ) -> tuple[Message, ...]:
        """Return message history for an authenticated owner.

        Raises:
            ConversationNotFoundError: The conversation does not exist or is foreign.
            ConversationValidationError: Input validation failed.
        """
        query = MessageHistoryQuery(
            conversation_id=conversation_id,
            after_message_id=after_message_id,
            limit=limit,
        )
        return self.list_messages(query, owner_user_id=owner_user_id)

    def get_messages_in_range(
        self,
        conversation_id: str,
        owner_user_id: str,
        after_sequence: int | None = None,
        limit: int = 100,
        until_sequence: int | None = None,
    ) -> tuple[Message, ...]:
        """Return owner-scoped messages in a range, in transcript order.

        Direct API for write-pipeline workers and extraction tasks that read
        ranges without building an HTTP cursor query. `owner_user_id` is
        mandatory so the read is tenant-bound like every other path.

        `until_sequence` closes the range from above. A per-turn extraction event
        that read to the end of the conversation attributed later turns to its own
        provenance; the bound keeps each event inside its own turn.
        """
        self._require_conversation_for_owner(conversation_id, owner_user_id)
        return tuple(
            self._conversations.list_messages(
                conversation_id,
                owner_user_id,
                after_sequence,
                limit,
                until_sequence,
            )
        )

    def get_deletion_epoch(self, conversation_id: str, owner_user_id: str) -> int:
        """Return the conversation deletion epoch for worker fencing.

        Reads the stored epoch even after the conversation is tombstoned, so
        a worker holding a stale lease can detect that its event is obsolete.
        """
        identifier = require_text(conversation_id, "conversation_id")
        owner = require_text(owner_user_id, "owner_user_id")
        return self._conversations.get_deletion_epoch(identifier, owner)

    def delete_conversation(
        self,
        conversation_id: str,
        owner_user_id: str,
    ) -> None:
        """Tombstone one owned conversation and remove it from product paths.

        Missing and foreign conversations both raise `ConversationNotFoundError`
        so ownership cannot be enumerated.

        Raises:
            ConversationValidationError: An identifier is blank.
            ConversationNotFoundError: The conversation does not exist or is foreign.
            ConversationStorageError: Storage failed.
        """
        self._require_conversation_for_owner(conversation_id, owner_user_id)
        deleted = self._conversations.delete(conversation_id, owner_user_id)
        if not deleted:
            raise ConversationNotFoundError("The conversation does not exist.")
        logger.info(
            "conversation.delete ok conversation_id=%s owner_user_id=%s",
            conversation_id,
            owner_user_id,
        )

    def _resolve_cursor(
        self, query: MessageHistoryQuery, owner_user_id: str
    ) -> int | None:
        if query.after_message_id is None:
            return None

        cursor = self._conversations.get_message(query.after_message_id, owner_user_id)
        if cursor is None or cursor.conversation_id != query.conversation_id:
            raise ConversationValidationError(
                "The history cursor does not belong to this conversation."
            )
        return cursor.sequence

    def _require_conversation_for_owner(
        self, conversation_id: str, owner_user_id: str
    ) -> Conversation:
        identifier = require_text(conversation_id, "conversation_id")
        owner = require_text(owner_user_id, "owner_user_id")
        conversation = self.get_conversation(identifier, owner)
        if conversation is None:
            raise ConversationNotFoundError("The conversation does not exist.")
        return conversation
