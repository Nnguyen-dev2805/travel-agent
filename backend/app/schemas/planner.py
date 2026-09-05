"""Pydantic schemas for the R7 planner routes.

Request models mirror the planner domain contracts and reject unknown
fields. Response models carry controlled planner fields only: identifiers,
lifecycle states, structured items, and counts. No itinerary text beyond
the stored snapshot and no raw message content travels outside the domain
objects the service already validated.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.planner.models import (
    DecisionStatus,
    DecisionType,
    ItineraryItem,
    ItineraryItemType,
    ItineraryStatus,
    ItineraryVersion,
    PlannerOperation,
    PlannerOperationType,
    TripDecision,
)


class ItineraryItemRequest(BaseModel):
    """One structured stop inside an itinerary create request."""

    model_config = ConfigDict(extra="forbid")

    day_index: int
    position: int
    item_type: ItineraryItemType
    title: str
    location: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    notes: Optional[str] = None
    source_decision_ids: List[str] = Field(default_factory=list)


class ItineraryCreateRequest(BaseModel):
    """Create a draft or proposed itinerary version."""

    model_config = ConfigDict(extra="forbid")

    status: ItineraryStatus = ItineraryStatus.DRAFT
    title: Optional[str] = None
    summary: Optional[str] = None
    items: List[ItineraryItemRequest] = Field(default_factory=list)
    conversation_id: Optional[str] = None
    source_message_id: Optional[str] = None


class DecisionCreateRequest(BaseModel):
    """Record a trip decision, optionally superseding an earlier one."""

    model_config = ConfigDict(extra="forbid")

    decision_type: DecisionType = DecisionType.PREFERENCE
    status: DecisionStatus = DecisionStatus.PENDING
    statement: str
    rationale: Optional[str] = None
    conversation_id: Optional[str] = None
    source_message_id: Optional[str] = None
    supersedes_decision_id: Optional[str] = None


class DecisionStatusUpdateRequest(BaseModel):
    """Move one decision along its lifecycle."""

    model_config = ConfigDict(extra="forbid")

    status: DecisionStatus


class ItineraryItemResponse(BaseModel):
    """One structured stop inside a stored itinerary version."""

    day_index: int
    position: int
    item_type: ItineraryItemType
    title: str
    location: Optional[str]
    start_time: Optional[str]
    end_time: Optional[str]
    notes: Optional[str]
    source_decision_ids: List[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, item: ItineraryItem) -> "ItineraryItemResponse":
        return cls(
            day_index=item.day_index,
            position=item.position,
            item_type=item.item_type,
            title=item.title,
            location=item.location,
            start_time=item.start_time,
            end_time=item.end_time,
            notes=item.notes,
            source_decision_ids=list(item.source_decision_ids),
        )


class ItineraryVersionResponse(BaseModel):
    """One stored itinerary version snapshot."""

    itinerary_version_id: str
    workspace_id: str
    version_number: int
    status: ItineraryStatus
    title: Optional[str]
    summary: Optional[str]
    items: List[ItineraryItemResponse] = Field(default_factory=list)
    created_from_operation_id: Optional[str]
    created_from_message_id: Optional[str]
    created_at: datetime

    @classmethod
    def from_domain(cls, version: ItineraryVersion) -> "ItineraryVersionResponse":
        return cls(
            itinerary_version_id=version.itinerary_version_id,
            workspace_id=version.workspace_id,
            version_number=version.version_number,
            status=version.status,
            title=version.title,
            summary=version.summary,
            items=[ItineraryItemResponse.from_domain(item) for item in version.items],
            created_from_operation_id=version.created_from_operation_id,
            created_from_message_id=version.created_from_message_id,
            created_at=version.created_at,
        )


class TripDecisionResponse(BaseModel):
    """One stored trip decision, including rejected options."""

    decision_id: str
    workspace_id: str
    decision_type: DecisionType
    status: DecisionStatus
    statement: str
    rationale: Optional[str]
    source_message_id: Optional[str]
    supersedes_decision_id: Optional[str]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, decision: TripDecision) -> "TripDecisionResponse":
        return cls(
            decision_id=decision.decision_id,
            workspace_id=decision.workspace_id,
            decision_type=decision.decision_type,
            status=decision.status,
            statement=decision.statement,
            rationale=decision.rationale,
            source_message_id=decision.source_message_id,
            supersedes_decision_id=decision.supersedes_decision_id,
            created_at=decision.created_at,
            updated_at=decision.updated_at,
        )


class PlannerOperationResponse(BaseModel):
    """One append-only planner operation row."""

    operation_id: str
    workspace_id: str
    conversation_id: Optional[str]
    operation_type: PlannerOperationType
    status: str
    input_summary: Optional[str]
    result_itinerary_version_id: Optional[str]
    result_decision_id: Optional[str]
    source_message_id: Optional[str]
    created_at: datetime

    @classmethod
    def from_domain(cls, operation: PlannerOperation) -> "PlannerOperationResponse":
        return cls(
            operation_id=operation.operation_id,
            workspace_id=operation.workspace_id,
            conversation_id=operation.conversation_id,
            operation_type=operation.operation_type,
            status=operation.status.value,
            input_summary=operation.input_summary,
            result_itinerary_version_id=operation.result_itinerary_version_id,
            result_decision_id=operation.result_decision_id,
            source_message_id=operation.source_message_id,
            created_at=operation.created_at,
        )
