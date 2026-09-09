from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class IrrigationPlanCreate(BaseModel):
    plot_id: Optional[str] = None
    source_twin_id: Optional[str] = None
    source: str = "manual"
    recommended_volume_liters: Optional[float] = None
    recommended_duration_minutes: Optional[float] = None
    reason: Optional[str] = None
    scheduled_for: Optional[datetime] = None


class IrrigationPlanOut(BaseModel):
    id: str
    farm_id: str
    plot_id: Optional[str] = None
    source_twin_id: Optional[str] = None
    source: str
    status: str
    recommended_volume_liters: Optional[float] = None
    recommended_duration_minutes: Optional[float] = None
    reason: Optional[str] = None
    scheduled_for: Optional[datetime] = None
    workflow_instance_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class IrrigationEventCreate(BaseModel):
    actual_volume_liters: Optional[float] = None
    actual_duration_minutes: Optional[float] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    safety_checks: dict = {}
    notes: Optional[str] = None


class IrrigationEventOut(BaseModel):
    id: str
    plan_id: Optional[str] = None
    farm_id: str
    plot_id: Optional[str] = None
    actual_volume_liters: Optional[float] = None
    actual_duration_minutes: Optional[float] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    executed_by: str
    safety_checks: dict
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class FertilizerCreate(BaseModel):
    code: str
    name: str
    composition: dict = {}
    stock_ref: Optional[str] = None


class FertilizerOut(BaseModel):
    id: str
    code: str
    name: str
    composition: dict
    stock_ref: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class FertigationPlanCreate(BaseModel):
    plot_id: Optional[str] = None
    fertilizer_id: str
    source: str = "manual"
    target_n_kg: Optional[float] = None
    target_p_kg: Optional[float] = None
    target_k_kg: Optional[float] = None
    recommended_quantity_kg: Optional[float] = None
    reason: Optional[str] = None
    scheduled_for: Optional[datetime] = None


class FertigationPlanOut(BaseModel):
    id: str
    farm_id: str
    plot_id: Optional[str] = None
    fertilizer_id: str
    source: str
    status: str
    target_n_kg: Optional[float] = None
    target_p_kg: Optional[float] = None
    target_k_kg: Optional[float] = None
    recommended_quantity_kg: Optional[float] = None
    reason: Optional[str] = None
    scheduled_for: Optional[datetime] = None
    workflow_instance_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class FertigationEventCreate(BaseModel):
    tree_id: Optional[str] = None
    actual_quantity_kg: Optional[float] = None
    actual_breakdown: dict = {}
    applied_at: Optional[datetime] = None
    notes: Optional[str] = None


class FertigationEventOut(BaseModel):
    id: str
    plan_id: Optional[str] = None
    farm_id: str
    plot_id: Optional[str] = None
    tree_id: Optional[str] = None
    actual_quantity_kg: Optional[float] = None
    actual_breakdown: dict
    applied_at: datetime
    executed_by: str
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ApprovalDecisionRequest(BaseModel):
    reason: Optional[str] = None
