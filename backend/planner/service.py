"""Planner use cases for milestone R7.

The service owns workspace scope validation, lifecycle decisions, and
operation evidence. Every successful state-changing method writes one
append-only operation row; validation failures write nothing. SQL and
schema details stay in the repository adapter. This module never imports
RAG, memory, orchestration, FastAPI, or provider clients.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from backend.conversations.service import (
    ConversationNotFoundError,
    WorkspaceNotFoundError,
)
from backend.planner.models import (
    DecisionStatus,
    DecisionType,
    ItineraryStatus,
    ItineraryVersion,
    ItineraryVersionDraft,
    PlannerOperation,
    PlannerOperationStatus,
    PlannerOperationType,
    TripDecision,
    generate_itinerary_version_id,
    generate_operation_id,
    require_text,
)
from backend.planner.repository import PlannerRepository

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from backend.conversations.repository import ConversationRepository
    from backend.workspaces.repository import WorkspaceRepository

logger = logging.getLogger("travel_agent_planner")

_CREATABLE_ITINERARY_STATUSES = frozenset(
    {ItineraryStatus.DRAFT, ItineraryStatus.PROPOSED}
)
_ARCHIVABLE_ITINERARY_STATUSES = frozenset(
    {
        ItineraryStatus.DRAFT,
        ItineraryStatus.PROPOSED,
        ItineraryStatus.SUPERSEDED,
    }
)
_ACCEPTABLE_ITINERARY_STATUSES = frozenset(
    {ItineraryStatus.DRAFT, ItineraryStatus.PROPOSED, ItineraryStatus.ACCEPTED}
)
_CREATABLE_DECISION_STATUSES = frozenset(
    {DecisionStatus.PENDING, DecisionStatus.ACCEPTED, DecisionStatus.REJECTED}
)
_DECISION_TRANSITIONS = {
    DecisionStatus.PENDING: frozenset(
        {
            DecisionStatus.ACCEPTED,
            DecisionStatus.REJECTED,
            DecisionStatus.CHANGED,
        }
    ),
    DecisionStatus.ACCEPTED: frozenset({DecisionStatus.CHANGED}),
    DecisionStatus.REJECTED: frozenset({DecisionStatus.CHANGED}),
    DecisionStatus.CHANGED: frozenset(),
    DecisionStatus.SUPERSEDED: frozenset(),
}


class PlannerServiceError(Exception):
    """Base class for planner service failures."""


class PlannerConflictError(PlannerServiceError):
    """A planner write violates a lifecycle rule.

    Routes map this to a controlled HTTP 409 response.
    """


class PlannerScopeMismatchError(PlannerServiceError):
    """Planner provenance does not belong to the addressed workspace.

    Routes map this to a controlled HTTP 404 response so errors never leak
    whether an identifier exists elsewhere.
    """


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PlannerService:
    """Workspace-scoped planner use cases with operation evidence."""

    def __init__(
        self,
        planner_repository: PlannerRepository,
        workspace_repository: WorkspaceRepository,
        conversation_repository: ConversationRepository,
    ) -> None:
        self._planner = planner_repository
        self._workspaces = workspace_repository
        self._conversations = conversation_repository

    def create_itinerary_version(
        self,
        workspace_id: str,
        draft: ItineraryVersionDraft,
        conversation_id: Optional[str] = None,
        source_message_id: Optional[str] = None,
    ) -> ItineraryVersion:
        """Persist an itinerary draft with its create operation atomically.

        The version row and the operation row commit in one repository
        transaction: when the operation write fails, no version survives,
        so the service never reports a failure for a plan it saved.
        """
        import dataclasses

        workspace_id = require_text(workspace_id, "workspace_id")
        self._require_scope(workspace_id, conversation_id)
        if draft.workspace_id != workspace_id:
            raise PlannerScopeMismatchError(
                "The itinerary draft does not belong to this workspace."
            )
        if draft.status not in _CREATABLE_ITINERARY_STATUSES:
            raise PlannerConflictError(
                "An itinerary version can only be created as draft or proposed."
            )
        moment = _utc_now()
        stamped = dataclasses.replace(
            draft,
            created_from_message_id=(
                source_message_id
                if source_message_id is not None
                else draft.created_from_message_id
            ),
            created_at=draft.created_at or moment,
        )
        version_id = generate_itinerary_version_id()
        stored = self._planner.create_itinerary_version(
            stamped,
            version_id,
            operation=self._build_operation(
                workspace_id=workspace_id,
                conversation_id=conversation_id,
                operation_type=PlannerOperationType.CREATE_ITINERARY,
                source_message_id=source_message_id,
                result_itinerary_version_id=version_id,
                input_summary=f"status={stamped.status.value}",
                created_at=moment,
            ),
        )
        logger.info(
            "planner.itinerary created workspace_id=%s version_number=%s",
            workspace_id,
            stored.version_number,
        )
        return stored

    def get_itinerary_version(
        self, workspace_id: str, itinerary_version_id: str
    ) -> ItineraryVersion:
        """Return one itinerary version scoped to the workspace."""
        workspace_id = require_text(workspace_id, "workspace_id")
        itinerary_version_id = require_text(
            itinerary_version_id, "itinerary_version_id"
        )
        self._require_workspace(workspace_id)
        return self._planner.get_itinerary_version(workspace_id, itinerary_version_id)

    def list_itinerary_versions(
        self, workspace_id: str, status: Optional[ItineraryStatus] = None
    ) -> tuple[ItineraryVersion, ...]:
        """Return workspace itinerary versions newest first."""
        workspace_id = require_text(workspace_id, "workspace_id")
        self._require_workspace(workspace_id)
        return self._planner.list_itinerary_versions(workspace_id, status)

    def accept_itinerary_version(
        self, workspace_id: str, itinerary_version_id: str
    ) -> ItineraryVersion:
        """Accept one version with its accept operation atomically."""
        workspace_id = require_text(workspace_id, "workspace_id")
        itinerary_version_id = require_text(
            itinerary_version_id, "itinerary_version_id"
        )
        self._require_workspace(workspace_id)
        current = self._planner.get_itinerary_version(
            workspace_id, itinerary_version_id
        )
        if current.status not in _ACCEPTABLE_ITINERARY_STATUSES:
            raise PlannerConflictError(
                f"An itinerary version with status '{current.status.value}' "
                "cannot be accepted."
            )
        if current.status is ItineraryStatus.ACCEPTED:
            return current
        moment = _utc_now()
        stored = self._planner.accept_itinerary_version(
            workspace_id,
            itinerary_version_id,
            operation=self._build_operation(
                workspace_id=workspace_id,
                conversation_id=None,
                operation_type=PlannerOperationType.ACCEPT_ITINERARY,
                source_message_id=None,
                result_itinerary_version_id=itinerary_version_id,
                input_summary="status=accepted",
                created_at=moment,
            ),
        )
        logger.info(
            "planner.itinerary accepted workspace_id=%s version_number=%s",
            workspace_id,
            stored.version_number,
        )
        return stored

    def archive_itinerary_version(
        self, workspace_id: str, itinerary_version_id: str
    ) -> ItineraryVersion:
        """Archive one version with its archive operation atomically."""
        workspace_id = require_text(workspace_id, "workspace_id")
        itinerary_version_id = require_text(
            itinerary_version_id, "itinerary_version_id"
        )
        self._require_workspace(workspace_id)
        current = self._planner.get_itinerary_version(
            workspace_id, itinerary_version_id
        )
        if current.status not in _ARCHIVABLE_ITINERARY_STATUSES:
            raise PlannerConflictError(
                f"An itinerary version with status '{current.status.value}' "
                "cannot be archived."
            )
        moment = _utc_now()
        stored = self._planner.update_itinerary_status(
            workspace_id,
            itinerary_version_id,
            ItineraryStatus.ARCHIVED,
            operation=self._build_operation(
                workspace_id=workspace_id,
                conversation_id=None,
                operation_type=PlannerOperationType.ARCHIVE_ITINERARY,
                source_message_id=None,
                result_itinerary_version_id=itinerary_version_id,
                input_summary="status=archived",
                created_at=moment,
            ),
        )
        logger.info(
            "planner.itinerary archived workspace_id=%s version_number=%s",
            workspace_id,
            stored.version_number,
        )
        return stored

    def record_decision(
        self,
        workspace_id: str,
        draft: TripDecision,
        conversation_id: Optional[str] = None,
        source_message_id: Optional[str] = None,
    ) -> TripDecision:
        """Persist a decision and log the record or supersede operation."""
        workspace_id = require_text(workspace_id, "workspace_id")
        self._require_scope(workspace_id, conversation_id)
        if draft.workspace_id != workspace_id:
            raise PlannerScopeMismatchError(
                "The decision draft does not belong to this workspace."
            )
        if draft.status not in _CREATABLE_DECISION_STATUSES:
            raise PlannerConflictError(
                "A decision can only be recorded as pending, accepted, or rejected."
            )
        moment = _utc_now()
        superseding = draft.supersedes_decision_id is not None
        stored = self._planner.create_decision(
            self._with_decision_provenance(draft, source_message_id),
            operation=self._build_operation(
                workspace_id=workspace_id,
                conversation_id=conversation_id,
                operation_type=(
                    PlannerOperationType.SUPERSEDE_DECISION
                    if superseding
                    else PlannerOperationType.RECORD_DECISION
                ),
                source_message_id=source_message_id,
                result_decision_id=draft.decision_id,
                input_summary=(
                    f"status={draft.status.value} type={draft.decision_type.value}"
                ),
                created_at=moment,
            ),
        )
        logger.info(
            "planner.decision recorded workspace_id=%s superseding=%s",
            workspace_id,
            superseding,
        )
        return stored

    def update_decision_status(
        self,
        workspace_id: str,
        decision_id: str,
        status: DecisionStatus | str,
    ) -> TripDecision:
        """Move one decision along its lifecycle and log the operation."""
        workspace_id = require_text(workspace_id, "workspace_id")
        decision_id = require_text(decision_id, "decision_id")
        self._require_workspace(workspace_id)
        target: DecisionStatus = (
            status if isinstance(status, DecisionStatus) else DecisionStatus(status)
        )
        current = self._planner.get_decision(workspace_id, decision_id)
        if target not in _DECISION_TRANSITIONS[current.status]:
            raise PlannerConflictError(
                f"A decision with status '{current.status.value}' cannot move "
                f"to '{target.value}'."
            )
        moment = _utc_now()
        stored = self._planner.update_decision_status(
            workspace_id,
            decision_id,
            target,
            operation=self._build_operation(
                workspace_id=workspace_id,
                conversation_id=None,
                operation_type=PlannerOperationType.UPDATE_DECISION_STATUS,
                source_message_id=None,
                result_decision_id=decision_id,
                input_summary=f"status={target.value}",
                created_at=moment,
            ),
        )
        logger.info(
            "planner.decision status workspace_id=%s status=%s",
            workspace_id,
            stored.status.value,
        )
        return stored

    def list_decisions(
        self,
        workspace_id: str,
        status: Optional[DecisionStatus] = None,
        decision_type: Optional[DecisionType] = None,
    ) -> tuple[TripDecision, ...]:
        """Return workspace decisions newest first."""
        workspace_id = require_text(workspace_id, "workspace_id")
        self._require_workspace(workspace_id)
        return self._planner.list_decisions(workspace_id, status, decision_type)

    def list_operations(self, workspace_id: str) -> tuple[PlannerOperation, ...]:
        """Return workspace planner operations newest first."""
        workspace_id = require_text(workspace_id, "workspace_id")
        self._require_workspace(workspace_id)
        return self._planner.list_operations(workspace_id)

    def _require_workspace(self, workspace_id: str) -> None:
        if self._workspaces.get(workspace_id) is None:
            raise WorkspaceNotFoundError("The parent workspace does not exist.")

    def _require_scope(self, workspace_id: str, conversation_id: Optional[str]) -> None:
        self._require_workspace(workspace_id)
        if conversation_id is None:
            return
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError("The conversation does not exist.")
        if conversation.workspace_id != workspace_id:
            raise PlannerScopeMismatchError(
                f"The conversation '{conversation_id}' does not belong to "
                f"workspace '{workspace_id}'."
            )

    @staticmethod
    def _with_decision_provenance(
        draft: TripDecision, source_message_id: Optional[str]
    ) -> TripDecision:
        import dataclasses

        return dataclasses.replace(
            draft,
            source_message_id=(
                source_message_id
                if source_message_id is not None
                else draft.source_message_id
            ),
        )

    @staticmethod
    def _build_operation(
        *,
        workspace_id: str,
        conversation_id: Optional[str],
        operation_type: PlannerOperationType,
        source_message_id: Optional[str],
        result_itinerary_version_id: Optional[str] = None,
        result_decision_id: Optional[str] = None,
        input_summary: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> PlannerOperation:
        """Build the operation row the repository writes atomically.

        The operation is returned, never persisted here: persistence
        happens inside the same repository transaction as the state
        change it describes.
        """
        return PlannerOperation(
            operation_id=generate_operation_id(),
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            operation_type=operation_type,
            status=PlannerOperationStatus.APPLIED,
            input_summary=input_summary,
            result_itinerary_version_id=result_itinerary_version_id,
            result_decision_id=result_decision_id,
            source_message_id=source_message_id,
            created_at=created_at or _utc_now(),
        )
