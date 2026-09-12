"""PostgreSQL conversation repository adapter for the authenticated chat path.

Mirrors the repository contract semantics over the clean-break schema:
server-owned identity and ordering, governed vocabulary mapping that fails closed,
deletion/tombstone-hidden reads, and atomic message append with a parent timestamp bump.
Additionally, append accepts an optional outbox event persisted in the same transaction.

Raised `ConversationRepositoryError` messages are safe for a controlled
HTTP 500 response: they never include DSNs, full SQL text, credentials,
or message content.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from datetime import timezone
from typing import Any, Iterator

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    exc as sa_exc,
    func,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

# The fence's refusal vocabulary (ADR 0033). Imported at module level rather than
# lazily: the check functions return it on every refusal, so a lazy import would
# only move the failure to the first fenced write.
from backend.memory.write_pipeline.uow import FenceReason

from backend.conversations.models import (
    Conversation,
    ConversationRetentionState,
    ConversationValidationError,
    Message,
    MessageDraft,
    MessageRole,
    MessageSource,
    MessageStatus,
    OutboxIntent,
    TraceVisibility,
    TransitionResult,
    generate_message_id,
    require_text,
    utc_now,
)
from backend.conversations.repository import (
    ConversationAlreadyExistsError,
    ConversationGoneError,
    ConversationRepositoryError,
    ConversationStorageError,
    MessageAlreadyExistsError,
    MessageSequenceConflictError,
)
from backend.storage.postgres import (
    require_tenant_context,
    set_tenant,
    transaction,
)

logger = logging.getLogger("travel_agent_conversations")


@contextmanager
def tenant_transaction(engine: Engine, owner_user_id: str) -> Iterator[Any]:
    """Yield one tenant-bound transaction for an owner-scoped operation.

    Binds `app.tenant` and verifies the binding before yielding, so every
    repository read and write runs under row-level security for the same
    owner the application predicate checks.
    """
    with transaction(engine) as connection:
        set_tenant(connection, owner_user_id)
        require_tenant_context(connection)
        yield connection


metadata = MetaData()

conversations_table = Table(
    "conversations",
    metadata,
    Column("conversation_id", Text(), primary_key=True),
    Column("owner_user_id", Text(), nullable=False),
    Column("title", Text(), nullable=True),
    Column("retention_state", Text(), nullable=False),
    Column("deletion_epoch", Integer(), nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("idx_conversations_owner", "owner_user_id"),
    Index("idx_conversations_owner_created_at", "owner_user_id", "created_at"),
    Index("idx_conversations_id_owner", "conversation_id", "owner_user_id"),
)

messages_table = Table(
    "messages",
    metadata,
    Column("message_id", Text(), primary_key=True),
    Column(
        "conversation_id",
        Text(),
        ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("sequence", Integer(), nullable=False),
    Column("role", Text(), nullable=False),
    Column("content", Text(), nullable=False),
    Column("source", Text(), nullable=False),
    Column("trace_visibility", Text(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("status", Text(), nullable=False, server_default="complete"),
    UniqueConstraint("conversation_id", "sequence"),
    Index("idx_messages_conversation", "conversation_id", "sequence"),
)

conversation_outbox_table = Table(
    "conversation_outbox",
    metadata,
    Column("outbox_id", Text(), primary_key=True),
    Column(
        "conversation_id",
        Text(),
        ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("message_id", Text(), nullable=False),
    Column("owner_user_id", Text(), nullable=False),
    Column("event_type", Text(), nullable=False),
    Column("payload", JSONB(), nullable=False),
    Column("status", Text(), nullable=False, server_default="pending"),
    Column("attempt_count", Integer(), nullable=False, server_default="0"),
    Column("lease_owner", Text(), nullable=True),
    Column("lease_until", DateTime(timezone=True), nullable=True),
    Column("last_error", Text(), nullable=True),
    Column("next_attempt_after", DateTime(timezone=True), nullable=True),
    # ADR 0027 release gate. NULL means blocked: the event is owed but its turn is
    # not finished. Non-NULL means released. Deliberately a separate fact from
    # `status`, which records only where the event sits in its retry lifecycle.
    Column("released_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Index("idx_conversation_outbox_conversation", "conversation_id"),
    Index("idx_conversation_outbox_ready", "status", "released_at"),
)

memory_evidence_table = Table(
    "memory_evidence",
    metadata,
    Column("evidence_id", Text(), primary_key=True),
    Column("conversation_id", Text(), nullable=False),
    Column("invalidated_at", DateTime(timezone=True), nullable=True),
)

_DELETION_STATES = (
    ConversationRetentionState.DELETED.value,
    ConversationRetentionState.DELETION_REQUESTED.value,
    ConversationRetentionState.TOMBSTONED.value,
)

_OUTBOX_ID_PREFIX = "cout_"


def _require_vocabulary(value: Any, column: str, enum_type: type) -> Any:
    try:
        return enum_type(value)
    except ValueError as error:
        raise ConversationStorageError(
            f"Stored conversation column '{column}' is outside the governed vocabulary."
        ) from error


class PostgresConversationRepository:
    """Persist standalone conversations and messages in PostgreSQL."""

    def __init__(self, engine: Engine) -> None:
        """Bind to an existing engine; schema comes from Alembic, not here."""
        self._engine = engine

    def create(self, conversation: Conversation) -> Conversation:
        """Persist a new conversation and return it."""
        retention_val = (
            conversation.retention_state.value
            if isinstance(conversation.retention_state, ConversationRetentionState)
            else str(conversation.retention_state)
        )
        try:
            with tenant_transaction(
                self._engine, conversation.owner_user_id
            ) as connection:
                connection.execute(
                    conversations_table.insert().values(
                        conversation_id=conversation.conversation_id,
                        owner_user_id=conversation.owner_user_id,
                        title=conversation.title,
                        retention_state=retention_val,
                        created_at=conversation.created_at,
                        updated_at=conversation.updated_at,
                    )
                )
        except sa_exc.IntegrityError as error:
            raise ConversationAlreadyExistsError(
                "A conversation with this identity already exists."
            ) from error
        except sa_exc.SQLAlchemyError as error:
            raise ConversationStorageError(
                "Could not persist the conversation record."
            ) from error
        return conversation

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
        outbox event commit in one transaction, so turn-1 auto-creation cannot
        leave an orphaned conversation, a user message with no reply slot, or a
        live extraction event over an unanswered range (ADR 0023).
        """
        retention_val = (
            conversation.retention_state.value
            if isinstance(conversation.retention_state, ConversationRetentionState)
            else str(conversation.retention_state)
        )
        event_type, payload = self._coerce_outbox_event(outbox_event)
        try:
            with tenant_transaction(
                self._engine, conversation.owner_user_id
            ) as connection:
                connection.execute(
                    conversations_table.insert().values(
                        conversation_id=conversation.conversation_id,
                        owner_user_id=conversation.owner_user_id,
                        title=conversation.title,
                        retention_state=retention_val,
                        created_at=conversation.created_at,
                        updated_at=conversation.updated_at,
                    )
                )
                connection.execute(
                    messages_table.insert().values(
                        message_id=message_id,
                        conversation_id=conversation.conversation_id,
                        sequence=1,
                        role=message.role.value,
                        content=message.content,
                        source=message.source.value,
                        trace_visibility=message.trace_visibility.value,
                        created_at=message.created_at,
                        status=MessageStatus.COMPLETE.value,
                    )
                )
                connection.execute(
                    messages_table.insert().values(
                        message_id=assistant_message_id,
                        conversation_id=conversation.conversation_id,
                        sequence=2,
                        role=MessageRole.ASSISTANT.value,
                        content="",
                        source=MessageSource.MODEL.value,
                        trace_visibility=TraceVisibility.EXCLUDED.value,
                        created_at=message.created_at,
                        status=MessageStatus.PENDING.value,
                    )
                )
                if event_type is not None:
                    stored_payload = dict(payload)
                    stored_payload.setdefault("deletion_epoch", 0)
                    stored_payload["conversation_id"] = conversation.conversation_id
                    # Bound the worker's read to this turn, both ends. The
                    # repository owns sequence allocation, so it owns the cursor:
                    # this turn's user message sits at sequence 1 and its
                    # assistant row at sequence 2. Without the upper bound the
                    # event would read every later turn and attribute it here.
                    stored_payload["after_sequence"] = 0
                    stored_payload["until_sequence"] = 2
                    connection.execute(
                        conversation_outbox_table.insert().values(
                            outbox_id=f"{_OUTBOX_ID_PREFIX}{uuid.uuid4().hex}",
                            conversation_id=conversation.conversation_id,
                            message_id=message_id,
                            owner_user_id=conversation.owner_user_id,
                            event_type=event_type,
                            payload=stored_payload,
                            status="pending",
                            attempt_count=0,
                            # ADR 0027: blocked until complete_turn releases it.
                            released_at=None,
                            created_at=message.created_at,
                            updated_at=message.created_at,
                        )
                    )
        except sa_exc.IntegrityError as error:
            raise self._classify_integrity_error(error) from error
        except sa_exc.SQLAlchemyError as error:
            raise ConversationStorageError(
                "Could not atomically persist the conversation and its first turn."
            ) from error

        return (
            conversation,
            Message(
                message_id=message_id,
                conversation_id=conversation.conversation_id,
                sequence=1,
                role=message.role,
                content=message.content,
                source=message.source,
                trace_visibility=message.trace_visibility,
                created_at=message.created_at,
                status=MessageStatus.COMPLETE,
            ),
            Message(
                message_id=assistant_message_id,
                conversation_id=conversation.conversation_id,
                sequence=2,
                role=MessageRole.ASSISTANT,
                content="",
                source=MessageSource.MODEL,
                trace_visibility=TraceVisibility.EXCLUDED,
                created_at=message.created_at,
                status=MessageStatus.PENDING,
            ),
        )

    def get(self, conversation_id: str, owner_user_id: str) -> Conversation | None:
        """Return the stored owner-scoped conversation, or None when absent.

        The tenant marker is bound before the read, so the row-level-security
        policy filters on the same owner the application predicate checks.
        """
        try:
            with tenant_transaction(self._engine, owner_user_id) as connection:
                row = (
                    connection.execute(
                        select(conversations_table).where(
                            conversations_table.c.conversation_id == conversation_id
                        )
                    )
                    .mappings()
                    .fetchone()
                )
        except sa_exc.SQLAlchemyError as error:
            raise ConversationStorageError(
                "Could not read the conversation record."
            ) from error
        return None if row is None else self._row_to_conversation(row)

    def list_by_owner(
        self, owner_user_id: str, include_deletion: bool = False
    ) -> tuple[Conversation, ...]:
        """Return directly owned conversations in governed order."""
        statement = select(conversations_table).where(
            conversations_table.c.owner_user_id == owner_user_id
        )
        if not include_deletion:
            statement = statement.where(
                conversations_table.c.retention_state.not_in(_DELETION_STATES)
            )
        statement = statement.order_by(
            conversations_table.c.created_at.desc(),
            conversations_table.c.conversation_id.asc(),
        )
        try:
            with tenant_transaction(self._engine, owner_user_id) as connection:
                rows = connection.execute(statement).mappings().fetchall()
        except sa_exc.SQLAlchemyError as error:
            raise ConversationStorageError(
                "Could not list conversation records."
            ) from error
        return tuple(self._row_to_conversation(row) for row in rows)

    def delete(self, conversation_id: str, owner_user_id: str) -> bool:
        """Tombstone one conversation and propagate the deletion atomically.

        The tombstone, the outbox cancellation, the memory-evidence
        invalidation, and the deletion-epoch bump run in one owner-scoped
        transaction, so a deleted conversation cannot leave pending or
        leased extraction events, live evidence rows, or a stale epoch
        behind. Background extraction writes shadow evidence only and never
        creates active versions, so invalidation plus fencing is the complete
        propagation on this path: there are no versions to suspend and no
        projections to rebuild.
        """
        try:
            with tenant_transaction(self._engine, owner_user_id) as connection:
                result = connection.execute(
                    conversations_table.update()
                    .where(conversations_table.c.conversation_id == conversation_id)
                    .where(
                        conversations_table.c.retention_state
                        != ConversationRetentionState.TOMBSTONED.value
                    )
                    .values(
                        retention_state=ConversationRetentionState.TOMBSTONED.value,
                        updated_at=utc_now(),
                        deletion_epoch=conversations_table.c.deletion_epoch + 1,
                    )
                )
                if result.rowcount == 0:
                    return False
                deleted_at = utc_now()
                connection.execute(
                    conversation_outbox_table.update()
                    .where(
                        conversation_outbox_table.c.conversation_id == conversation_id
                    )
                    .where(
                        conversation_outbox_table.c.status.in_(("pending", "leased"))
                    )
                    .values(
                        status="cancelled",
                        lease_owner=None,
                        lease_until=None,
                        last_error="conversation_deleted",
                        updated_at=deleted_at,
                    )
                )
                connection.execute(
                    memory_evidence_table.update()
                    .where(memory_evidence_table.c.conversation_id == conversation_id)
                    .where(memory_evidence_table.c.invalidated_at.is_(None))
                    .values(invalidated_at=deleted_at)
                )
                return True
        except sa_exc.SQLAlchemyError as error:
            raise ConversationStorageError(
                "Could not tombstone the conversation record."
            ) from error

    def get_deletion_epoch(self, conversation_id: str, owner_user_id: str) -> int:
        """Return the conversation deletion epoch, reading tombstoned rows too.

        Workers compare this against the epoch captured when their outbox
        event was written; a higher stored value fences a stale lease.
        """
        try:
            with tenant_transaction(self._engine, owner_user_id) as connection:
                value = connection.execute(
                    select(conversations_table.c.deletion_epoch).where(
                        conversations_table.c.conversation_id == conversation_id
                    )
                ).scalar_one_or_none()
        except sa_exc.SQLAlchemyError as error:
            raise ConversationStorageError(
                "Could not read the conversation deletion epoch."
            ) from error
        return int(value) if value is not None else 0

    def append_message(
        self,
        message: MessageDraft,
        message_id: str,
        owner_user_id: str,
        outbox_event: OutboxIntent | dict | None = None,
    ) -> Message:
        """Persist one owner-scoped message, allocating position and bumping parent.

        The sequence allocation, parent bump, message insert, and optional
        outbox insert run in one transaction behind a parent row lock, so a
        failing insert leaves neither the position nor the parent timestamp
        mutated. The tenant marker is bound first so row-level security
        enforces the same owner scope as the application predicate.
        """
        event_type, payload = self._coerce_outbox_event(outbox_event)
        try:
            with tenant_transaction(self._engine, owner_user_id) as connection:
                parent = (
                    connection.execute(
                        select(conversations_table)
                        .where(
                            conversations_table.c.conversation_id
                            == message.conversation_id
                        )
                        .with_for_update()
                    )
                    .mappings()
                    .fetchone()
                )
                if parent is None:
                    raise ConversationGoneError(
                        "Parent conversation was missing while appending a message."
                    )
                parent_retention = (
                    parent["retention_state"]
                    if "retention_state" in parent.keys()
                    else ConversationRetentionState.ACTIVE.value
                )
                if parent_retention != ConversationRetentionState.ACTIVE.value:
                    # A delete landed after the service-level check. Fail
                    # closed under the parent lock instead of writing into a
                    # tombstoned conversation.
                    raise ConversationGoneError(
                        "Parent conversation is no longer active."
                    )

                highest_sequence = connection.execute(
                    select(messages_table.c.sequence)
                    .where(messages_table.c.conversation_id == message.conversation_id)
                    .order_by(messages_table.c.sequence.desc())
                    .limit(1)
                ).scalar_one_or_none()
                sequence = 1 if highest_sequence is None else highest_sequence + 1

                connection.execute(
                    conversations_table.update()
                    .where(
                        conversations_table.c.conversation_id == message.conversation_id
                    )
                    .values(updated_at=message.created_at)
                )
                connection.execute(
                    messages_table.insert().values(
                        message_id=message_id,
                        conversation_id=message.conversation_id,
                        sequence=sequence,
                        role=message.role.value,
                        content=message.content,
                        source=message.source.value,
                        trace_visibility=message.trace_visibility.value,
                        created_at=message.created_at,
                    )
                )
                if event_type is not None:
                    # Stamp the fencing epoch captured from the locked parent row,
                    # so a worker holding this event can detect a later tombstone.
                    stored_payload = dict(payload)
                    parent_epoch = (
                        parent["deletion_epoch"]
                        if "deletion_epoch" in parent.keys()
                        else 0
                    )
                    stored_payload.setdefault("deletion_epoch", int(parent_epoch or 0))
                    connection.execute(
                        conversation_outbox_table.insert().values(
                            outbox_id=f"{_OUTBOX_ID_PREFIX}{uuid.uuid4().hex}",
                            conversation_id=message.conversation_id,
                            message_id=message_id,
                            owner_user_id=parent["owner_user_id"],
                            event_type=event_type,
                            payload=stored_payload,
                            status="pending",
                            attempt_count=0,
                            # This path inserts an already-terminal message, so
                            # there is no pending turn to wait for: the event is
                            # released at insert and today's behaviour is kept.
                            released_at=message.created_at,
                            created_at=message.created_at,
                            updated_at=message.created_at,
                        )
                    )
        except (
            ConversationStorageError,
            MessageAlreadyExistsError,
            MessageSequenceConflictError,
        ):
            raise
        except sa_exc.IntegrityError as error:
            raise self._classify_integrity_error(error) from error
        except sa_exc.SQLAlchemyError as error:
            raise ConversationStorageError(
                "Could not persist the message record."
            ) from error

        logger.info(
            "conversation.message appended conversation_id=%s message_id=%s "
            "sequence=%s role=%s",
            message.conversation_id,
            message_id,
            sequence,
            message.role.value,
        )
        return Message(
            message_id=message_id,
            conversation_id=message.conversation_id,
            sequence=sequence,
            role=message.role,
            content=message.content,
            source=message.source,
            trace_visibility=message.trace_visibility,
            created_at=message.created_at,
        )

    @staticmethod
    def _require_active_conversation(
        connection: Any, conversation_id: str, owner_user_id: str
    ) -> Any:
        """Lock the parent row and fail closed unless it is still active.

        Taken `FOR UPDATE` so a concurrent delete cannot commit between this
        check and the caller's write: whichever transaction takes the row lock
        first wins, and the loser observes the committed tombstone. The owner
        predicate repeats what row-level security already enforces, so a foreign
        conversation fails as `ConversationGoneError` rather than as a silently
        empty update.
        """
        parent = (
            connection.execute(
                select(conversations_table)
                .where(
                    conversations_table.c.conversation_id == conversation_id,
                    conversations_table.c.owner_user_id == owner_user_id,
                )
                .with_for_update()
            )
            .mappings()
            .fetchone()
        )
        if parent is None:
            raise ConversationGoneError(
                "Parent conversation was missing or not owned by this caller."
            )
        if parent["retention_state"] != ConversationRetentionState.ACTIVE.value:
            raise ConversationGoneError("Parent conversation is no longer active.")
        return parent

    def append_turn(
        self,
        conversation_id: str,
        owner_user_id: str,
        user_content: str,
        assistant_placeholder: str = "",
        outbox_event: OutboxIntent | dict | None = None,
    ) -> tuple[Message, Message]:
        """Allocate one turn in a single transaction under one parent-row lock.

        The user message, the pending assistant row and the outbox event commit
        together, and both sequences are allocated together, so turn adjacency
        holds under concurrent turns (ADR 0023). Identity is generated here
        rather than passed in, because the two identities and the two sequences
        must be allocated in the same transaction to stay correlated.
        """
        normalized_content = require_text(user_content, "content")
        event_type, payload = self._coerce_outbox_event(outbox_event)
        created_at = utc_now()
        user_message_id = generate_message_id()
        assistant_message_id = generate_message_id()
        try:
            with tenant_transaction(self._engine, owner_user_id) as connection:
                parent = self._require_active_conversation(
                    connection, conversation_id, owner_user_id
                )
                highest_sequence = connection.execute(
                    select(messages_table.c.sequence)
                    .where(messages_table.c.conversation_id == conversation_id)
                    .order_by(messages_table.c.sequence.desc())
                    .limit(1)
                ).scalar_one_or_none()
                base = 1 if highest_sequence is None else highest_sequence + 1

                connection.execute(
                    conversations_table.update()
                    .where(conversations_table.c.conversation_id == conversation_id)
                    .values(updated_at=created_at)
                )
                connection.execute(
                    messages_table.insert().values(
                        message_id=user_message_id,
                        conversation_id=conversation_id,
                        sequence=base,
                        role=MessageRole.USER.value,
                        content=normalized_content,
                        source=MessageSource.UI.value,
                        trace_visibility=TraceVisibility.EXCLUDED.value,
                        created_at=created_at,
                        status=MessageStatus.COMPLETE.value,
                    )
                )
                connection.execute(
                    messages_table.insert().values(
                        message_id=assistant_message_id,
                        conversation_id=conversation_id,
                        sequence=base + 1,
                        role=MessageRole.ASSISTANT.value,
                        content=assistant_placeholder,
                        source=MessageSource.MODEL.value,
                        trace_visibility=TraceVisibility.EXCLUDED.value,
                        created_at=created_at,
                        status=MessageStatus.PENDING.value,
                    )
                )
                if event_type is not None:
                    # Stamp the fencing epoch read from the locked parent row, so
                    # a worker holding this event can detect a later tombstone.
                    stored_payload = dict(payload)
                    stored_payload.setdefault(
                        "deletion_epoch", int(parent["deletion_epoch"] or 0)
                    )
                    # Bound the worker's read to this turn, both ends. The
                    # repository owns sequence allocation, so it owns the cursor and
                    # overwrites any caller-supplied value: a stale cursor would
                    # silently re-extract an older range. This turn's user message
                    # sits at `base` and its assistant row at `base + 1`, so the
                    # upper bound keeps the event inside its own turn instead of
                    # reading every later one.
                    stored_payload["after_sequence"] = base - 1
                    stored_payload["until_sequence"] = base + 1
                    connection.execute(
                        conversation_outbox_table.insert().values(
                            outbox_id=f"{_OUTBOX_ID_PREFIX}{uuid.uuid4().hex}",
                            conversation_id=conversation_id,
                            message_id=user_message_id,
                            owner_user_id=owner_user_id,
                            event_type=event_type,
                            payload=stored_payload,
                            status="pending",
                            attempt_count=0,
                            # ADR 0027: blocked until complete_turn releases it.
                            released_at=None,
                            created_at=created_at,
                            updated_at=created_at,
                        )
                    )
        except (
            ConversationGoneError,
            ConversationStorageError,
            MessageAlreadyExistsError,
            MessageSequenceConflictError,
        ):
            raise
        except sa_exc.IntegrityError as error:
            raise self._classify_integrity_error(error) from error
        except sa_exc.SQLAlchemyError as error:
            raise ConversationStorageError(
                "Could not persist the conversation turn."
            ) from error

        return (
            Message(
                message_id=user_message_id,
                conversation_id=conversation_id,
                sequence=base,
                role=MessageRole.USER,
                content=normalized_content,
                source=MessageSource.UI,
                trace_visibility=TraceVisibility.EXCLUDED,
                created_at=created_at,
                status=MessageStatus.COMPLETE,
            ),
            Message(
                message_id=assistant_message_id,
                conversation_id=conversation_id,
                sequence=base + 1,
                role=MessageRole.ASSISTANT,
                content=assistant_placeholder,
                source=MessageSource.MODEL,
                trace_visibility=TraceVisibility.EXCLUDED,
                created_at=created_at,
                status=MessageStatus.PENDING,
            ),
        )

    def complete_turn(
        self,
        conversation_id: str,
        message_id: str,
        owner_user_id: str,
        content: str,
    ) -> TransitionResult:
        """Fill in a pending assistant row. Idempotent, and fails closed.

        Returns `TransitionResult`, so a caller can tell whether it wrote this
        reply or merely observed one another writer had already stored.
        """
        return self._transition_turn(
            conversation_id,
            message_id,
            owner_user_id,
            status=MessageStatus.COMPLETE,
            content=require_text(content, "content"),
        )

    def fail_turn(
        self, conversation_id: str, message_id: str, owner_user_id: str
    ) -> TransitionResult:
        """Mark a pending assistant row failed. Idempotent.

        Never overwrites a completed row. The row is emptied, so a failed turn
        cannot carry a partial reply or a provider error string (ADR 0023).
        """
        return self._transition_turn(
            conversation_id,
            message_id,
            owner_user_id,
            status=MessageStatus.FAILED,
            content="",
        )

    def _transition_turn(
        self,
        conversation_id: str,
        message_id: str,
        owner_user_id: str,
        *,
        status: MessageStatus,
        content: str,
    ) -> TransitionResult:
        """Single-row turn transition, guarded by `status = 'pending'`.

        The guard is what makes a duplicate call a no-op instead of a
        corruption: `complete_turn` racing `fail_turn` cannot produce a row with
        content and `status = 'failed'`, nor empty content and
        `status = 'complete'`. Whichever commits first wins.
        """
        try:
            with tenant_transaction(self._engine, owner_user_id) as connection:
                self._require_active_conversation(
                    connection, conversation_id, owner_user_id
                )
                updated = (
                    connection.execute(
                        messages_table.update()
                        .where(
                            messages_table.c.message_id == message_id,
                            messages_table.c.conversation_id == conversation_id,
                            messages_table.c.status == MessageStatus.PENDING.value,
                        )
                        .values(content=content, status=status.value)
                        .returning(*messages_table.c)
                    )
                    .mappings()
                    .fetchone()
                )
                if updated is not None:
                    transitioned = self._row_to_message(updated)
                    applied = True
                else:
                    # Already completed or failed: return the stored row
                    # unchanged rather than overwriting it.
                    stored = (
                        connection.execute(
                            select(messages_table).where(
                                messages_table.c.message_id == message_id,
                                messages_table.c.conversation_id == conversation_id,
                            )
                        )
                        .mappings()
                        .fetchone()
                    )
                    if stored is None:
                        raise ConversationGoneError(
                            "The assistant message does not exist in this "
                            "conversation."
                        )
                    transitioned = self._row_to_message(stored)
                    # Another writer moved this row first. The row is returned
                    # unchanged, so it is the caller's only signal that the reply
                    # it generated was *not* stored.
                    applied = False

                if transitioned.status is MessageStatus.COMPLETE:
                    # ADR 0027: the turn is terminal, so its extraction event may
                    # now be claimed. Released in the same transaction as the
                    # status change, so "complete" and "released" cannot diverge.
                    self._release_turn_outbox(
                        connection, conversation_id, transitioned
                    )

                if transitioned.status is MessageStatus.FAILED:
                    self._cancel_turn_outbox(
                        connection, conversation_id, transitioned
                    )
                return TransitionResult(message=transitioned, applied=applied)
        except (ConversationGoneError, ConversationStorageError):
            raise
        except sa_exc.SQLAlchemyError as error:
            raise ConversationStorageError(
                "Could not transition the conversation turn."
            ) from error

    @staticmethod
    def _preceding_user_message_id(
        connection: Any, conversation_id: str, assistant_row: Message
    ) -> str | None:
        """Return the user message id immediately preceding an assistant row.

        The outbox row is keyed on the message that triggered it — the user
        message — while the row that becomes terminal is the assistant row. The
        correlation is positional, and both the release and the cancel depend on
        it, so it lives in one place rather than being restated at each site.
        """
        return connection.execute(
            select(messages_table.c.message_id).where(
                messages_table.c.conversation_id == conversation_id,
                messages_table.c.sequence == assistant_row.sequence - 1,
                messages_table.c.role == MessageRole.USER.value,
            )
        ).scalar_one_or_none()

    @staticmethod
    def _release_turn_outbox(
        connection: Any, conversation_id: str, assistant_row: Message
    ) -> None:
        """Open the release gate on this turn's extraction event (ADR 0027).

        Runs in the same transaction as the completion it belongs to, so a
        completed turn is always claimable and an unfinished turn never is. The
        `released_at IS NULL` guard makes a repeat call a no-op rather than a
        timestamp move, which keeps a second `complete_turn` idempotent.
        """
        user_message_id = PostgresConversationRepository._preceding_user_message_id(
            connection, conversation_id, assistant_row
        )
        if user_message_id is None:
            return
        connection.execute(
            conversation_outbox_table.update()
            .where(
                conversation_outbox_table.c.conversation_id == conversation_id,
                conversation_outbox_table.c.message_id == user_message_id,
                conversation_outbox_table.c.released_at.is_(None),
            )
            .values(released_at=utc_now())
        )

    @staticmethod
    def _cancel_turn_outbox(
        connection: Any, conversation_id: str, assistant_row: Message
    ) -> None:
        """Cancel the extraction event written with this turn, in the same
        transaction as the failure.

        A turn that produced no reply must not cause extraction over an
        unanswered range (ADR 0023). Because the event is blocked until its turn
        is released (ADR 0027), a worker can never have claimed it at this point,
        so this match always finds the row it is looking for.
        """
        user_message_id = PostgresConversationRepository._preceding_user_message_id(
            connection, conversation_id, assistant_row
        )
        if user_message_id is None:
            return
        connection.execute(
            conversation_outbox_table.update()
            .where(
                conversation_outbox_table.c.conversation_id == conversation_id,
                conversation_outbox_table.c.message_id == user_message_id,
                conversation_outbox_table.c.status == "pending",
            )
            .values(status="cancelled", updated_at=utc_now())
        )

    @staticmethod
    def _coerce_outbox_event(
        event: OutboxIntent | dict | None,
    ) -> tuple[str | None, dict]:
        if event is None:
            return None, {}
        if isinstance(event, OutboxIntent):
            return event.event_type, dict(event.payload)
        if not isinstance(event, dict):
            raise ConversationStorageError(
                "A message outbox event must be an OutboxIntent or mapping."
            )
        event_type = event.get("event_type")
        if not isinstance(event_type, str) or not event_type.strip():
            raise ConversationStorageError("A message outbox event requires a type.")
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            raise ConversationStorageError(
                "A message outbox event payload must be a mapping."
            )
        return event_type.strip(), dict(payload)

    @staticmethod
    def _classify_integrity_error(error: sa_exc.IntegrityError):
        """Map a unique-constraint violation to its contract error.

        The violated constraint comes from the driver diagnostic when
        available, falling back to the detail text. Neither carries
        stored content into the raised message.
        """
        name = ""
        diagnostic = getattr(getattr(error, "orig", None), "diag", None)
        if diagnostic is not None:
            name = getattr(diagnostic, "constraint_name", "") or ""
        if not name:
            name = str(error)
        if "messages_conversation_id_sequence_key" in name or (
            "messages" in name and "sequence" in name
        ):
            return MessageSequenceConflictError(
                "This conversation turn position is already taken."
            )
        return MessageAlreadyExistsError("A message with this identity already exists.")

    def get_message(self, message_id: str, owner_user_id: str) -> Message | None:
        """Return the stored owner-scoped message, or None when absent."""
        try:
            with tenant_transaction(self._engine, owner_user_id) as connection:
                row = (
                    connection.execute(
                        select(messages_table).where(
                            messages_table.c.message_id == message_id
                        )
                    )
                    .mappings()
                    .fetchone()
                )
        except sa_exc.SQLAlchemyError as error:
            raise ConversationStorageError(
                "Could not read the message record."
            ) from error
        return None if row is None else self._row_to_message(row)

    def list_messages(
        self,
        conversation_id: str,
        owner_user_id: str,
        after_sequence: int | None,
        limit: int,
        until_sequence: int | None = None,
    ) -> tuple[Message, ...]:
        """Return up to `limit` owner-scoped messages in an inclusive range.

        `until_sequence` bounds the read from above. A per-turn extraction event
        that read to the end of the conversation attributed later turns to its own
        provenance; the bound keeps each event's read inside its own turn.
        """
        try:
            with tenant_transaction(self._engine, owner_user_id) as connection:
                statement = (
                    select(messages_table)
                    .where(messages_table.c.conversation_id == conversation_id)
                    .where(
                        messages_table.c.sequence
                        > (0 if after_sequence is None else after_sequence)
                    )
                )
                if until_sequence is not None:
                    statement = statement.where(
                        messages_table.c.sequence <= until_sequence
                    )
                rows = (
                    connection.execute(
                        statement.order_by(messages_table.c.sequence.asc()).limit(limit)
                    )
                    .mappings()
                    .fetchall()
                )
        except sa_exc.SQLAlchemyError as error:
            raise ConversationStorageError("Could not list message records.") from error
        return tuple(self._row_to_message(row) for row in rows)

    def _row_to_conversation(self, row) -> Conversation:
        """Map one stored conversation row to its contract, failing closed."""
        retention = _require_vocabulary(
            row["retention_state"], "retention_state", ConversationRetentionState
        )
        try:
            return Conversation(
                conversation_id=row["conversation_id"],
                owner_user_id=row["owner_user_id"],
                title=row["title"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                retention_state=retention,
                deletion_epoch=int(row["deletion_epoch"]),
            )
        except ConversationValidationError as error:
            raise ConversationStorageError(
                "Stored conversation record violates the conversation contract."
            ) from error

    def _row_to_message(self, row) -> Message:
        """Map one stored message row to its contract, failing closed."""
        resolved_role = _require_vocabulary(row["role"], "role", MessageRole)
        resolved_source = _require_vocabulary(row["source"], "source", MessageSource)
        resolved_visibility = _require_vocabulary(
            row["trace_visibility"], "trace_visibility", TraceVisibility
        )
        resolved_status = _require_vocabulary(row["status"], "status", MessageStatus)
        try:
            return Message(
                message_id=row["message_id"],
                conversation_id=row["conversation_id"],
                sequence=row["sequence"],
                role=resolved_role,
                content=row["content"],
                source=resolved_source,
                trace_visibility=resolved_visibility,
                created_at=row["created_at"],
                status=resolved_status,
            )
        except ConversationValidationError as error:
            raise ConversationStorageError(
                "Stored message record violates the message contract."
            ) from error


def check_conversation_fence(
    connection: Any,
    conversation_id: str,
    expected_epoch: int,
    owner_user_id: str | None = None,
) -> tuple[bool, "FenceReason | None"]:
    """Verify conversation status and deletion epoch on a given connection.

    Returns (is_valid, reason). Encapsulates conversation domain tables.

    The reason is typed (ADR 0033), because a caller's next decision — whether to
    cancel the conversation's other outbox events — depends on *which* of the
    three causes applied, and a caller cannot branch on a sentence.

    The parent row is locked (`FOR UPDATE`) so a concurrent delete cannot
    commit between this check and the caller's subsequent writes: whichever
    transaction holds the row lock first wins, and the loser observes the
    committed tombstone/epoch. When `owner_user_id` is given, the row must
    additionally belong to that owner.
    """
    statement = select(
        conversations_table.c.retention_state,
        conversations_table.c.deletion_epoch,
    ).where(conversations_table.c.conversation_id == conversation_id)
    if owner_user_id is not None:
        statement = statement.where(
            conversations_table.c.owner_user_id == owner_user_id
        )
    row = connection.execute(statement.with_for_update()).mappings().fetchone()
    if row is None:
        return False, FenceReason.CONVERSATION_GONE
    if row["retention_state"] != "active":
        return False, FenceReason.CONVERSATION_NOT_ACTIVE
    stored_epoch = row["deletion_epoch"]
    stored_epoch = int(stored_epoch) if stored_epoch is not None else 0
    if stored_epoch != expected_epoch:
        return False, FenceReason.DELETION_EPOCH_MOVED
    return True, None


def check_outbox_lease(
    connection: Any,
    outbox_id: str,
    lease_owner: str,
) -> tuple[bool, "FenceReason | None"]:
    """Verify outbox event lease on a given connection.

    Returns (is_valid, reason). Encapsulates outbox domain tables.

    Checks the lease *window* as well as the holder. Comparing the holder alone
    proved identity but not current authority: a worker whose lease had already
    expired — but whose event had not yet been re-claimed — still passed this
    fence and wrote Memory.

    The window is judged here, against `now()`, rather than by a timestamp the
    caller supplies. Accepting a caller's `now` closed the first half of the hole
    and left the second: the party being judged chose the clock. A worker that
    captured its timestamp before an unbounded model call reported an expired
    lease as held, and the fence agreed (ADR 0032). `now()` is the transaction
    timestamp, so the check and the write it guards observe one instant.

    The three refusals are distinct reasons (ADR 0033): a lease that was lost and
    a lease that merely expired call for different responses, and an event whose
    row has vanished is a third case again.
    """
    lease_held = or_(
        conversation_outbox_table.c.lease_until.is_(None),
        conversation_outbox_table.c.lease_until >= func.now(),
    ).label("lease_held")

    row = (
        connection.execute(
            select(
                conversation_outbox_table.c.status,
                conversation_outbox_table.c.lease_owner,
                lease_held,
            )
            .where(conversation_outbox_table.c.outbox_id == outbox_id)
            .with_for_update()
        )
        .mappings()
        .fetchone()
    )
    if row is None:
        return False, FenceReason.OUTBOX_EVENT_GONE
    if row["status"] != "leased" or row["lease_owner"] != lease_owner:
        return False, FenceReason.LEASE_LOST
    if not row["lease_held"]:
        return False, FenceReason.LEASE_EXPIRED
    return True, None
