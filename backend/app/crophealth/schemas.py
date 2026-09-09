from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DiseaseCreate(BaseModel):
    code: str
    name_en: str
    name_th: str
    pathogen_type: str
    symptoms: Optional[str] = None
    susceptible_crop_codes: list[str] = []


class DiseaseOut(BaseModel):
    id: str
    code: str
    name_en: str
    name_th: str
    pathogen_type: str
    symptoms: Optional[str] = None
    susceptible_crop_codes: list[str]
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class DiseaseIncidentCreate(BaseModel):
    plot_id: Optional[str] = None
    tree_id: Optional[str] = None
    disease_id: str
    source_detection_id: Optional[str] = None
    risk_score: Optional[float] = None
    confidence: Optional[float] = None
    evidence: dict = {}
    notes: Optional[str] = None


class DiseaseIncidentOut(BaseModel):
    id: str
    farm_id: str
    plot_id: Optional[str] = None
    tree_id: Optional[str] = None
    disease_id: str
    source_detection_id: Optional[str] = None
    status: str
    risk_score: Optional[float] = None
    confidence: Optional[float] = None
    evidence: dict
    notes: Optional[str] = None
    reported_by: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class IncidentStatusUpdateRequest(BaseModel):
    status: str
    notes: Optional[str] = None


class TreatmentPlanCreate(BaseModel):
    incident_id: str
    method: Optional[str] = None
    chemical_or_treatment: dict = {}
    work_task_ref: Optional[str] = None
    reason: Optional[str] = None
    scheduled_for: Optional[datetime] = None


class TreatmentPlanOut(BaseModel):
    id: str
    incident_id: str
    farm_id: str
    method: Optional[str] = None
    chemical_or_treatment: dict
    work_task_ref: Optional[str] = None
    reason: Optional[str] = None
    status: str
    scheduled_for: Optional[datetime] = None
    workflow_instance_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TreatmentEventCreate(BaseModel):
    applied_at: Optional[datetime] = None
    actual_method: dict = {}
    notes: Optional[str] = None


class TreatmentEventOut(BaseModel):
    id: str
    plan_id: str
    farm_id: str
    applied_at: datetime
    executed_by: str
    actual_method: dict
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ApprovalDecisionRequest(BaseModel):
    reason: Optional[str] = None


class DiseaseRiskRequest(BaseModel):
    plot_id: Optional[str] = None
    humidity_pct: Optional[float] = None
    rainfall_mm_7d: Optional[float] = None
    leaf_wetness_hours: Optional[float] = None


class DiseaseRiskOut(BaseModel):
    risk_score: float
    band: str
    confidence: float
    evidence: list[str]
    recommendations: list[str]
