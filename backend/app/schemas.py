from datetime import datetime, date
from typing import Optional, List, Dict

from pydantic import BaseModel, ConfigDict


class ModelOut(BaseModel):
    id: str
    name: str
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EquipmentCreate(BaseModel):
    model_id: Optional[str] = None
    type: str
    name: str
    pos_x: float = 0.0
    pos_y: float = 0.0
    pos_z: float = 0.0
    rotation_y: float = 0.0
    scale: float = 1.0
    notes: Optional[str] = None
    status: Optional[str] = None
    install_date: Optional[date] = None
    last_maintenance_date: Optional[date] = None
    operating_hours: Optional[float] = None
    temperature_c: Optional[float] = None
    vibration_mm_s: Optional[float] = None


class EquipmentUpdate(BaseModel):
    name: Optional[str] = None
    pos_x: Optional[float] = None
    pos_y: Optional[float] = None
    pos_z: Optional[float] = None
    rotation_y: Optional[float] = None
    scale: Optional[float] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    install_date: Optional[date] = None
    last_maintenance_date: Optional[date] = None
    operating_hours: Optional[float] = None
    temperature_c: Optional[float] = None
    vibration_mm_s: Optional[float] = None


class EquipmentOut(BaseModel):
    id: str
    model_id: Optional[str] = None
    type: str
    name: str
    pos_x: float
    pos_y: float
    pos_z: float
    rotation_y: float
    scale: float
    notes: Optional[str] = None
    status: str
    install_date: Optional[date] = None
    last_maintenance_date: Optional[date] = None
    operating_hours: float
    temperature_c: Optional[float] = None
    vibration_mm_s: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HealthMetric(BaseModel):
    label: str
    value: Optional[float] = None
    unit: str = ""
    band: str


class HealthOut(BaseModel):
    equipment_id: str
    score: int
    band: str
    summary: str
    metrics: List[HealthMetric]
    recommendations: List[str]


class DashboardEquipmentItem(BaseModel):
    id: str
    type: str
    name: str
    model_id: Optional[str] = None
    model_name: Optional[str] = None
    score: int
    band: str
    summary: str


class DashboardSummary(BaseModel):
    generated_at: datetime
    total: int
    average_score: float
    by_band: Dict[str, int]
    equipment: List[DashboardEquipmentItem]
