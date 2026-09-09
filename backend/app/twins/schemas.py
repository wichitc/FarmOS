from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class TwinTypeCreate(BaseModel):
    code: str
    name: str
    category: str
    is_ifc_sourced: bool = False
    property_schema: dict = {}


class TwinTypeOut(BaseModel):
    id: str
    code: str
    name: str
    category: str
    is_ifc_sourced: bool
    property_schema: dict

    model_config = ConfigDict(from_attributes=True)


class DigitalTwinCreate(BaseModel):
    twin_type_id: str
    farm_id: Optional[str] = None
    display_code: str
    current_state: dict = {}
    location_ref: dict = {}
    model_ref: dict = {}


class DigitalTwinUpdate(BaseModel):
    display_code: Optional[str] = None
    current_state: Optional[dict] = None
    location_ref: Optional[dict] = None
    model_ref: Optional[dict] = None
    status: Optional[str] = None


class DigitalTwinOut(BaseModel):
    id: str
    twin_type_id: str
    farm_id: Optional[str] = None
    display_code: str
    current_state: dict
    location_ref: dict
    model_ref: dict
    status: str
    deleted_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TwinRelationshipCreate(BaseModel):
    to_twin_id: str
    relation_type: str
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None


class TwinRelationshipOut(BaseModel):
    id: str
    from_twin_id: str
    to_twin_id: str
    relation_type: str
    valid_from: date
    valid_to: Optional[date] = None

    model_config = ConfigDict(from_attributes=True)


class TwinPropertySet(BaseModel):
    key: str
    value: Any


class TwinPropertyOut(BaseModel):
    key: str
    value: Any

    model_config = ConfigDict(from_attributes=True)


class TwinEventCreate(BaseModel):
    event_type: str
    payload: dict = {}
    occurred_at: Optional[datetime] = None


class TwinEventOut(BaseModel):
    id: str
    twin_id: str
    event_type: str
    payload: dict
    occurred_at: datetime
    created_by: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TwinTelemetryCreate(BaseModel):
    metric: str
    value_numeric: Optional[float] = None
    value_text: Optional[str] = None
    recorded_at: Optional[datetime] = None


class TwinTelemetryOut(BaseModel):
    id: str
    twin_id: str
    metric: str
    value_numeric: Optional[float] = None
    value_text: Optional[str] = None
    recorded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TwinInspectorOut(BaseModel):
    id: str
    display_code: str
    twin_type: TwinTypeOut
    farm_id: Optional[str] = None
    current_state: dict
    status: str
    properties: dict
    recent_events: list[TwinEventOut]
    latest_telemetry: dict
