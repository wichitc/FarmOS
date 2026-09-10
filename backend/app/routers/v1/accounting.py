import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...accounting import models as acct_models
from ...accounting import schemas as acct_schemas
from ...accounting.profitability import compute_profitability
from ...accounting.service import post_ledger_entry
from ...core.deps import assert_farm_scope, require_permission
from ...database import get_db
from ...foundation import models as fm
from ...foundation.audit import record_audit

router = APIRouter(prefix="/api/v1/accounting", tags=["accounting"])

_HEATMAP_GROUP_BY_FIELDS = ("plot_id", "tree_id", "crop_id", "asset_twin_id", "cost_center_id")


def _get_or_404(db: Session, model, obj_id: str, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


# ---------------------------------------------------------------------------
# Cost centers (one of FR-ACC-001's eleven dimensions, the one with no
# existing master table elsewhere in the platform)
# ---------------------------------------------------------------------------

@router.post("/cost-centers", response_model=acct_schemas.CostCenterOut, status_code=201)
def create_cost_center(
    payload: acct_schemas.CostCenterCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("accounting.costcenter.manage")),
):
    cc = acct_models.CostCenter(
        tenant_id=current_user.tenant_id, code=payload.code, name=payload.name,
        created_by=current_user.id, updated_by=current_user.id,
    )
    db.add(cc)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A cost center with this code already exists") from exc

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="cost_center.create", entity_type="cost_center", entity_id=cc.id, new_values={"code": cc.code},
    )
    db.commit()
    return cc


@router.get("/cost-centers", response_model=list[acct_schemas.CostCenterOut])
def list_cost_centers(
    db: Session = Depends(get_db),
    _user: fm.User = Depends(require_permission("accounting.costcenter.view")),
):
    return db.query(acct_models.CostCenter).order_by(acct_models.CostCenter.name.asc()).all()


# ---------------------------------------------------------------------------
# Ledger (FR-ACC-001/002) - a flat postings ledger, not double-entry
# bookkeeping (see models.py's module docstring)
# ---------------------------------------------------------------------------

def _assert_dimension_farm_scope(db: Session, user: fm.User, permission_code: str, dimensions: dict) -> None:
    farm_id = dimensions.get("farm_id")
    if farm_id:
        assert_farm_scope(db, user, permission_code, farm_id)


@router.post("/ledger-entries", response_model=acct_schemas.LedgerEntryOut, status_code=201)
def post_entry(
    payload: acct_schemas.LedgerEntryCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("accounting.ledger.manage")),
):
    if payload.entry_type not in acct_models.ENTRY_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown entry_type '{payload.entry_type}'")
    if payload.direction not in acct_models.ENTRY_DIRECTIONS:
        raise HTTPException(status_code=422, detail=f"Unknown direction '{payload.direction}'")
    _assert_dimension_farm_scope(db, current_user, "accounting.ledger.manage", payload.dimensions)

    entry = post_ledger_entry(
        db,
        tenant_id=current_user.tenant_id,
        entry_type=payload.entry_type,
        direction=payload.direction,
        amount=payload.amount,
        dimensions=payload.dimensions,
        source_type=payload.source_type,
        source_id=payload.source_id,
        notes=payload.notes,
        posted_by=current_user.id,
    )
    if payload.posted_at:
        entry.posted_at = payload.posted_at

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="ledger_entry.post", entity_type="ledger_entry", entity_id=entry.id,
        new_values={"direction": entry.direction, "amount": entry.amount, "dimensions": entry.dimensions},
    )
    db.commit()
    return entry


@router.get("/ledger-entries", response_model=list[acct_schemas.LedgerEntryOut])
def list_ledger_entries(
    farm_id: Optional[str] = Query(default=None),
    season_id: Optional[str] = Query(default=None),
    plot_id: Optional[str] = Query(default=None),
    direction: Optional[str] = Query(default=None),
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("accounting.ledger.view")),
):
    if farm_id:
        assert_farm_scope(db, user, "accounting.ledger.view", farm_id)
    query = db.query(acct_models.LedgerEntry)
    dimension_filter = {}
    if farm_id:
        dimension_filter["farm_id"] = farm_id
    if season_id:
        dimension_filter["season_id"] = season_id
    if plot_id:
        dimension_filter["plot_id"] = plot_id
    if dimension_filter:
        query = query.filter(acct_models.LedgerEntry.dimensions.contains(dimension_filter))
    if direction:
        query = query.filter(acct_models.LedgerEntry.direction == direction)
    return query.order_by(acct_models.LedgerEntry.posted_at.desc()).limit(limit).all()


# ---------------------------------------------------------------------------
# Budgets (FR-ACC-002) - actual/variance always computed from the ledger,
# never a stored field that could drift.
# ---------------------------------------------------------------------------

@router.post("/budgets", response_model=acct_schemas.BudgetOut, status_code=201)
def create_budget(
    payload: acct_schemas.BudgetCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("accounting.budget.manage")),
):
    if payload.direction not in acct_models.ENTRY_DIRECTIONS:
        raise HTTPException(status_code=422, detail=f"Unknown direction '{payload.direction}'")
    _assert_dimension_farm_scope(db, current_user, "accounting.budget.manage", payload.dimensions)

    budget = acct_models.Budget(
        tenant_id=current_user.tenant_id, direction=payload.direction, amount=payload.amount,
        dimensions=payload.dimensions, period_start=payload.period_start, period_end=payload.period_end,
        notes=payload.notes, created_by=current_user.id, updated_by=current_user.id,
    )
    db.add(budget)
    db.flush()

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="budget.create", entity_type="budget", entity_id=budget.id,
        new_values={"direction": budget.direction, "amount": budget.amount, "dimensions": budget.dimensions},
    )
    db.commit()
    return budget


@router.get("/budgets", response_model=list[acct_schemas.BudgetOut])
def list_budgets(
    farm_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("accounting.budget.view")),
):
    if farm_id:
        assert_farm_scope(db, user, "accounting.budget.view", farm_id)
    query = db.query(acct_models.Budget)
    if farm_id:
        query = query.filter(acct_models.Budget.dimensions.contains({"farm_id": farm_id}))
    return query.order_by(acct_models.Budget.period_start.desc()).all()


@router.get("/budgets/{budget_id}/variance", response_model=acct_schemas.BudgetVarianceOut)
def budget_variance(
    budget_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("accounting.budget.view")),
):
    budget = _get_or_404(db, acct_models.Budget, budget_id, "Budget")
    _assert_dimension_farm_scope(db, user, "accounting.budget.view", budget.dimensions)

    actual_entries = (
        db.query(acct_models.LedgerEntry)
        .filter(
            acct_models.LedgerEntry.direction == budget.direction,
            acct_models.LedgerEntry.dimensions.contains(budget.dimensions),
            acct_models.LedgerEntry.posted_at >= budget.period_start,
            acct_models.LedgerEntry.posted_at <= budget.period_end,
        )
        .all()
    )
    actual = sum(e.amount for e in actual_entries)
    variance = actual - budget.amount
    variance_pct = round((variance / budget.amount) * 100, 2) if budget.amount else 0.0
    return acct_schemas.BudgetVarianceOut(
        budget_id=budget.id, budgeted_amount=budget.amount, actual_amount=actual,
        variance=round(variance, 2), variance_pct=variance_pct,
    )


# ---------------------------------------------------------------------------
# Profitability (FR-PROF-001/002)
# ---------------------------------------------------------------------------

@router.post("/profitability", response_model=acct_schemas.ProfitabilityOut)
def profitability(
    payload: acct_schemas.ProfitabilityRequest,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("accounting.ledger.view")),
):
    _assert_dimension_farm_scope(db, user, "accounting.ledger.view", payload.dimensions)
    result = compute_profitability(db, dimensions=payload.dimensions, overhead_allocation_pct=payload.overhead_allocation_pct)
    return acct_schemas.ProfitabilityOut(
        dimensions=payload.dimensions, revenue=result.revenue, direct_costs=result.direct_costs,
        allocated_overhead=result.allocated_overhead, profit=result.profit, margin_pct=result.margin_pct,
    )


@router.get("/profitability/heatmap", response_model=list[acct_schemas.ProfitabilityHeatmapRow])
def profitability_heatmap(
    farm_id: str,
    group_by: str,
    season_id: Optional[str] = Query(default=None),
    overhead_allocation_pct: float = Query(default=0.0),
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("accounting.ledger.view")),
):
    """FR-PROF-002's "profit heatmap over the spatial hierarchy" - this
    returns the underlying data (one row per `group_by` dimension value
    within the farm/season); rendering it as an actual heatmap is a
    frontend concern, same deferral as every other dashboard-shaped
    endpoint in this platform so far."""
    assert_farm_scope(db, user, "accounting.ledger.view", farm_id)
    if group_by not in _HEATMAP_GROUP_BY_FIELDS:
        raise HTTPException(status_code=422, detail=f"group_by must be one of {_HEATMAP_GROUP_BY_FIELDS}")

    base_filter = {"farm_id": farm_id}
    if season_id:
        base_filter["season_id"] = season_id

    rows = db.execute(
        text(f"SELECT DISTINCT dimensions->>'{group_by}' AS gid FROM ledger_entries WHERE dimensions @> :base"),
        {"base": json.dumps(base_filter)},
    ).all()

    results = []
    for row in rows:
        if row.gid is None:
            continue
        result = compute_profitability(
            db, dimensions={**base_filter, group_by: row.gid}, overhead_allocation_pct=overhead_allocation_pct
        )
        results.append(
            acct_schemas.ProfitabilityHeatmapRow(
                group_id=row.gid, revenue=result.revenue, direct_costs=result.direct_costs,
                profit=result.profit, margin_pct=result.margin_pct,
            )
        )
    return results
