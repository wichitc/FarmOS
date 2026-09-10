import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...ai.service import record_prediction
from ...core.deps import assert_farm_scope, require_permission, set_tenant_context
from ...database import get_db
from ...farm import models as farm_models
from ...foundation import models as fm
from ...foundation.audit import record_audit
from ...harvest import models as harvest_models
from ...harvest import schemas as harvest_schemas
from ...harvest.estimation import estimate_yield_range

router = APIRouter(prefix="/api/v1/harvest", tags=["harvest"])


def _get_or_404(db: Session, model, obj_id: str, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


def _new_qr_code() -> str:
    return secrets.token_urlsafe(16)


# ---------------------------------------------------------------------------
# Fruit lifecycle observations (FR-YIELD-001)
# ---------------------------------------------------------------------------

@router.post("/farms/{farm_id}/observations", response_model=harvest_schemas.FruitObservationOut, status_code=201)
def create_observation(
    farm_id: str,
    payload: harvest_schemas.FruitObservationCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("harvest.observation.manage")),
):
    farm = _get_or_404(db, farm_models.Farm, farm_id, "Farm")
    assert_farm_scope(db, current_user, "harvest.observation.manage", farm.id)
    tree = _get_or_404(db, farm_models.Tree, payload.tree_id, "Tree")
    if payload.stage not in harvest_models.FRUIT_STAGES:
        raise HTTPException(status_code=422, detail=f"Unknown stage '{payload.stage}'")

    observation = harvest_models.FruitObservation(
        tenant_id=current_user.tenant_id,
        tree_id=tree.id,
        stage=payload.stage,
        estimated_count=payload.estimated_count,
        observed_at=payload.observed_at or datetime.now(timezone.utc),
        notes=payload.notes,
        recorded_by=current_user.id,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(observation)
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="fruit_observation.create",
        entity_type="fruit_observation",
        entity_id=observation.id,
        new_values={"tree_id": tree.id, "stage": observation.stage},
    )
    db.commit()
    return observation


@router.get("/trees/{tree_id}/observations", response_model=list[harvest_schemas.FruitObservationOut])
def list_tree_observations(
    tree_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("harvest.observation.view")),
):
    tree = _get_or_404(db, farm_models.Tree, tree_id, "Tree")
    row = db.get(farm_models.Row, tree.row_id)
    block = db.get(farm_models.Block, row.block_id)
    plot = db.get(farm_models.Plot, block.plot_id)
    zone = db.get(farm_models.Zone, plot.zone_id)
    assert_farm_scope(db, user, "harvest.observation.view", zone.farm_id)
    return (
        db.query(harvest_models.FruitObservation)
        .filter(harvest_models.FruitObservation.tree_id == tree_id)
        .order_by(harvest_models.FruitObservation.observed_at.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Yield forecasts (FR-YIELD-002 - always a range)
# ---------------------------------------------------------------------------

@router.post("/farms/{farm_id}/yield-forecasts", response_model=harvest_schemas.YieldForecastOut, status_code=201)
def create_yield_forecast(
    farm_id: str,
    payload: harvest_schemas.YieldEstimateRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("harvest.yield.manage")),
):
    farm = _get_or_404(db, farm_models.Farm, farm_id, "Farm")
    assert_farm_scope(db, current_user, "harvest.yield.manage", farm.id)
    if payload.plot_id:
        _get_or_404(db, farm_models.Plot, payload.plot_id, "Plot")
    if payload.tree_id:
        _get_or_404(db, farm_models.Tree, payload.tree_id, "Tree")
    if payload.season_id:
        _get_or_404(db, farm_models.Season, payload.season_id, "Season")

    estimate = estimate_yield_range(
        tree_count=payload.tree_count,
        avg_fruit_count_per_tree=payload.avg_fruit_count_per_tree,
        avg_fruit_weight_kg=payload.avg_fruit_weight_kg,
        variability_pct=payload.variability_pct,
    )

    forecast = harvest_models.YieldForecast(
        tenant_id=current_user.tenant_id,
        farm_id=farm.id,
        plot_id=payload.plot_id,
        tree_id=payload.tree_id,
        season_id=payload.season_id,
        estimated_yield_kg_low=estimate.estimated_yield_kg_low,
        estimated_yield_kg_high=estimate.estimated_yield_kg_high,
        confidence=estimate.confidence,
        basis={
            "tree_count": payload.tree_count,
            "avg_fruit_count_per_tree": payload.avg_fruit_count_per_tree,
            "avg_fruit_weight_kg": payload.avg_fruit_weight_kg,
            "evidence": estimate.evidence,
        },
        forecast_date=datetime.now(timezone.utc),
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(forecast)
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="yield_forecast.create",
        entity_type="yield_forecast",
        entity_id=forecast.id,
        new_values={"farm_id": farm.id, "estimated_yield_kg_low": estimate.estimated_yield_kg_low, "estimated_yield_kg_high": estimate.estimated_yield_kg_high},
    )
    record_prediction(
        db,
        tenant_id=current_user.tenant_id,
        model_code="yield_estimation_rule_engine",
        entity_type="yield_forecast",
        entity_id=forecast.id,
        input_ref={
            "tree_count": payload.tree_count,
            "avg_fruit_count_per_tree": payload.avg_fruit_count_per_tree,
            "avg_fruit_weight_kg": payload.avg_fruit_weight_kg,
        },
        output={"estimated_yield_kg_low": estimate.estimated_yield_kg_low, "estimated_yield_kg_high": estimate.estimated_yield_kg_high},
        confidence=estimate.confidence,
        created_by=current_user.id,
    )
    db.commit()
    return forecast


@router.get("/farms/{farm_id}/yield-forecasts", response_model=list[harvest_schemas.YieldForecastOut])
def list_yield_forecasts(
    farm_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("harvest.yield.view")),
):
    assert_farm_scope(db, user, "harvest.yield.view", farm_id)
    return (
        db.query(harvest_models.YieldForecast)
        .filter(harvest_models.YieldForecast.farm_id == farm_id)
        .order_by(harvest_models.YieldForecast.forecast_date.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Harvest lots / Packing lots (FR-HARV-001/002)
# ---------------------------------------------------------------------------

@router.post("/farms/{farm_id}/harvest-lots", response_model=harvest_schemas.HarvestLotOut, status_code=201)
def create_harvest_lot(
    farm_id: str,
    payload: harvest_schemas.HarvestLotCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("harvest.lot.manage")),
):
    farm = _get_or_404(db, farm_models.Farm, farm_id, "Farm")
    assert_farm_scope(db, current_user, "harvest.lot.manage", farm.id)
    if payload.plot_id:
        _get_or_404(db, farm_models.Plot, payload.plot_id, "Plot")
    if payload.tree_id:
        _get_or_404(db, farm_models.Tree, payload.tree_id, "Tree")

    lot = harvest_models.HarvestLot(
        tenant_id=current_user.tenant_id,
        farm_id=farm.id,
        plot_id=payload.plot_id,
        tree_id=payload.tree_id,
        season_id=payload.season_id,
        qr_code=_new_qr_code(),
        harvested_at=payload.harvested_at or datetime.now(timezone.utc),
        quantity_kg=payload.quantity_kg,
        grade=payload.grade,
        harvested_by=current_user.id,
        notes=payload.notes,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(lot)
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="harvest_lot.create",
        entity_type="harvest_lot",
        entity_id=lot.id,
        new_values={"farm_id": farm.id, "quantity_kg": lot.quantity_kg},
    )
    db.commit()
    return lot


@router.get("/farms/{farm_id}/harvest-lots", response_model=list[harvest_schemas.HarvestLotOut])
def list_harvest_lots(
    farm_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("harvest.lot.view")),
):
    assert_farm_scope(db, user, "harvest.lot.view", farm_id)
    return (
        db.query(harvest_models.HarvestLot)
        .filter(harvest_models.HarvestLot.farm_id == farm_id)
        .order_by(harvest_models.HarvestLot.harvested_at.desc())
        .all()
    )


@router.get("/farms/{farm_id}/yield-summary")
def yield_summary(
    farm_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("harvest.lot.view")),
):
    """Roll-up per FR-YIELD-001 ("counts/estimates rolled up Tree -> Row ->
    Plot -> Farm -> Crop -> Season") - a live aggregation query over
    `HarvestLot`, not a separately maintained rollup table."""
    assert_farm_scope(db, user, "harvest.lot.view", farm_id)
    rows = (
        db.query(
            harvest_models.HarvestLot.plot_id,
            harvest_models.HarvestLot.season_id,
            func.sum(harvest_models.HarvestLot.quantity_kg).label("total_kg"),
            func.count(harvest_models.HarvestLot.id).label("lot_count"),
        )
        .filter(harvest_models.HarvestLot.farm_id == farm_id)
        .group_by(harvest_models.HarvestLot.plot_id, harvest_models.HarvestLot.season_id)
        .all()
    )
    return [
        {"plot_id": r.plot_id, "season_id": r.season_id, "total_kg": r.total_kg, "lot_count": r.lot_count}
        for r in rows
    ]


@router.post("/farms/{farm_id}/packing-lots", response_model=harvest_schemas.PackingLotOut, status_code=201)
def create_packing_lot(
    farm_id: str,
    payload: harvest_schemas.PackingLotCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("harvest.lot.manage")),
):
    farm = _get_or_404(db, farm_models.Farm, farm_id, "Farm")
    assert_farm_scope(db, current_user, "harvest.lot.manage", farm.id)
    if not payload.harvest_lot_ids:
        raise HTTPException(status_code=422, detail="At least one harvest_lot_id is required")

    harvest_lots = []
    for harvest_lot_id in payload.harvest_lot_ids:
        lot = _get_or_404(db, harvest_models.HarvestLot, harvest_lot_id, "Harvest lot")
        if lot.farm_id != farm.id:
            raise HTTPException(status_code=422, detail=f"Harvest lot {harvest_lot_id} does not belong to this farm")
        harvest_lots.append(lot)

    packing_lot = harvest_models.PackingLot(
        tenant_id=current_user.tenant_id,
        farm_id=farm.id,
        qr_code=_new_qr_code(),
        packed_at=payload.packed_at or datetime.now(timezone.utc),
        packed_by=current_user.id,
        notes=payload.notes,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(packing_lot)
    db.flush()

    for lot in harvest_lots:
        db.add(
            harvest_models.PackingLotItem(
                tenant_id=current_user.tenant_id,
                packing_lot_id=packing_lot.id,
                harvest_lot_id=lot.id,
                created_by=current_user.id,
                updated_by=current_user.id,
            )
        )

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="packing_lot.create",
        entity_type="packing_lot",
        entity_id=packing_lot.id,
        new_values={"farm_id": farm.id, "harvest_lot_ids": payload.harvest_lot_ids},
    )
    db.commit()
    return packing_lot


@router.get("/farms/{farm_id}/packing-lots", response_model=list[harvest_schemas.PackingLotOut])
def list_packing_lots(
    farm_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("harvest.lot.view")),
):
    assert_farm_scope(db, user, "harvest.lot.view", farm_id)
    return (
        db.query(harvest_models.PackingLot)
        .filter(harvest_models.PackingLot.farm_id == farm_id)
        .order_by(harvest_models.PackingLot.packed_at.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Consumer-facing traceability (FR-HARV-002) - deliberately PUBLIC, no auth:
# a shopper scanning a QR code on packaging is not a logged-in platform
# user. `tenant_slug` in the path plays the same "which tenant" role it
# already plays in POST /api/v1/auth/login; only traceability-safe fields
# are exposed (no user IDs, no internal notes/cost data).
# ---------------------------------------------------------------------------

@router.get("/trace/{tenant_slug}/{qr_code}", response_model=harvest_schemas.TraceOut)
def trace_qr_code(tenant_slug: str, qr_code: str, db: Session = Depends(get_db)):
    tenant = db.query(fm.Tenant).filter(fm.Tenant.slug == tenant_slug).one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Not found")
    set_tenant_context(db, tenant.id)

    packing_lot = db.query(harvest_models.PackingLot).filter(harvest_models.PackingLot.qr_code == qr_code).one_or_none()
    if packing_lot is None:
        # Fall back to a direct harvest-lot QR (sold unpacked).
        harvest_lot = db.query(harvest_models.HarvestLot).filter(harvest_models.HarvestLot.qr_code == qr_code).one_or_none()
        if harvest_lot is None:
            raise HTTPException(status_code=404, detail="Not found")
        farm = db.get(farm_models.Farm, harvest_lot.farm_id)
        return harvest_schemas.TraceOut(
            packing_lot_qr=qr_code,
            packed_at=harvest_lot.harvested_at,
            farm_name=farm.name,
            harvest_lots=[_trace_harvest_lot_out(db, harvest_lot)],
        )

    farm = db.get(farm_models.Farm, packing_lot.farm_id)
    items = db.query(harvest_models.PackingLotItem).filter(harvest_models.PackingLotItem.packing_lot_id == packing_lot.id).all()
    harvest_lots = [db.get(harvest_models.HarvestLot, item.harvest_lot_id) for item in items]

    return harvest_schemas.TraceOut(
        packing_lot_qr=packing_lot.qr_code,
        packed_at=packing_lot.packed_at,
        farm_name=farm.name,
        harvest_lots=[_trace_harvest_lot_out(db, lot) for lot in harvest_lots if lot],
    )


def _trace_harvest_lot_out(db: Session, lot: harvest_models.HarvestLot) -> harvest_schemas.TraceHarvestLotOut:
    plot = db.get(farm_models.Plot, lot.plot_id) if lot.plot_id else None
    tree = db.get(farm_models.Tree, lot.tree_id) if lot.tree_id else None
    return harvest_schemas.TraceHarvestLotOut(
        quantity_kg=lot.quantity_kg,
        grade=lot.grade,
        harvested_at=lot.harvested_at,
        plot_code=plot.code if plot else None,
        plot_name=plot.name if plot else None,
        tree_code=tree.code if tree else None,
    )
