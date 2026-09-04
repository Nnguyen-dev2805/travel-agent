"""Local SQLite conversation repository adapter for runtime milestone R4.

Per ADR 0004 this adapter and the workspace adapter share one local database
file and record independent schema versions through the shared registry. The
caller supplies that file path; the setting that resolves it is named only in
`backend/app/config.py` and at the dependency construction sites, so this module
stays free of configuration knowledge. Per ADR 0003 SQLite remains a local
development adapter behind the repository boundary; it is not a production
database commitment, and it settles no production migration, backup, restore,
concurrency, retention, or deletion policy.

Two properties are load-bearing:

1. **A turn position is a stored fact.** `sequence` is allocated inside one
   `BEGIN IMMEDIATE` transaction that also bumps the parent conversation's
   `updated_at`, so later provenance never has to infer order from timestamps.
   The bump is applied before the insert, so a failing insert rolls it back.
2. **A stored row that violates the contract fails closed.** Row mapping never
   coerces an unknown vocabulary value or an untyped timestamp into something
   plausible.

Raised `ConversationRepositoryError` messages are safe for a controlled HTTP 500
response: they never include the local database path, full SQL text, or message
content.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.conversations.models import (
    Conversation,
    ConversationRetentionState,
    ConversationValidationError,
    Message,
    MessageDraft,
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
from backend.storage.schema_registry import (
    SchemaRegistryError,
    open_application_database,
    register_module_schema,
)

logger = logging.getLogger("travel_agent_conversations")

SCHEMA_VERSION = 1
SCHEMA_MODULE = "conversations"
CONVERSATION_TABLE = "conversations"
MESSAGE_TABLE = "messages"

_CREATE_CONVERSATION_TABLE = f"""
CREATE TABLE IF NOT EXISTS {CONVERSATION_TABLE} (
    conversation_id TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL,
    title           TEXT,
    retention_state TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
)
"""

_CREATE_CONVERSATION_INDEX = f"""
CREATE INDEX IF NOT EXISTS idx_{CONVERSATION_TABLE}_workspace
ON {CONVERSATION_TABLE} (
    workspace_id, updated_at DESC, created_at DESC, conversation_id ASC
)
"""

_CREATE_MESSAGE_TABLE = f"""
CREATE TABLE IF NOT EXISTS {MESSAGE_TABLE} (
    message_id       TEXT PRIMARY KEY,
    conversation_id  TEXT NOT NULL,
    sequence         INTEGER NOT NULL,
    role             TEXT NOT NULL,
    content          TEXT NOT NULL,
    source           TEXT NOT NULL,
    trace_visibility TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    UNIQUE (conversation_id, sequence)
)
"""

_CREATE_MESSAGE_INDEX = f"""
CREATE INDEX IF NOT EXISTS idx_{MESSAGE_TABLE}_conversation
ON {MESSAGE_TABLE} (conversation_id, sequence ASC)
"""

_INSERT_CONVERSATION = f"""
INSERT INTO {CONVERSATION_TABLE} (
    conversation_id, workspace_id, title, retention_state, created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?)
"""

_CONVERSATION_COLUMNS = """
    conversation_id, workspace_id, title, retention_state, created_at, updated_at
"""

_SELECT_CONVERSATION_BY_ID = (
    f"SELECT {_CONVERSATION_COLUMNS} FROM {CONVERSATION_TABLE} "
    "WHERE conversation_id = ?"
)

# Listing excludes `deleted` records. R4 creates only `active` records, so this
# filter has no effect today; it keeps a future deletion milestone from
# surfacing removed records through the list route.
_SELECT_CONVERSATIONS_BY_WORKSPACE = f"""
SELECT {_CONVERSATION_COLUMNS} FROM {CONVERSATION_TABLE}
WHERE workspace_id = ? AND retention_state != ?
ORDER BY updated_at DESC, created_at DESC, conversation_id ASC
"""

_BUMP_CONVERSATION = (
    f"UPDATE {CONVERSATION_TABLE} SET updated_at = ? WHERE conversation_id = ?"
)

_MAX_SEQUENCE = f"SELECT MAX(sequence) FROM {MESSAGE_TABLE} WHERE conversation_id = ?"

_INSERT_MESSAGE = f"""
INSERT INTO {MESSAGE_TABLE} (
    message_id, conversation_id, sequence, role, content,
    source, trace_visibility, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

_MESSAGE_COLUMNS = """
    message_id, conversation_id, sequence, role, content,
    source, trace_visibility, created_at
"""

_SELECT_MESSAGE_BY_ID = (
    f"SELECT {_MESSAGE_COLUMNS} FROM {MESSAGE_TABLE} WHERE message_id = ?"
)

_SELECT_MESSAGES = f"""
SELECT {_MESSAGE_COLUMNS} FROM {MESSAGE_TABLE}
WHERE conversation_id = ? AND sequence > ?
ORDER BY sequence ASC
LIMIT ?
"""


def _to_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _from_iso(value: Any, column: str) -> datetime:
    if not isinstance(value, str):
        raise ConversationStorageError(
            f"Stored conversation column '{column}' is not a timestamp string."
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ConversationStorageError(
            f"Stored conversation column '{column}' is not a valid ISO timestamp."
        ) from error
    if parsed.tzinfo is None:
        raise ConversationStorageError(
            f"Stored conversation column '{column}' is missing timezone information."
        )
    return parsed.astimezone(timezone.utc)


def _require_vocabulary(value: Any, column: str, enum_type: type) -> Any:
    try:
        return enum_type(value)
    except ValueError as error:
        raise ConversationStorageError(
            f"Stored conversation column '{column}' is outside the governed vocabulary."
        ) from error


def _create_conversation_schema(connection: sqlite3.Connection) -> None:
    """Create both conversation tables and both indexes on first registration."""
    connection.execute(_CREATE_CONVERSATION_TABLE)
    connection.execute(_CREATE_CONVERSATION_INDEX)
    connection.execute(_CREATE_MESSAGE_TABLE)
    connection.execute(_CREATE_MESSAGE_INDEX)


class SQLiteConversationRepository:
    """Persist conversation and message records in the shared local database."""

    def __init__(self, db_path: Path) -> None:
        """Open or initialize conversation storage in the shared database.

        Raises:
            ConversationStorageError: The parent directory cannot be created, the
                database cannot be opened, the file is not owned by a build this
                one recognizes, or the recorded conversation schema version is
                incompatible with `SCHEMA_VERSION`.
        """
        self._db_path = Path(db_path)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        try:
            connection = open_application_database(self._db_path)
        except SchemaRegistryError as error:
            logger.error(
                "conversation.storage unavailable module=%s failure_class=%s",
                SCHEMA_MODULE,
                type(error).__name__,
            )
            raise ConversationStorageError(
                "Could not open the local application database for conversation "
                "storage."
            ) from error

        try:
            register_module_schema(
                connection, SCHEMA_MODULE, SCHEMA_VERSION, _create_conversation_schema
            )
        except SchemaRegistryError as error:
            logger.error(
                "conversation.storage schema_incompatible module=%s supported=%s",
                SCHEMA_MODULE,
                SCHEMA_VERSION,
            )
            raise ConversationStorageError(
                "The local application database does not provide conversation "
                f"schema version {SCHEMA_VERSION}. Refusing to migrate "
                "automatically."
            ) from error
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        try:
            return sqlite3.connect(self._db_path)
        except sqlite3.Error as error:
            raise ConversationStorageError(
                "Could not open the local conversation database."
            ) from error

    def create(self, conversation: Conversation) -> Conversation:
        """Persist a new conversation record and return it."""
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    _INSERT_CONVERSATION,
                    (
                        conversation.conversation_id,
                        conversation.workspace_id,
                        conversation.title,
                        conversation.retention_state.value,
                        _to_iso(conversation.created_at),
                        _to_iso(conversation.updated_at),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise ConversationAlreadyExistsError(
                "A conversation with this identity already exists."
            ) from error
        except sqlite3.Error as error:
            raise ConversationStorageError(
                "Could not persist the conversation record."
            ) from error
        finally:
            connection.close()

        return conversation

    def get(self, conversation_id: str) -> Conversation | None:
        """Return the stored conversation, or None when no record exists."""
        connection = self._connect()
        try:
            row = connection.execute(
                _SELECT_CONVERSATION_BY_ID, (conversation_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise ConversationStorageError(
                "Could not read the conversation record."
            ) from error
        finally:
            connection.close()

        return None if row is None else self._row_to_conversation(row)

    def list_by_workspace(self, workspace_id: str) -> tuple[Conversation, ...]:
        """Return workspace-scoped conversations in governed order."""
        connection = self._connect()
        try:
            rows = connection.execute(
                _SELECT_CONVERSATIONS_BY_WORKSPACE,
                (workspace_id, ConversationRetentionState.DELETED.value),
            ).fetchall()
        except sqlite3.Error as error:
            raise ConversationStorageError(
                "Could not list conversation records."
            ) from error
        finally:
            connection.close()

        return tuple(self._row_to_conversation(row) for row in rows)

    def _allocate_next_sequence(
        self, connection: sqlite3.Connection, conversation_id: str
    ) -> int:
        """Return the next turn position for one conversation.

        Called inside the `BEGIN IMMEDIATE` transaction that performs the write,
        so the read and the insert cannot interleave with another writer on this
        local database.
        """
        highest = connection.execute(_MAX_SEQUENCE, (conversation_id,)).fetchone()[0]
        return 1 if highest is None else int(highest) + 1

    def append_message(self, message: MessageDraft, message_id: str) -> Message:
        """Persist one message, allocating its position and bumping the parent."""
        if message.created_at is None:  # pragma: no cover - contract guarantees this
            raise ConversationStorageError(
                "A message draft must carry a server-assigned timestamp."
            )

        created_at = _to_iso(message.created_at)
        connection = self._connect()
        connection.isolation_level = None
        try:
            connection.execute("BEGIN IMMEDIATE")
            sequence = self._allocate_next_sequence(connection, message.conversation_id)
            connection.execute(
                _BUMP_CONVERSATION, (created_at, message.conversation_id)
            )
            connection.execute(
                _INSERT_MESSAGE,
                (
                    message_id,
                    message.conversation_id,
                    sequence,
                    message.role.value,
                    message.content,
                    message.source.value,
                    message.trace_visibility.value,
                    created_at,
                ),
            )
            connection.execute("COMMIT")
        except sqlite3.IntegrityError as error:
            self._rollback(connection)
            raise self._classify_integrity_error(error) from error
        except sqlite3.Error as error:
            self._rollback(connection)
            raise ConversationStorageError(
                "Could not persist the message record."
            ) from error
        finally:
            connection.close()

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
    def _rollback(connection: sqlite3.Connection) -> None:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:  # pragma: no cover - nothing left to roll back
            pass

    @staticmethod
    def _classify_integrity_error(error: sqlite3.IntegrityError):
        """Map a unique-constraint violation to its contract error.

        SQLite reports the violated constraint only inside the exception text, so
        the constraint is identified by the column names it names. Neither the
        text nor any path or content is carried into the raised message.
        """
        detail = str(error)
        if "sequence" in detail:
            return MessageSequenceConflictError(
                "This conversation turn position is already taken."
            )
        return MessageAlreadyExistsError("A message with this identity already exists.")

    def get_message(self, message_id: str) -> Message | None:
        """Return the stored message, or None when no record exists."""
        connection = self._connect()
        try:
            row = connection.execute(_SELECT_MESSAGE_BY_ID, (message_id,)).fetchone()
        except sqlite3.Error as error:
            raise ConversationStorageError(
                "Could not read the message record."
            ) from error
        finally:
            connection.close()

        return None if row is None else self._row_to_message(row)

    def list_messages(
        self, conversation_id: str, after_sequence: int | None, limit: int
    ) -> tuple[Message, ...]:
        """Return up to `limit` messages after a position, oldest first."""
        connection = self._connect()
        try:
            rows = connection.execute(
                _SELECT_MESSAGES,
                (
                    conversation_id,
                    0 if after_sequence is None else after_sequence,
                    limit,
                ),
            ).fetchall()
        except sqlite3.Error as error:
            raise ConversationStorageError("Could not list message records.") from error
        finally:
            connection.close()

        return tuple(self._row_to_message(row) for row in rows)

    def _row_to_conversation(self, row: tuple[Any, ...]) -> Conversation:
        """Map one stored conversation row to its contract, failing closed."""
        (
            conversation_id,
            workspace_id,
            title,
            retention_state,
            created_at,
            updated_at,
        ) = row

        retention = _require_vocabulary(
            retention_state, "retention_state", ConversationRetentionState
        )

        try:
            return Conversation(
                conversation_id=conversation_id,
                workspace_id=workspace_id,
                title=title,
                created_at=_from_iso(created_at, "created_at"),
                updated_at=_from_iso(updated_at, "updated_at"),
                retention_state=retention,
            )
        except ConversationValidationError as error:
            raise ConversationStorageError(
                "Stored conversation record violates the conversation contract."
            ) from error

    def _row_to_message(self, row: tuple[Any, ...]) -> Message:
        """Map one stored message row to its contract, failing closed."""
        (
            message_id,
            conversation_id,
            sequence,
            role,
            content,
            source,
            trace_visibility,
            created_at,
        ) = row

        resolved_role = _require_vocabulary(role, "role", MessageRole)
        resolved_source = _require_vocabulary(source, "source", MessageSource)
        resolved_visibility = _require_vocabulary(
            trace_visibility, "trace_visibility", TraceVisibility
        )

        try:
            return Message(
                message_id=message_id,
                conversation_id=conversation_id,
                sequence=sequence,
                role=resolved_role,
                content=content,
                source=resolved_source,
                trace_visibility=resolved_visibility,
                created_at=_from_iso(created_at, "created_at"),
            )
        except ConversationValidationError as error:
            raise ConversationStorageError(
                "Stored message record violates the message contract."
            ) from error
