from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class FarmCreate(BaseModel):
    code: str
    name: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    area_hectares: Optional[float] = None


class FarmOut(BaseModel):
    id: str
    code: str
    name: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    area_hectares: Optional[float] = None
    status: str

    model_config = ConfigDict(from_attributes=True)


class ZoneCreate(BaseModel):
    code: str
    name: str


class ZoneOut(BaseModel):
    id: str
    farm_id: str
    code: str
    name: str

    model_config = ConfigDict(from_attributes=True)


class PlotCreate(BaseModel):
    code: str
    name: str
    area_hectares: Optional[float] = None


class PlotOut(BaseModel):
    id: str
    zone_id: str
    code: str
    name: str
    area_hectares: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class BlockCreate(BaseModel):
    code: str
    name: str
    area_hectares: Optional[float] = None


class BlockOut(BaseModel):
    id: str
    plot_id: str
    code: str
    name: str
    area_hectares: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class RowCreate(BaseModel):
    code: str
    name: str
    spacing_m: Optional[float] = None


class RowOut(BaseModel):
    id: str
    block_id: str
    code: str
    name: str
    spacing_m: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class TreeCreate(BaseModel):
    crop_id: str
    variety_id: Optional[str] = None
    code: Optional[str] = None
    planting_date: Optional[date] = None
    rootstock: Optional[str] = None
    height_m: Optional[float] = None
    canopy_diameter_m: Optional[float] = None
    trunk_diameter_cm: Optional[float] = None
    growth_stage: str = "seedling"
    lat: Optional[float] = None
    lng: Optional[float] = None
    notes: Optional[str] = None


class TreeUpdate(BaseModel):
    code: Optional[str] = None
    rootstock: Optional[str] = None
    height_m: Optional[float] = None
    canopy_diameter_m: Optional[float] = None
    trunk_diameter_cm: Optional[float] = None
    growth_stage: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class TreeOut(BaseModel):
    id: str
    row_id: str
    crop_id: str
    variety_id: Optional[str] = None
    digital_twin_id: Optional[str] = None
    code: str
    planting_date: Optional[date] = None
    rootstock: Optional[str] = None
    height_m: Optional[float] = None
    canopy_diameter_m: Optional[float] = None
    trunk_diameter_cm: Optional[float] = None
    growth_stage: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    status: str
    notes: Optional[str] = None
    deleted_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TreeBulkCreateRequest(BaseModel):
    trees: list[TreeCreate]


class TreeGridGenerateRequest(BaseModel):
    crop_id: str
    variety_id: Optional[str] = None
    count: int
    spacing_m: float = 3.0
    start_lat: Optional[float] = None
    start_lng: Optional[float] = None
    planting_date: Optional[date] = None


class SeasonCreate(BaseModel):
    name: str
    start_date: date
    end_date: Optional[date] = None


class SeasonOut(BaseModel):
    id: str
    farm_id: str
    name: str
    start_date: date
    end_date: Optional[date] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class TreeEventCreate(BaseModel):
    event_type: str
    payload: dict = {}
    occurred_at: Optional[datetime] = None


class TreeEventOut(BaseModel):
    id: str
    tree_id: str
    event_type: str
    payload: dict
    occurred_at: datetime
    created_by: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
