"""Trip planner state for milestone R7.

Planner state holds explicit itinerary versions, trip decisions, and an
append-only operation log scoped to a trip workspace. This package owns the
domain contracts; storage, service, and evaluation arrive in later R7 tasks.
"""

from backend.planner.models import (
    DECISION_ID_PREFIX,
    ITINERARY_VERSION_ID_PREFIX,
    OPERATION_ID_PREFIX,
    DecisionStatus,
    DecisionType,
    ItineraryItem,
    ItineraryItemType,
    ItineraryStatus,
    ItineraryVersion,
    PlannerOperation,
    PlannerOperationStatus,
    PlannerOperationType,
    PlannerValidationError,
    TripDecision,
    generate_decision_id,
    generate_itinerary_version_id,
    generate_operation_id,
    require_text,
)
from backend.planner.repository import (
    PlannerNotFoundError,
    PlannerRepository,
    PlannerRepositoryError,
    PlannerStorageError,
)
from backend.planner.service import (
    PlannerConflictError,
    PlannerScopeMismatchError,
    PlannerService,
    PlannerServiceError,
)

__all__ = [
    "DECISION_ID_PREFIX",
    "ITINERARY_VERSION_ID_PREFIX",
    "OPERATION_ID_PREFIX",
    "DecisionStatus",
    "DecisionType",
    "ItineraryItem",
    "ItineraryItemType",
    "ItineraryStatus",
    "ItineraryVersion",
    "PlannerNotFoundError",
    "PlannerOperation",
    "PlannerOperationStatus",
    "PlannerOperationType",
    "PlannerConflictError",
    "PlannerRepository",
    "PlannerRepositoryError",
    "PlannerScopeMismatchError",
    "PlannerService",
    "PlannerServiceError",
    "PlannerStorageError",
    "PlannerValidationError",
    "TripDecision",
    "generate_decision_id",
    "generate_itinerary_version_id",
    "generate_operation_id",
    "require_text",
]
