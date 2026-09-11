from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class WorkTaskCreate(BaseModel):
    plot_id: Optional[str] = None
    work_type: str
    title: str
    description: Optional[str] = None
    source_type: Optional[str] = None
    source_id: Optional[str] = None


class WorkTaskOut(BaseModel):
    id: str
    farm_id: str
    plot_id: Optional[str] = None
    work_type: str
    title: str
    description: Optional[str] = None
    status: str
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    requested_by: Optional[str] = None
    scheduled_for: Optional[datetime] = None
    assigned_to: Optional[str] = None
    assigned_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    evidence: dict
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None
    cancel_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class WorkTaskPlanRequest(BaseModel):
    scheduled_for: Optional[datetime] = None


class WorkTaskAssignRequest(BaseModel):
    assigned_to: str


class WorkTaskAcceptDecisionRequest(BaseModel):
    reason: Optional[str] = None


class WorkTaskCompleteRequest(BaseModel):
    evidence: dict = {}


class WorkTaskReviewRequest(BaseModel):
    decision: str  # "close" or "send_back"
    notes: Optional[str] = None


class WorkTaskCancelRequest(BaseModel):
    reason: Optional[str] = None
