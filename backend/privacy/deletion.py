"""Workspace deletion orchestration for milestone R9.

`DeletionService` coordinates workspace, conversation, and memory
visibility changes with fail-closed ordering rather than one
cross-adapter transaction: the workspace moves to `deletion_requested`
first, which immediately blocks normal product access, and idempotent
child transitions follow. Planner state needs no transition because
hiding is derived from workspace state in the planner service.

A partial child failure leaves the workspace in `deletion_requested`
and propagates a retryable error instead of claiming confirmed
deletion. Confirmation verifies that no active or requested child
records remain before moving the workspace to `deleted`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.conversations.models import ConversationRetentionState
from backend.conversations.service import WorkspaceNotFoundError
from backend.memory.models import MemoryRecordStatus
from backend.workspaces.models import RetentionState

logger = logging.getLogger("travel_agent_privacy")


class PrivacyServiceError(Exception):
    """A privacy operation failed after the fail-closed barrier was set.

    Messages raised as this type are safe for a controlled retryable
    failure: they carry no user content and no storage internals.
    """


class DeletionConflictError(PrivacyServiceError):
    """A deletion confirmation cannot proceed yet.

    Routes map this to a controlled `409` response: confirming an active
    workspace, or leftover child records after a retry, means the caller
    should request or retry rather than assume deletion completed.
    """


@dataclass(frozen=True)
class DeletionResult:
    """One workspace deletion request or confirmation outcome.

    Counts report records that actually changed state in this call, so
    idempotent retries report zeros rather than cumulative totals.
    """

    workspace_id: str
    workspace_state: str
    conversations_updated: int
    memory_updated: int

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_id, str) or not self.workspace_id.strip():
            raise PrivacyServiceError(
                "Deletion result workspace id must be a non-empty string."
            )
        if self.workspace_state not in ("deletion_requested", "deleted"):
            raise PrivacyServiceError(
                "Deletion result state must be a deletion lifecycle value."
            )
        for field_name in ("conversations_updated", "memory_updated"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise PrivacyServiceError(
                    f"Deletion result {field_name} must be a non-negative integer."
                )


class DeletionService:
    """Coordinate workspace deletion across repository adapters."""

    def __init__(
        self,
        workspace_repository,
        conversation_repository,
        memory_repository,
    ) -> None:
        self._workspaces = workspace_repository
        self._conversations = conversation_repository
        self._memory = memory_repository

    def request_workspace_deletion(self, workspace_id: str) -> DeletionResult:
        """Mark a workspace and its active children deletion-requested."""
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError("The parent workspace does not exist.")
        if workspace.retention_state is RetentionState.DELETED:
            return DeletionResult(
                workspace_id=workspace_id,
                workspace_state=RetentionState.DELETED.value,
                conversations_updated=0,
                memory_updated=0,
            )
        stored = self._workspaces.update_retention_state(
            workspace_id, RetentionState.DELETION_REQUESTED
        )
        if stored is None:  # pragma: no cover - raced deletion
            raise WorkspaceNotFoundError("The parent workspace does not exist.")
        try:
            conversations = self._conversations.transition_workspace_conversations(
                workspace_id, ConversationRetentionState.DELETION_REQUESTED
            )
            memory = self._memory.transition_workspace_records(
                workspace_id, MemoryRecordStatus.DELETION_REQUESTED
            )
        except Exception as error:
            logger.error(
                "privacy.deletion request partial workspace_id=%s failure_class=%s",
                workspace_id,
                type(error).__name__,
            )
            raise PrivacyServiceError(
                "Workspace deletion was requested but child transitions did "
                "not complete; normal access stays denied and the request "
                "may be retried."
            ) from error
        logger.info(
            "privacy.deletion requested workspace_id=%s conversations=%s memory=%s",
            workspace_id,
            conversations,
            memory,
        )
        return DeletionResult(
            workspace_id=workspace_id,
            workspace_state=RetentionState.DELETION_REQUESTED.value,
            conversations_updated=conversations,
            memory_updated=memory,
        )

    def confirm_workspace_deletion(self, workspace_id: str) -> DeletionResult:
        """Confirm deletion after verifying child transitions completed."""
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError("The parent workspace does not exist.")
        if workspace.retention_state is RetentionState.DELETED:
            return DeletionResult(
                workspace_id=workspace_id,
                workspace_state=RetentionState.DELETED.value,
                conversations_updated=0,
                memory_updated=0,
            )
        if workspace.retention_state is not RetentionState.DELETION_REQUESTED:
            raise DeletionConflictError(
                "Workspace deletion must be requested before confirmation."
            )
        try:
            conversations = self._conversations.transition_workspace_conversations(
                workspace_id, ConversationRetentionState.DELETED
            )
            memory = self._memory.transition_workspace_records(
                workspace_id, MemoryRecordStatus.DELETED
            )
        except Exception as error:
            logger.error(
                "privacy.deletion confirm partial workspace_id=%s failure_class=%s",
                workspace_id,
                type(error).__name__,
            )
            raise PrivacyServiceError(
                "Workspace deletion confirmation did not complete; the "
                "workspace stays deletion-requested and the confirmation "
                "may be retried."
            ) from error
        leftover_conversations = [
            item
            for item in self._conversations.list_by_workspace(workspace_id)
            if item.retention_state
            in (
                ConversationRetentionState.ACTIVE,
                ConversationRetentionState.DELETION_REQUESTED,
            )
        ]
        leftover_memory = [
            item
            for item in self._memory.list_records(workspace_id=workspace_id)
            if item.status
            in (
                MemoryRecordStatus.ACTIVE,
                MemoryRecordStatus.DELETION_REQUESTED,
            )
        ]
        if leftover_conversations or leftover_memory:
            raise DeletionConflictError(
                "Workspace deletion confirmation found remaining child "
                "records; retry the confirmation."
            )
        stored = self._workspaces.update_retention_state(
            workspace_id, RetentionState.DELETED
        )
        if stored is None:  # pragma: no cover - raced deletion
            raise WorkspaceNotFoundError("The parent workspace does not exist.")
        logger.info(
            "privacy.deletion confirmed workspace_id=%s conversations=%s memory=%s",
            workspace_id,
            conversations,
            memory,
        )
        return DeletionResult(
            workspace_id=workspace_id,
            workspace_state=RetentionState.DELETED.value,
            conversations_updated=conversations,
            memory_updated=memory,
        )


__all__ = [
    "DeletionConflictError",
    "DeletionResult",
    "DeletionService",
    "PrivacyServiceError",
]
