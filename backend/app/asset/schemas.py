from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AssetRegisterRequest(BaseModel):
    """FR-ASSET-001. Creates the underlying DigitalTwin plus the standard
    TwinProperty fields in one call - manufacturer/model/serial/warranty
    are static-ish attributes (TwinProperty); condition (temperature,
    vibration, status) is the twin's current_state, same convention as the
    Phase 6 equipment migration."""

    farm_id: Optional[str] = None
    twin_type_id: str
    display_code: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_no: Optional[str] = None
    install_date: Optional[date] = None
    warranty_until: Optional[date] = None
    documents: list[str] = []
    initial_state: dict = {}


class AssetOut(BaseModel):
    id: str
    twin_type_id: str
    farm_id: Optional[str] = None
    display_code: str
    current_state: dict
    status: str
    properties: dict = {}

    model_config = ConfigDict(from_attributes=True)


class HealthAssessmentOut(BaseModel):
    id: str
    twin_id: str
    computed_at: datetime
    score: int
    band: str
    summary: str
    metrics: list
    recommendations: list
    method_id: str
    method_version: str

    model_config = ConfigDict(from_attributes=True)


class MaintenanceRequestCreate(BaseModel):
    strategy: str = "corrective"
    description: str
    source_assessment_id: Optional[str] = None


class MaintenanceRequestOut(BaseModel):
    id: str
    twin_id: str
    farm_id: Optional[str] = None
    strategy: str
    description: str
    source_assessment_id: Optional[str] = None
    status: str
    workflow_instance_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ApprovalDecisionRequest(BaseModel):
    reason: Optional[str] = None


class WorkOrderUpdate(BaseModel):
    status: Optional[str] = None
    scheduled_for: Optional[datetime] = None
    assigned_to: Optional[str] = None
    parts_used: Optional[list] = None
    labor_hours: Optional[float] = None
    inspection_notes: Optional[str] = None


class WorkOrderOut(BaseModel):
    id: str
    twin_id: str
    farm_id: Optional[str] = None
    request_id: str
    status: str
    scheduled_for: Optional[datetime] = None
    assigned_to: Optional[str] = None
    parts_used: list
    labor_hours: Optional[float] = None
    inspection_notes: Optional[str] = None
    completed_at: Optional[datetime] = None
    completed_by: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
