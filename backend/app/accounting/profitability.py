"""Profitability computation (FR-PROF-001/002). Revenue and direct costs
are real aggregations over posted `LedgerEntry` rows (not a placeholder
formula like `health.py`/`app.irrigation.recommendation`'s rule engines -
there's nothing to estimate, the ledger already has the numbers). The only
"configurable, indicative" part is overhead allocation (FR-PROF-001 asks
for "configurable cost-allocation methods") - a flat percentage-of-revenue
split, the simplest of several defensible allocation bases, swappable
later without changing this function's contract.

Dimension matching uses PostgreSQL JSONB containment (`dimensions @>
filter`) so a caller can filter by any subset of the eleven FR-ACC-001
dimensions (e.g. just `plot_id`, or `plot_id` + `season_id` together) and
match every posting that was tagged with at least those dimensions.
"""
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models as acct_models


@dataclass
class ProfitabilityResult:
    revenue: float
    direct_costs: float
    allocated_overhead: float
    profit: float
    margin_pct: float


def compute_profitability(
    db: Session, *, dimensions: dict, overhead_allocation_pct: float = 0.0
) -> ProfitabilityResult:
    revenue = (
        db.query(func.coalesce(func.sum(acct_models.LedgerEntry.amount), 0.0))
        .filter(acct_models.LedgerEntry.direction == "revenue", acct_models.LedgerEntry.dimensions.contains(dimensions))
        .scalar()
    )
    direct_costs = (
        db.query(func.coalesce(func.sum(acct_models.LedgerEntry.amount), 0.0))
        .filter(acct_models.LedgerEntry.direction == "expense", acct_models.LedgerEntry.dimensions.contains(dimensions))
        .scalar()
    )
    allocated_overhead = revenue * (overhead_allocation_pct / 100)
    profit = revenue - direct_costs - allocated_overhead
    margin_pct = round((profit / revenue) * 100, 2) if revenue else 0.0

    return ProfitabilityResult(
        revenue=revenue,
        direct_costs=direct_costs,
        allocated_overhead=round(allocated_overhead, 2),
        profit=round(profit, 2),
        margin_pct=margin_pct,
    )
