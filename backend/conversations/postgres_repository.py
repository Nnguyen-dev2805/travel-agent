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
from typing import Any

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
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from backend.conversations.models import (
    Conversation,
    ConversationRetentionState,
    ConversationValidationError,
    Message,
    MessageDraft,
    MessageRole,
    MessageSource,
    OutboxIntent,
    TraceVisibility,
    utc_now,
)
from backend.conversations.repository import (
    ConversationAlreadyExistsError,
    ConversationRepositoryError,
    ConversationStorageError,
    MessageAlreadyExistsError,
    MessageSequenceConflictError,
)

logger = logging.getLogger("travel_agent_conversations")

metadata = MetaData()

conversations_table = Table(
    "conversations",
    metadata,
    Column("conversation_id", Text(), primary_key=True),
    Column("owner_user_id", Text(), nullable=False),
    Column("title", Text(), nullable=True),
    Column("retention_state", Text(), nullable=False),
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
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Index("idx_conversation_outbox_conversation", "conversation_id"),
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
            with self._engine.begin() as connection:
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

    def get(self, conversation_id: str) -> Conversation | None:
        """Return the stored conversation, or None when no record exists."""
        try:
            with self._engine.connect() as connection:
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
            with self._engine.connect() as connection:
                rows = connection.execute(statement).mappings().fetchall()
        except sa_exc.SQLAlchemyError as error:
            raise ConversationStorageError(
                "Could not list conversation records."
            ) from error
        return tuple(self._row_to_conversation(row) for row in rows)

    def delete(self, conversation_id: str) -> bool:
        """Mark a conversation as tombstoned."""
        try:
            with self._engine.begin() as connection:
                result = connection.execute(
                    conversations_table.update()
                    .where(conversations_table.c.conversation_id == conversation_id)
                    .where(
                        conversations_table.c.retention_state != ConversationRetentionState.TOMBSTONED.value
                    )
                    .values(
                        retention_state=ConversationRetentionState.TOMBSTONED.value,
                        updated_at=utc_now(),
                    )
                )
                return result.rowcount > 0
        except sa_exc.SQLAlchemyError as error:
            raise ConversationStorageError(
                "Could not tombstone the conversation record."
            ) from error

    def append_message(
        self,
        message: MessageDraft,
        message_id: str,
        outbox_event: OutboxIntent | dict | None = None,
    ) -> Message:
        """Persist one message, allocating its position and bumping the parent.

        The sequence allocation, parent bump, message insert, and optional
        outbox insert run in one transaction behind a parent row lock, so a
        failing insert leaves neither the position nor the parent timestamp
        mutated.
        """
        event_type, payload = self._coerce_outbox_event(outbox_event)
        try:
            with self._engine.begin() as connection:
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
                    raise ConversationStorageError(
                        "Parent conversation was missing or deleted while appending a message."
                    )

                highest_sequence = connection.execute(
                    select(messages_table.c.sequence)
                    .where(
                        messages_table.c.conversation_id == message.conversation_id
                    )
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
                    connection.execute(
                        conversation_outbox_table.insert().values(
                            outbox_id=f"{_OUTBOX_ID_PREFIX}{uuid.uuid4().hex}",
                            conversation_id=message.conversation_id,
                            message_id=message_id,
                            owner_user_id=parent["owner_user_id"],
                            event_type=event_type,
                            payload=payload,
                            status="pending",
                            attempt_count=0,
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

    def get_message(self, message_id: str) -> Message | None:
        """Return the stored message, or None when no record exists."""
        try:
            with self._engine.connect() as connection:
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
        self, conversation_id: str, after_sequence: int | None, limit: int
    ) -> tuple[Message, ...]:
        """Return up to `limit` messages after a position, oldest first."""
        try:
            with self._engine.connect() as connection:
                rows = (
                    connection.execute(
                        select(messages_table)
                        .where(messages_table.c.conversation_id == conversation_id)
                        .where(
                            messages_table.c.sequence
                            > (0 if after_sequence is None else after_sequence)
                        )
                        .order_by(messages_table.c.sequence.asc())
                        .limit(limit)
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
            )
        except ConversationValidationError as error:
            raise ConversationStorageError(
                "Stored message record violates the message contract."
            ) from error
