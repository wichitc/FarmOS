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
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class DeviceRegisterOut(DeviceOut):
    secret: str


class DeviceDeactivateRequest(BaseModel):
    reason: Optional[str] = None


ACTUATOR_COMMANDS = ("on", "off", "auto", "schedule")


class ActuatorCommandRequest(BaseModel):
    """Master prompt §25. `confirmed` is the same-request human
    confirmation an L2 agent-gateway action requires for "on"/"auto"/
    "schedule" - required for those, ignored for "off" (never gated,
    see `routers/v1/iot.py::send_actuator_command`)."""

    command: str
    scheduled_for: Optional[datetime] = None
    confirmed: bool = False


class ActuatorCommandOut(BaseModel):
    id: str
    twin_id: str
    command: str
    status: str
    issued_by: Optional[str] = None
    executed_at: Optional[datetime] = None
    result: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class ActuatorCommandCancelRequest(BaseModel):
    """Master-prompt integration, Phase 38 - cancels a still-pending
    'schedule' command before it fires."""

    reason: str = "Cancelled by operator"


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
