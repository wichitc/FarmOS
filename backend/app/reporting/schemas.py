from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class ReportFilter(BaseModel):
    """Shared date/season range filter (RPT-002). `farm_id` is required at
    the router level (ABAC-scoped via `assert_farm_scope`, same as every
    other farm-scoped endpoint) - it is not part of this model since it
    comes from the path, not a query filter."""

    plot_id: Optional[str] = None
    season_id: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None


class FarmHealthRow(BaseModel):
    """Equipment health (asset-category twins) is farm-wide; disease
    incidents are per-plot. Tree-level health scoring has no persisted
    metric anywhere in the platform (no continuous "tree health score" is
    computed by any prior phase) - this report is honest about that
    rather than inventing one."""

    farm_id: str
    open_disease_incidents: int
    highest_disease_risk_score: Optional[float]
    equipment_count: int
    equipment_average_score: Optional[float]
    equipment_critical_count: int


class IrrigationFertigationUsageRow(BaseModel):
    plot_id: Optional[str]
    irrigation_events: int
    total_irrigation_liters: float
    fertigation_events: int
    total_fertigation_kg: float


class WorkCompletionRow(BaseModel):
    work_type: str
    requested: int
    closed: int
    cancelled_or_rejected: int
    completion_rate_pct: float


class DiseaseTrendRow(BaseModel):
    period: str  # ISO week, e.g. "2026-W03"
    new_incidents: int
    confirmed_incidents: int
    resolved_incidents: int


class YieldHarvestRow(BaseModel):
    plot_id: Optional[str]
    forecast_count: int
    estimated_yield_kg_low: float
    estimated_yield_kg_high: float
    actual_harvest_kg: float
    variance_kg: float


class MaintenanceRow(BaseModel):
    strategy: str
    request_count: int
    work_orders_completed: int
    average_labor_hours: Optional[float]
    pm_compliance_pct: float  # preventive+predictive share of all requests


class InventoryRow(BaseModel):
    item_code: str
    item_name: str
    on_hand_qty: float
    received_qty: float
    issued_qty: float
    lots_expiring_within_30_days: int


class FinancialRow(BaseModel):
    direction: str
    actual_amount: float
    budgeted_amount: Optional[float]
    variance: Optional[float]
