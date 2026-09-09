from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DeviceRegisterRequest(BaseModel):
    farm_id: str
    twin_type_id: str
    display_code: str
    device_key: str
    protocol: str = "mqtt"
    gateway_id: Optional[str] = None


class DeviceOut(BaseModel):
    id: str
    digital_twin_id: str
    farm_id: str
    device_key: str
    protocol: str
    gateway_id: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    is_online: bool

    model_config = ConfigDict(from_attributes=True)


class DeviceRegisterOut(DeviceOut):
    secret: str


class RuleCreate(BaseModel):
    twin_type_id: str
    metric: str
    operator: str
    threshold_value: float
    severity: str = "medium"
    message_template: str
    is_active: bool = True


class RuleOut(BaseModel):
    id: str
    twin_type_id: str
    metric: str
    operator: str
    threshold_value: float
    severity: str
    message_template: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class AlertOut(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    severity: str
    status: str
    source_rule_id: Optional[str] = None
    message: str
    raised_at: datetime
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
