"""Planner storage interface and repository error types for milestone R7.

Per ADR 0008 product code depends on this interface rather than on SQLite
details. Route handlers and the planner service must not embed table DDL,
SQL statements, path creation, or connection management.
"""

from __future__ import annotations

from typing import Optional, Protocol

from backend.planner.models import (
    DecisionStatus,
    DecisionType,
    ItineraryStatus,
    ItineraryVersion,
    PlannerOperation,
    TripDecision,
)


class PlannerRepositoryError(Exception):
    """Base class for planner storage failures."""


class PlannerNotFoundError(PlannerRepositoryError):
    """A planner record is missing or belongs to another workspace.

    Cross-workspace access reports not-found so route errors never leak
    whether the identifier exists elsewhere.
    """


class PlannerStorageError(PlannerRepositoryError):
    """Storage could not complete the requested planner operation.

    Messages raised as this type are safe for a controlled HTTP 500 response.
    They must not carry local filesystem paths, full SQL text, credentials,
    or itinerary and decision content.
    """


class PlannerRepository(Protocol):
    """Persistence boundary for trip planner state."""

    def create_itinerary_version(self, version: ItineraryVersion) -> ItineraryVersion:
        """Persist an itinerary version, assigning the next version number.

        The incoming `version_number` is a placeholder: the repository
        assigns `max(version_number) + 1` for the workspace inside the same
        transaction, so successful creates stay contiguous per workspace and
        failed requests allocate nothing.

        Raises:
            PlannerStorageError: Storage failed.
        """
        ...

    def get_itinerary_version(
        self, workspace_id: str, itinerary_version_id: str
    ) -> ItineraryVersion:
        """Return one itinerary version scoped to the workspace.

        Raises:
            PlannerNotFoundError: The version is missing or elsewhere.
            PlannerStorageError: Storage failed.
        """
        ...

    def list_itinerary_versions(
        self, workspace_id: str, status: Optional[ItineraryStatus] = None
    ) -> tuple[ItineraryVersion, ...]:
        """Return workspace versions newest first, optionally filtered.

        Raises:
            PlannerStorageError: Storage failed.
        """
        ...

    def accept_itinerary_version(
        self, workspace_id: str, itinerary_version_id: str
    ) -> ItineraryVersion:
        """Accept one version, superseding prior accepted ones atomically.

        Prior accepted versions in the same workspace become `superseded`
        inside the same transaction. Accepting an already-accepted version
        returns it unchanged. Other workspaces are untouched.

        Raises:
            PlannerNotFoundError: The version is missing or elsewhere.
            PlannerStorageError: Storage failed.
        """
        ...

    def update_itinerary_status(
        self, workspace_id: str, itinerary_version_id: str, status: ItineraryStatus
    ) -> ItineraryVersion:
        """Set one version status without lifecycle reasoning.

        Lifecycle decisions belong to the planner service; this method only
        performs the scoped write.

        Raises:
            PlannerNotFoundError: The version is missing or elsewhere.
            PlannerStorageError: Storage failed.
        """
        ...

    def create_decision(self, decision: TripDecision) -> TripDecision:
        """Persist a decision, superseding its cited target atomically.

        When `supersedes_decision_id` is set, the same-workspace target
        becomes `superseded` inside the same transaction.

        Raises:
            PlannerNotFoundError: The cited target is missing or elsewhere.
            PlannerStorageError: Storage failed.
        """
        ...

    def get_decision(self, workspace_id: str, decision_id: str) -> TripDecision:
        """Return one decision scoped to the workspace.

        Raises:
            PlannerNotFoundError: The decision is missing or elsewhere.
            PlannerStorageError: Storage failed.
        """
        ...

    def list_decisions(
        self,
        workspace_id: str,
        status: Optional[DecisionStatus] = None,
        decision_type: Optional[DecisionType] = None,
    ) -> tuple[TripDecision, ...]:
        """Return workspace decisions newest first, optionally filtered.

        Raises:
            PlannerStorageError: Storage failed.
        """
        ...

    def update_decision_status(
        self, workspace_id: str, decision_id: str, status: DecisionStatus
    ) -> TripDecision:
        """Set one decision status without lifecycle reasoning.

        Lifecycle decisions belong to the planner service; this method only
        performs the scoped write.

        Raises:
            PlannerNotFoundError: The decision is missing or elsewhere.
            PlannerStorageError: Storage failed.
        """
        ...

    def create_operation(self, operation: PlannerOperation) -> PlannerOperation:
        """Persist one planner operation row and return it.

        Raises:
            PlannerStorageError: Storage failed.
        """
        ...

    def list_operations(self, workspace_id: str) -> tuple[PlannerOperation, ...]:
        """Return workspace operations newest first.

        Raises:
            PlannerStorageError: Storage failed.
        """
        ...
