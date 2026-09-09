"""Conversation use cases for runtime milestone R4.

The service owns validation, identity generation, timestamping, existence
checks, and cursor resolution. It depends on the conversation contracts, the
conversation repository interface, and the workspace repository interface only.

The workspace interface is imported under `TYPE_CHECKING` on purpose. The
service needs the interface's shape, not the concrete SQLite adapter that the
workspace package re-exports, so keeping the import out of the runtime graph
makes the one-way boundary between conversations and workspaces verifiable
rather than merely documented.

`WorkspaceNotFoundError` and `ConversationNotFoundError` exist so the route layer
can map a missing parent to `404` without inspecting storage details.

Message content passes through this module and is never logged.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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
    coerce_outbox_intent,
    generate_conversation_id,
    generate_message_id,
    require_text,
    utc_now,
)
from backend.conversations.repository import (
    ConversationAlreadyExistsError,
    ConversationRepository,
    ConversationStorageError,
    MessageAlreadyExistsError,
    MessageSequenceConflictError,
)

# Workspace retention values hidden from normal product paths. Kept as
# plain strings (rather than importing workspace contracts) so importing
# this module never executes the workspace package init behind the R4
# import boundary.
_DELETION_HIDDEN_RETENTION_VALUES = frozenset({"deletion_requested", "deleted"})

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from backend.workspaces.repository import WorkspaceRepository

logger = logging.getLogger("travel_agent_conversations")

MAX_IDENTITY_ATTEMPTS = 2
"""One initial attempt plus exactly one retry on a generated-identity collision."""


class ConversationNotFoundError(Exception):
    """The referenced conversation does not exist."""


class WorkspaceNotFoundError(Exception):
    """The referenced parent workspace does not exist."""


class ConversationService:
    """Create and inspect conversation records behind approved contracts."""

    def __init__(
        self,
        conversation_repository: ConversationRepository,
        workspace_repository: "WorkspaceRepository",
    ) -> None:
        self._conversations = conversation_repository
        self._workspaces = workspace_repository

    def create_conversation(
        self, conversation_input: ConversationCreate
    ) -> Conversation:
        """Create one standalone or workspace-bound conversation.

        `ConversationCreate` has already normalized and validated its fields, so
        invalid input raises before this method is reached and no storage write
        occurs. A `None` workspace means a standalone conversation owned
        directly by `owner_user_id`; no hidden or default workspace is
        created and the workspace repository is not consulted. A present
        workspace must exist and be owned by the same owner, otherwise the
        request is rejected without disclosing which foreign id exists.

        A generated-identity collision is retried exactly once with a fresh
        identity. A second collision raises `ConversationStorageError` rather
        than leaving a partial write or looping.

        Raises:
            ConversationValidationError: The input is not a `ConversationCreate`.
            WorkspaceNotFoundError: The parent workspace does not exist or
                does not belong to the requesting owner.
            ConversationStorageError: Identity generation collided twice or
                storage failed.
        """
        if not isinstance(conversation_input, ConversationCreate):
            raise ConversationValidationError(
                "create_conversation requires a ConversationCreate input."
            )

        if conversation_input.workspace_id is not None:
            self._require_workspace_for_owner(
                conversation_input.workspace_id, conversation_input.owner_user_id
            )

        moment = utc_now()
        for remaining in reversed(range(MAX_IDENTITY_ATTEMPTS)):
            candidate = Conversation(
                conversation_id=generate_conversation_id(),
                owner_user_id=conversation_input.owner_user_id,
                workspace_id=conversation_input.workspace_id,
                title=conversation_input.title,
                created_at=moment,
                updated_at=moment,
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
                "conversation.create ok conversation_id=%s workspace_id=%s",
                created.conversation_id,
                created.workspace_id,
            )
            return created

        raise ConversationStorageError(
            "Conversation creation made no storage attempt because the configured "
            "identity attempt budget is not positive."
        )

    def get_workspace_owner_id(self, workspace_id: str) -> str | None:
        """Return the workspace owner label, or None when absent.

        Read-only helper for route-boundary authorization: it performs no
        scope check itself and never creates storage.
        """
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            return None
        return workspace.owner_user_id

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        """Return one conversation by identifier, or None when absent.

        Conversations pending or under deletion read as absent through
        normal product paths; coordination reads them through the
        repository.

        Raises:
            ConversationValidationError: The identifier is blank.
        """
        conversation = self._conversations.get(
            require_text(conversation_id, "conversation_id")
        )
        if conversation is None:
            return None
        if conversation.retention_state in (
            ConversationRetentionState.DELETION_REQUESTED,
            ConversationRetentionState.DELETED,
        ):
            return None
        return conversation

    def get_workspace(self, workspace_id: str):
        """Return the parent workspace record, or None when absent.

        Read-only helper for route-boundary authorization: it performs no
        scope check itself and never creates storage.
        """
        return self._workspaces.get(workspace_id)

    def list_conversations(self, workspace_id: str) -> tuple[Conversation, ...]:
        """Return conversations for one workspace in repository order.

        Ordering is owned by the repository and is not mutated here.

        Raises:
            ConversationValidationError: The workspace identifier is blank.
            WorkspaceNotFoundError: The parent workspace does not exist.
        """
        scope = require_text(workspace_id, "workspace_id")
        self._require_workspace(scope)
        return tuple(self._conversations.list_by_workspace(scope))

    def list_conversations_by_owner(
        self, owner_user_id: str
    ) -> tuple[Conversation, ...]:
        """Return directly owned conversations in repository order.

        Includes standalone conversations with no workspace. Ordering is
        owned by the repository and is not mutated here.

        Raises:
            ConversationValidationError: The owner identifier is blank.
        """
        owner = require_text(owner_user_id, "owner_user_id")
        return tuple(self._conversations.list_by_owner(owner))

    def get_conversation_for_owner(
        self, conversation_id: str, owner_user_id: str
    ) -> Conversation | None:
        """Return one owned conversation, or None when absent or foreign.

        Foreign, missing, and deletion-hidden conversations all read as
        absent so ownership cannot be enumerated. No message content is
        carried in any error.

        Raises:
            ConversationValidationError: An identifier is blank.
        """
        identifier = require_text(conversation_id, "conversation_id")
        owner = require_text(owner_user_id, "owner_user_id")
        conversation = self.get_conversation(identifier)
        if conversation is None:
            return None
        if conversation.owner_user_id != owner:
            return None
        return conversation

    def append_message(
        self,
        conversation_id: str,
        role: MessageRole | str,
        content: str,
        source: MessageSource | str | None = None,
        trace_visibility: TraceVisibility | str | None = None,
        outbox_event: OutboxIntent | dict | None = None,
    ) -> Message:
        """Append one message to an existing conversation.

        The service sets `created_at` and generates `message_id`; the repository
        assigns `sequence` inside its write transaction. The public role
        restriction is enforced by the route, not here, because the orchestrator
        writes `assistant` turns through this same method.

        Two write conflicts are retried exactly once, then fail closed. A
        generated `message_id` collision is retried with a fresh identity. A
        contested turn position is retried too, because the repository re-reads
        the highest `sequence` on every attempt, so one retry re-allocates the
        position rather than reordering or overwriting a turn. Neither conflict
        reaches the route layer after a successful retry.

        Raises:
            ConversationValidationError: The draft violates the message contract.
            ConversationNotFoundError: The parent conversation does not exist.
            ConversationStorageError: A conflict persisted through the retry
                budget, or storage failed.
        """
        self._require_conversation(conversation_id)
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
                        draft, generate_message_id(), outbox_event=outbox_intent
                    )
                else:
                    stored = self._conversations.append_message(
                        draft, generate_message_id()
                    )
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

    def list_messages(self, query: MessageHistoryQuery) -> tuple[Message, ...]:
        """Return one page of message history in transcript order.

        The caller's `after_message_id` is resolved to its stored position here,
        so the repository receives `after_sequence` and never interprets an
        identifier. A cursor that does not exist, or that belongs to another
        conversation, is rejected instead of silently returning the whole
        transcript.

        Raises:
            ConversationValidationError: The query is not a `MessageHistoryQuery`
                or its cursor is invalid.
            ConversationNotFoundError: The conversation does not exist.
        """
        if not isinstance(query, MessageHistoryQuery):
            raise ConversationValidationError(
                "list_messages requires a MessageHistoryQuery input."
            )

        self._require_conversation(query.conversation_id)
        after_sequence = self._resolve_cursor(query)

        return tuple(
            self._conversations.list_messages(
                query.conversation_id, after_sequence, query.limit
            )
        )

    def get_messages_in_range(
        self,
        conversation_id: str,
        after_sequence: int | None = None,
        limit: int = 100,
    ) -> tuple[Message, ...]:
        """Return messages in a conversation after sequence in transcript order.

        Direct API for write-pipeline workers and extraction tasks that read ranges
        without building an HTTP cursor query.
        """
        self._require_conversation(conversation_id)
        return tuple(
            self._conversations.list_messages(
                conversation_id, after_sequence, limit
            )
        )

    def _resolve_cursor(self, query: MessageHistoryQuery) -> int | None:
        if query.after_message_id is None:
            return None

        cursor = self._conversations.get_message(query.after_message_id)
        if cursor is None or cursor.conversation_id != query.conversation_id:
            raise ConversationValidationError(
                "The history cursor does not belong to this conversation."
            )
        return cursor.sequence

    def _is_deletion_hidden_workspace(self, workspace_id: str) -> bool:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            return False
        return workspace.retention_state.value in _DELETION_HIDDEN_RETENTION_VALUES

    def _require_workspace(self, workspace_id: str) -> None:
        if self._workspaces.get(workspace_id) is None:
            raise WorkspaceNotFoundError("The parent workspace does not exist.")
        if self._is_deletion_hidden_workspace(workspace_id):
            raise WorkspaceNotFoundError("The parent workspace does not exist.")

    def _require_workspace_for_owner(
        self, workspace_id: str, owner_user_id: str
    ) -> None:
        """Require an existing workspace owned by the requesting owner.

        Missing, deletion-hidden, and foreign workspaces all raise the same
        controlled `WorkspaceNotFoundError` so ownership cannot be
        enumerated. No workspace content is carried in the error.
        """
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError("The parent workspace does not exist.")
        if workspace.retention_state.value in _DELETION_HIDDEN_RETENTION_VALUES:
            raise WorkspaceNotFoundError("The parent workspace does not exist.")
        if workspace.owner_user_id != owner_user_id:
            raise WorkspaceNotFoundError("The parent workspace does not exist.")

    def _require_conversation(self, conversation_id: str) -> None:
        identifier = require_text(conversation_id, "conversation_id")
        if self.get_conversation(identifier) is None:
            raise ConversationNotFoundError("The conversation does not exist.")
