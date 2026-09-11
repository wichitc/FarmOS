from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class EquipmentHealthItem(BaseModel):
    twin_id: str
    display_code: str
    farm_id: Optional[str] = None
    score: Optional[int] = None
    band: Optional[str] = None
    assessed_at: Optional[datetime] = None


class EquipmentHealthWidget(BaseModel):
    """FR-DASH-003: stat tiles + distribution + sortable table. `equipment`
    is sorted worst-first (lowest score, unassessed last) - a reasonable
    default order for "what needs attention"; a frontend table can re-sort
    client-side."""

    total: int
    average_score: float
    by_band: dict[str, int]
    equipment: list[EquipmentHealthItem]


class WeatherWidget(BaseModel):
    """`None` means no reading has been ingested for that metric - honest
    absence, not a fabricated zero (same convention as
    `weather.provider.current_reading` returning `None`)."""

    temperature_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    rainfall_mm: Optional[float] = None
    soil_moisture_pct: Optional[float] = None


class DiseaseRiskWidget(BaseModel):
    open_incident_count: int
    highest_risk_score: Optional[float] = None


class IrrigationStatusWidget(BaseModel):
    pending_approval_count: int
    approved_count: int
    completed_last_7_days: int


class YieldForecastWidget(BaseModel):
    estimated_yield_kg_low: float
    estimated_yield_kg_high: float
    confidence: float
    forecast_date: datetime


class HarvestStatusWidget(BaseModel):
    lots_last_30_days: int
    total_kg_last_30_days: float


class WorkOrdersWidget(BaseModel):
    open_count: int
    in_progress_count: int


class LowStockItem(BaseModel):
    item_id: str
    code: str
    name: str
    on_hand: float
    min_qty: float


class InventoryWidget(BaseModel):
    low_stock_count: int
    items: list[LowStockItem]


class FinancialKpiWidget(BaseModel):
    """All-time (no date bound) profitability for this farm's ledger
    dimension - same aggregation `accounting/profitability.py` already
    computes on demand, just surfaced here rather than requiring a
    separate call."""

    revenue: float
    direct_costs: float
    profit: float
    margin_pct: float


class AIRecommendationItem(BaseModel):
    """Agent actions awaiting a human decision (status="proposed") - the
    "AI recommendations" a Command Center widget would surface for
    attention. Recorded `Prediction`s remain available via their own
    `GET /api/v1/ai/predictions` for anything not yet turned into an
    agent-proposed action."""

    agent_action_id: str
    agent_code: str
    action_type: str
    level: str
    rationale: str
    created_at: datetime


class FleetSummary(BaseModel):
    """FR-DASH-003's fleet/equipment health view, tenant-wide - the
    authenticated, RLS-scoped, twin-model successor to the legacy
    `/api/dashboard/summary` (kept as-is; not removed)."""

    generated_at: datetime
    equipment_health: EquipmentHealthWidget
    inventory: InventoryWidget
    ai_recommendations: list[AIRecommendationItem]


class FarmCommandCenterSummary(BaseModel):
    """FR-DASH-001's per-farm widget rollup - one aggregation call
    replacing what a real dashboard would otherwise make many separate
    calls for. Map/3D-viewer and drag-and-drop layout persistence
    (FR-DASH-002) are frontend concerns, out of scope for a backend-only
    build (see docs/05-RTM.md Phase 16 checklist)."""

    generated_at: datetime
    farm_id: str
    equipment_health: EquipmentHealthWidget
    weather: WeatherWidget
    disease_risk: DiseaseRiskWidget
    irrigation_status: IrrigationStatusWidget
    yield_forecast: Optional[YieldForecastWidget] = None
    harvest_status: HarvestStatusWidget
    work_orders: WorkOrdersWidget
    financial_kpis: FinancialKpiWidget
    ai_recommendations: list[AIRecommendationItem]
