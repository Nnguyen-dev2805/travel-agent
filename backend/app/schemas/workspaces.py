"""Public API schemas for the R3 trip workspace routes.

These schemas own the HTTP request and response JSON shapes only. Domain rules
live in `backend.workspaces`. The list response is deliberately an object with a
`workspaces` array rather than a bare array, per the approved R3 specification.
"""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from backend.workspaces.models import (
    DateWindow,
    PlanningStatus,
    RetentionState,
    TripWorkspace,
)


class DateWindowPayload(BaseModel):
    """Optional planned travel window. Either bound may be absent."""

    start_date: Optional[date] = Field(
        None, json_schema_extra={"example": "2026-12-20"}
    )
    end_date: Optional[date] = Field(None, json_schema_extra={"example": "2026-12-25"})

    def to_domain(self) -> Optional[DateWindow]:
        """Return a domain date window, or None when both bounds are absent."""
        if self.start_date is None and self.end_date is None:
            return None
        return DateWindow(start_date=self.start_date, end_date=self.end_date)

    @classmethod
    def from_domain(cls, window: Optional[DateWindow]) -> Optional["DateWindowPayload"]:
        if window is None:
            return None
        return cls(start_date=window.start_date, end_date=window.end_date)


class WorkspaceCreateRequest(BaseModel):
    """Create one trip workspace.

    `owner_user_id` is a local development scope label supplied by the caller. It
    is not authentication, authorization, or tenant isolation. `workspace_id` and
    `retention_state` are server-owned and are not accepted here.
    """

    owner_user_id: str = Field(..., json_schema_extra={"example": "local-user"})
    title: str = Field(..., json_schema_extra={"example": "Da Nang family trip"})
    destination_scope: Optional[str] = Field(
        None, json_schema_extra={"example": "Da Nang and Hoi An"}
    )
    date_window: Optional[DateWindowPayload] = None
    planning_status: Optional[PlanningStatus] = Field(
        None, json_schema_extra={"example": "idea"}
    )


class WorkspaceResponse(BaseModel):
    """One trip workspace record."""

    workspace_id: str = Field(..., json_schema_extra={"example": "tw_2f8a1c"})
    owner_user_id: str = Field(..., json_schema_extra={"example": "local-user"})
    title: str = Field(..., json_schema_extra={"example": "Da Nang family trip"})
    destination_scope: Optional[str] = None
    date_window: Optional[DateWindowPayload] = None
    planning_status: PlanningStatus
    retention_state: RetentionState
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, workspace: TripWorkspace) -> "WorkspaceResponse":
        return cls(
            workspace_id=workspace.workspace_id,
            owner_user_id=workspace.owner_user_id,
            title=workspace.title,
            destination_scope=workspace.destination_scope,
            date_window=DateWindowPayload.from_domain(workspace.date_window),
            planning_status=workspace.planning_status,
            retention_state=workspace.retention_state,
            created_at=workspace.created_at,
            updated_at=workspace.updated_at,
        )


class WorkspaceListResponse(BaseModel):
    """Owner-scoped workspace list in governed newest-first order."""

    workspaces: List[WorkspaceResponse] = Field(default_factory=list)
