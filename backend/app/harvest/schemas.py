from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class FruitObservationCreate(BaseModel):
    tree_id: str
    stage: str
    estimated_count: Optional[int] = None
    observed_at: Optional[datetime] = None
    notes: Optional[str] = None


class FruitObservationOut(BaseModel):
    id: str
    tree_id: str
    stage: str
    estimated_count: Optional[int] = None
    observed_at: datetime
    notes: Optional[str] = None
    recorded_by: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class YieldEstimateRequest(BaseModel):
    plot_id: Optional[str] = None
    tree_id: Optional[str] = None
    season_id: Optional[str] = None
    tree_count: int
    avg_fruit_count_per_tree: float
    avg_fruit_weight_kg: float
    variability_pct: float = 20.0


class YieldForecastOut(BaseModel):
    id: str
    farm_id: str
    plot_id: Optional[str] = None
    tree_id: Optional[str] = None
    season_id: Optional[str] = None
    estimated_yield_kg_low: float
    estimated_yield_kg_high: float
    confidence: float
    basis: dict
    forecast_date: datetime

    model_config = ConfigDict(from_attributes=True)


class HarvestLotCreate(BaseModel):
    plot_id: Optional[str] = None
    tree_id: Optional[str] = None
    season_id: Optional[str] = None
    harvested_at: Optional[datetime] = None
    quantity_kg: float
    grade: Optional[str] = None
    notes: Optional[str] = None


class HarvestLotOut(BaseModel):
    id: str
    farm_id: str
    plot_id: Optional[str] = None
    tree_id: Optional[str] = None
    season_id: Optional[str] = None
    qr_code: str
    harvested_at: datetime
    quantity_kg: float
    grade: Optional[str] = None
    harvested_by: Optional[str] = None
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PackingLotCreate(BaseModel):
    packed_at: Optional[datetime] = None
    harvest_lot_ids: list[str]
    notes: Optional[str] = None


class PackingLotOut(BaseModel):
    id: str
    farm_id: str
    qr_code: str
    packed_at: datetime
    packed_by: Optional[str] = None
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TraceHarvestLotOut(BaseModel):
    quantity_kg: float
    grade: Optional[str] = None
    harvested_at: datetime
    plot_code: Optional[str] = None
    plot_name: Optional[str] = None
    tree_code: Optional[str] = None


class TraceOut(BaseModel):
    packing_lot_qr: str
    packed_at: datetime
    farm_name: str
    harvest_lots: list[TraceHarvestLotOut]
