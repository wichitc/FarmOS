from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CostCenterCreate(BaseModel):
    code: str
    name: str


class CostCenterOut(BaseModel):
    id: str
    code: str
    name: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class LedgerEntryCreate(BaseModel):
    entry_type: str
    direction: str
    amount: float
    dimensions: dict = {}
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    notes: Optional[str] = None
    posted_at: Optional[datetime] = None


class LedgerEntryOut(BaseModel):
    id: str
    entry_type: str
    direction: str
    amount: float
    dimensions: dict
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    posted_at: datetime
    notes: Optional[str] = None
    posted_by: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BudgetCreate(BaseModel):
    direction: str
    amount: float
    dimensions: dict = {}
    period_start: date
    period_end: date
    notes: Optional[str] = None


class BudgetOut(BaseModel):
    id: str
    direction: str
    amount: float
    dimensions: dict
    period_start: date
    period_end: date
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BudgetVarianceOut(BaseModel):
    budget_id: str
    budgeted_amount: float
    actual_amount: float
    variance: float
    variance_pct: float


class ProfitabilityRequest(BaseModel):
    dimensions: dict
    overhead_allocation_pct: float = 0.0


class ProfitabilityOut(BaseModel):
    dimensions: dict
    revenue: float
    direct_costs: float
    allocated_overhead: float
    profit: float
    margin_pct: float


class ProfitabilityHeatmapRow(BaseModel):
    group_id: str
    revenue: float
    direct_costs: float
    profit: float
    margin_pct: float
