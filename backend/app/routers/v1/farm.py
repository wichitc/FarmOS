import csv
import io
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.deps import assert_farm_scope, require_permission
from ...database import get_db
from ...farm import models as farm_models
from ...farm import schemas as farm_schemas
from ...foundation import models as fm
from ...foundation.audit import record_audit

router = APIRouter(prefix="/api/v1/farm", tags=["farm"])


# ---------------------------------------------------------------------------
# Hierarchy lookups - each level stores only its immediate parent FK, so
# resolving the owning Farm (needed for ABAC scope checks and tree-code
# composition) walks the chain via the ORM relationships defined in
# app/farm/models.py.
# ---------------------------------------------------------------------------

def _get_or_404(db: Session, model, obj_id: str, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


def _farm_for_zone(zone: farm_models.Zone) -> farm_models.Farm:
    return zone.farm


def _farm_for_plot(plot: farm_models.Plot) -> farm_models.Farm:
    return plot.zone.farm


def _farm_for_block(block: farm_models.Block) -> farm_models.Farm:
    return block.plot.zone.farm


def _hierarchy_for_row(row: farm_models.Row):
    block = row.block
    plot = block.plot
    zone = plot.zone
    farm = zone.farm
    return farm, block, plot, zone


def _hierarchy_for_tree(tree: farm_models.Tree):
    return _hierarchy_for_row(tree.row)


# ---------------------------------------------------------------------------
# Farms
# ---------------------------------------------------------------------------

@router.post("/farms", response_model=farm_schemas.FarmOut, status_code=201)
def create_farm(
    payload: farm_schemas.FarmCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("farm.manage")),
):
    farm = farm_models.Farm(
        tenant_id=current_user.tenant_id,
        code=payload.code,
        name=payload.name,
        lat=payload.lat,
        lng=payload.lng,
        area_hectares=payload.area_hectares,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(farm)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A farm with this code already exists") from exc

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="farm.create",
        entity_type="farm",
        entity_id=farm.id,
        new_values={"code": farm.code, "name": farm.name},
    )
    db.commit()
    return farm


@router.get("/farms", response_model=list[farm_schemas.FarmOut])
def list_farms(
    db: Session = Depends(get_db),
    _user: fm.User = Depends(require_permission("farm.view")),
):
    return db.query(farm_models.Farm).order_by(farm_models.Farm.name.asc()).all()


@router.get("/farms/{farm_id}", response_model=farm_schemas.FarmOut)
def get_farm(
    farm_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("farm.view")),
):
    farm = _get_or_404(db, farm_models.Farm, farm_id, "Farm")
    assert_farm_scope(db, user, "farm.view", farm.id)
    return farm


# ---------------------------------------------------------------------------
# Zones / Plots / Blocks / Rows - identical create+list shape at each level
# ---------------------------------------------------------------------------

@router.post("/farms/{farm_id}/zones", response_model=farm_schemas.ZoneOut, status_code=201)
def create_zone(
    farm_id: str,
    payload: farm_schemas.ZoneCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("farm.manage")),
):
    farm = _get_or_404(db, farm_models.Farm, farm_id, "Farm")
    assert_farm_scope(db, current_user, "farm.manage", farm.id)

    zone = farm_models.Zone(
        tenant_id=current_user.tenant_id,
        farm_id=farm.id,
        code=payload.code,
        name=payload.name,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(zone)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A zone with this code already exists in this farm") from exc

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="zone.create",
        entity_type="zone",
        entity_id=zone.id,
        new_values={"farm_id": farm.id, "code": zone.code},
    )
    db.commit()
    return zone


@router.get("/farms/{farm_id}/zones", response_model=list[farm_schemas.ZoneOut])
def list_zones(
    farm_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("farm.view")),
):
    farm = _get_or_404(db, farm_models.Farm, farm_id, "Farm")
    assert_farm_scope(db, user, "farm.view", farm.id)
    return db.query(farm_models.Zone).filter(farm_models.Zone.farm_id == farm_id).order_by(farm_models.Zone.code.asc()).all()


@router.post("/zones/{zone_id}/plots", response_model=farm_schemas.PlotOut, status_code=201)
def create_plot(
    zone_id: str,
    payload: farm_schemas.PlotCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("farm.manage")),
):
    zone = _get_or_404(db, farm_models.Zone, zone_id, "Zone")
    assert_farm_scope(db, current_user, "farm.manage", _farm_for_zone(zone).id)

    plot = farm_models.Plot(
        tenant_id=current_user.tenant_id,
        zone_id=zone.id,
        code=payload.code,
        name=payload.name,
        area_hectares=payload.area_hectares,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(plot)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A plot with this code already exists in this zone") from exc

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="plot.create",
        entity_type="plot",
        entity_id=plot.id,
        new_values={"zone_id": zone.id, "code": plot.code},
    )
    db.commit()
    return plot


@router.get("/zones/{zone_id}/plots", response_model=list[farm_schemas.PlotOut])
def list_plots(
    zone_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("farm.view")),
):
    zone = _get_or_404(db, farm_models.Zone, zone_id, "Zone")
    assert_farm_scope(db, user, "farm.view", _farm_for_zone(zone).id)
    return db.query(farm_models.Plot).filter(farm_models.Plot.zone_id == zone_id).order_by(farm_models.Plot.code.asc()).all()


@router.post("/plots/{plot_id}/blocks", response_model=farm_schemas.BlockOut, status_code=201)
def create_block(
    plot_id: str,
    payload: farm_schemas.BlockCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("farm.manage")),
):
    plot = _get_or_404(db, farm_models.Plot, plot_id, "Plot")
    assert_farm_scope(db, current_user, "farm.manage", _farm_for_plot(plot).id)

    block = farm_models.Block(
        tenant_id=current_user.tenant_id,
        plot_id=plot.id,
        code=payload.code,
        name=payload.name,
        area_hectares=payload.area_hectares,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(block)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A block with this code already exists in this plot") from exc

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="block.create",
        entity_type="block",
        entity_id=block.id,
        new_values={"plot_id": plot.id, "code": block.code},
    )
    db.commit()
    return block


@router.get("/plots/{plot_id}/blocks", response_model=list[farm_schemas.BlockOut])
def list_blocks(
    plot_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("farm.view")),
):
    plot = _get_or_404(db, farm_models.Plot, plot_id, "Plot")
    assert_farm_scope(db, user, "farm.view", _farm_for_plot(plot).id)
    return db.query(farm_models.Block).filter(farm_models.Block.plot_id == plot_id).order_by(farm_models.Block.code.asc()).all()


@router.post("/blocks/{block_id}/rows", response_model=farm_schemas.RowOut, status_code=201)
def create_row(
    block_id: str,
    payload: farm_schemas.RowCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("farm.manage")),
):
    block = _get_or_404(db, farm_models.Block, block_id, "Block")
    assert_farm_scope(db, current_user, "farm.manage", _farm_for_block(block).id)

    row = farm_models.Row(
        tenant_id=current_user.tenant_id,
        block_id=block.id,
        code=payload.code,
        name=payload.name,
        spacing_m=payload.spacing_m,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A row with this code already exists in this block") from exc

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="row.create",
        entity_type="row",
        entity_id=row.id,
        new_values={"block_id": block.id, "code": row.code},
    )
    db.commit()
    return row


@router.get("/blocks/{block_id}/rows", response_model=list[farm_schemas.RowOut])
def list_rows(
    block_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("farm.view")),
):
    block = _get_or_404(db, farm_models.Block, block_id, "Block")
    assert_farm_scope(db, user, "farm.view", _farm_for_block(block).id)
    return db.query(farm_models.Row).filter(farm_models.Row.block_id == block_id).order_by(farm_models.Row.code.asc()).all()


# ---------------------------------------------------------------------------
# Trees
# ---------------------------------------------------------------------------

def _next_tree_seq(db: Session, row_id: str) -> int:
    return db.query(farm_models.Tree).filter(farm_models.Tree.row_id == row_id).count() + 1


def _default_tree_code(farm: farm_models.Farm, block: farm_models.Block, row: farm_models.Row, seq: int, crop: fm.Crop, variety: Optional[fm.Variety]) -> str:
    species = (variety.code if variety else crop.code).upper()
    return f"{farm.code}-{species}-{block.code}-{row.code}-T{seq:03d}"


def _resolve_crop_variety(db: Session, crop_id: str, variety_id: Optional[str]) -> tuple[fm.Crop, Optional[fm.Variety]]:
    crop = db.get(fm.Crop, crop_id)
    if crop is None:
        raise HTTPException(status_code=404, detail="Crop not found")
    variety = None
    if variety_id:
        variety = db.get(fm.Variety, variety_id)
        if variety is None or variety.crop_id != crop_id:
            raise HTTPException(status_code=404, detail="Variety not found for this crop")
    return crop, variety


def _build_tree(
    db: Session,
    *,
    row: farm_models.Row,
    farm: farm_models.Farm,
    block: farm_models.Block,
    current_user: fm.User,
    payload: farm_schemas.TreeCreate,
    seq: int,
) -> farm_models.Tree:
    crop, variety = _resolve_crop_variety(db, payload.crop_id, payload.variety_id)
    code = payload.code or _default_tree_code(farm, block, row, seq, crop, variety)
    return farm_models.Tree(
        tenant_id=current_user.tenant_id,
        row_id=row.id,
        crop_id=crop.id,
        variety_id=variety.id if variety else None,
        code=code,
        planting_date=payload.planting_date,
        rootstock=payload.rootstock,
        height_m=payload.height_m,
        canopy_diameter_m=payload.canopy_diameter_m,
        trunk_diameter_cm=payload.trunk_diameter_cm,
        growth_stage=payload.growth_stage,
        lat=payload.lat,
        lng=payload.lng,
        notes=payload.notes,
        created_by=current_user.id,
        updated_by=current_user.id,
    )


@router.post("/rows/{row_id}/trees", response_model=farm_schemas.TreeOut, status_code=201)
def create_tree(
    row_id: str,
    payload: farm_schemas.TreeCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("tree.manage")),
):
    row = _get_or_404(db, farm_models.Row, row_id, "Row")
    farm, block, _plot, _zone = _hierarchy_for_row(row)
    assert_farm_scope(db, current_user, "tree.manage", farm.id)

    tree = _build_tree(db, row=row, farm=farm, block=block, current_user=current_user, payload=payload, seq=_next_tree_seq(db, row.id))
    db.add(tree)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A tree with this code already exists") from exc

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="tree.create",
        entity_type="tree",
        entity_id=tree.id,
        new_values={"row_id": row.id, "code": tree.code},
    )
    db.commit()
    return tree


@router.get("/rows/{row_id}/trees", response_model=list[farm_schemas.TreeOut])
def list_trees(
    row_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("tree.view")),
):
    row = _get_or_404(db, farm_models.Row, row_id, "Row")
    farm, _block, _plot, _zone = _hierarchy_for_row(row)
    assert_farm_scope(db, user, "tree.view", farm.id)
    return (
        db.query(farm_models.Tree)
        .filter(farm_models.Tree.row_id == row_id, farm_models.Tree.deleted_at.is_(None))
        .order_by(farm_models.Tree.code.asc())
        .all()
    )


@router.post("/rows/{row_id}/trees/bulk", response_model=list[farm_schemas.TreeOut], status_code=201)
def bulk_create_trees(
    row_id: str,
    payload: farm_schemas.TreeBulkCreateRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("tree.manage")),
):
    row = _get_or_404(db, farm_models.Row, row_id, "Row")
    farm, block, _plot, _zone = _hierarchy_for_row(row)
    assert_farm_scope(db, current_user, "tree.manage", farm.id)

    seq = _next_tree_seq(db, row.id)
    trees = []
    for tree_payload in payload.trees:
        tree = _build_tree(db, row=row, farm=farm, block=block, current_user=current_user, payload=tree_payload, seq=seq)
        db.add(tree)
        trees.append(tree)
        seq += 1

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="One or more tree codes already exist") from exc

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="tree.bulk_create",
        entity_type="tree",
        entity_id=row.id,
        new_values={"row_id": row.id, "count": len(trees)},
    )
    db.commit()
    return trees


@router.post("/rows/{row_id}/trees/import-csv", response_model=list[farm_schemas.TreeOut], status_code=201)
async def import_trees_csv(
    row_id: str,
    file: UploadFile,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("tree.manage")),
):
    """FR-FARM-006 bulk import. Expected columns: crop_code (required),
    variety_code, code, planting_date (YYYY-MM-DD), lat, lng, rootstock,
    height_m, canopy_diameter_m, trunk_diameter_cm, growth_stage, notes."""
    row = _get_or_404(db, farm_models.Row, row_id, "Row")
    farm, block, _plot, _zone = _hierarchy_for_row(row)
    assert_farm_scope(db, current_user, "tree.manage", farm.id)

    raw = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))

    seq = _next_tree_seq(db, row.id)
    trees = []
    for line_no, csv_row in enumerate(reader, start=2):
        crop_code = (csv_row.get("crop_code") or "").strip()
        if not crop_code:
            raise HTTPException(status_code=422, detail=f"Row {line_no}: crop_code is required")
        crop = db.query(fm.Crop).filter(fm.Crop.code == crop_code).one_or_none()
        if crop is None:
            raise HTTPException(status_code=422, detail=f"Row {line_no}: unknown crop_code '{crop_code}'")

        variety_id = None
        variety_code = (csv_row.get("variety_code") or "").strip()
        if variety_code:
            variety = (
                db.query(fm.Variety)
                .filter(fm.Variety.crop_id == crop.id, fm.Variety.code == variety_code)
                .one_or_none()
            )
            if variety is None:
                raise HTTPException(status_code=422, detail=f"Row {line_no}: unknown variety_code '{variety_code}' for crop '{crop_code}'")
            variety_id = variety.id

        def _f(key: str) -> Optional[float]:
            value = (csv_row.get(key) or "").strip()
            return float(value) if value else None

        payload = farm_schemas.TreeCreate(
            crop_id=crop.id,
            variety_id=variety_id,
            code=(csv_row.get("code") or "").strip() or None,
            planting_date=(csv_row.get("planting_date") or "").strip() or None,
            rootstock=(csv_row.get("rootstock") or "").strip() or None,
            height_m=_f("height_m"),
            canopy_diameter_m=_f("canopy_diameter_m"),
            trunk_diameter_cm=_f("trunk_diameter_cm"),
            growth_stage=(csv_row.get("growth_stage") or "seedling").strip(),
            lat=_f("lat"),
            lng=_f("lng"),
            notes=(csv_row.get("notes") or "").strip() or None,
        )
        tree = _build_tree(db, row=row, farm=farm, block=block, current_user=current_user, payload=payload, seq=seq)
        db.add(tree)
        trees.append(tree)
        seq += 1

    if not trees:
        raise HTTPException(status_code=422, detail="CSV contained no data rows")

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="One or more tree codes already exist") from exc

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="tree.import_csv",
        entity_type="tree",
        entity_id=row.id,
        new_values={"row_id": row.id, "count": len(trees)},
    )
    db.commit()
    return trees


@router.post("/rows/{row_id}/trees/generate-grid", response_model=list[farm_schemas.TreeOut], status_code=201)
def generate_tree_grid(
    row_id: str,
    payload: farm_schemas.TreeGridGenerateRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("tree.manage")),
):
    """FR-FARM-006 grid-spacing generation: lays out `count` trees along the
    row, `spacing_m` apart, starting from (start_lat, start_lng) if given.
    `spacing_m` is treated as a straight offset in degrees-of-latitude*1e-5
    scale placeholder - real geodesic placement (bearing along the row's
    actual orientation) is a Phase 5 GIS concern once plot/row polygons
    exist; this satisfies FR-FARM-006 without inventing spatial math Phase 5
    will own."""
    if payload.count < 1:
        raise HTTPException(status_code=422, detail="count must be at least 1")

    row = _get_or_404(db, farm_models.Row, row_id, "Row")
    farm, block, _plot, _zone = _hierarchy_for_row(row)
    assert_farm_scope(db, current_user, "tree.manage", farm.id)

    seq = _next_tree_seq(db, row.id)
    trees = []
    for i in range(payload.count):
        lat = payload.start_lat + (i * payload.spacing_m * 1e-5) if payload.start_lat is not None else None
        lng = payload.start_lng
        tree_payload = farm_schemas.TreeCreate(
            crop_id=payload.crop_id,
            variety_id=payload.variety_id,
            planting_date=payload.planting_date,
            lat=lat,
            lng=lng,
        )
        tree = _build_tree(db, row=row, farm=farm, block=block, current_user=current_user, payload=tree_payload, seq=seq)
        db.add(tree)
        trees.append(tree)
        seq += 1

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="One or more generated tree codes already exist") from exc

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="tree.generate_grid",
        entity_type="tree",
        entity_id=row.id,
        new_values={"row_id": row.id, "count": len(trees)},
    )
    db.commit()
    return trees


@router.get("/trees/{tree_id}", response_model=farm_schemas.TreeOut)
def get_tree(
    tree_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("tree.view")),
):
    tree = _get_or_404(db, farm_models.Tree, tree_id, "Tree")
    farm, _block, _plot, _zone = _hierarchy_for_tree(tree)
    assert_farm_scope(db, user, "tree.view", farm.id)
    return tree


@router.patch("/trees/{tree_id}", response_model=farm_schemas.TreeOut)
def update_tree(
    tree_id: str,
    payload: farm_schemas.TreeUpdate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("tree.manage")),
):
    tree = _get_or_404(db, farm_models.Tree, tree_id, "Tree")
    farm, _block, _plot, _zone = _hierarchy_for_tree(tree)
    assert_farm_scope(db, current_user, "tree.manage", farm.id)

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(tree, field, value)
    tree.updated_by = current_user.id

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A tree with this code already exists") from exc

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="tree.update",
        entity_type="tree",
        entity_id=tree.id,
        new_values=changes,
    )
    db.commit()
    return tree


@router.delete("/trees/{tree_id}", status_code=204)
def delete_tree(
    tree_id: str,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("tree.manage")),
):
    tree = _get_or_404(db, farm_models.Tree, tree_id, "Tree")
    farm, _block, _plot, _zone = _hierarchy_for_tree(tree)
    assert_farm_scope(db, current_user, "tree.manage", farm.id)

    tree.deleted_at = datetime.now(timezone.utc)
    tree.updated_by = current_user.id
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="tree.delete",
        entity_type="tree",
        entity_id=tree.id,
    )
    db.commit()


# ---------------------------------------------------------------------------
# Tree events (FR-FARM-007) - append-only, no update/delete route exposed.
# ---------------------------------------------------------------------------

@router.post("/trees/{tree_id}/events", response_model=farm_schemas.TreeEventOut, status_code=201)
def record_tree_event(
    tree_id: str,
    payload: farm_schemas.TreeEventCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("tree.event.record")),
):
    tree = _get_or_404(db, farm_models.Tree, tree_id, "Tree")
    farm, _block, _plot, _zone = _hierarchy_for_tree(tree)
    assert_farm_scope(db, current_user, "tree.event.record", farm.id)

    event = farm_models.TreeEvent(
        tenant_id=current_user.tenant_id,
        tree_id=tree.id,
        event_type=payload.event_type,
        payload=payload.payload,
        occurred_at=payload.occurred_at or datetime.now(timezone.utc),
        created_by=current_user.id,
    )
    db.add(event)
    db.flush()
    db.commit()
    return event


@router.get("/trees/{tree_id}/events", response_model=list[farm_schemas.TreeEventOut])
def list_tree_events(
    tree_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("tree.view")),
):
    tree = _get_or_404(db, farm_models.Tree, tree_id, "Tree")
    farm, _block, _plot, _zone = _hierarchy_for_tree(tree)
    assert_farm_scope(db, user, "tree.view", farm.id)
    return (
        db.query(farm_models.TreeEvent)
        .filter(farm_models.TreeEvent.tree_id == tree_id)
        .order_by(farm_models.TreeEvent.occurred_at.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Seasons
# ---------------------------------------------------------------------------

@router.post("/farms/{farm_id}/seasons", response_model=farm_schemas.SeasonOut, status_code=201)
def create_season(
    farm_id: str,
    payload: farm_schemas.SeasonCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("season.manage")),
):
    farm = _get_or_404(db, farm_models.Farm, farm_id, "Farm")
    assert_farm_scope(db, current_user, "season.manage", farm.id)

    season = farm_models.Season(
        tenant_id=current_user.tenant_id,
        farm_id=farm.id,
        name=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(season)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A season with this name already exists for this farm") from exc

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="season.create",
        entity_type="season",
        entity_id=season.id,
        new_values={"farm_id": farm.id, "name": season.name},
    )
    db.commit()
    return season


@router.get("/farms/{farm_id}/seasons", response_model=list[farm_schemas.SeasonOut])
def list_seasons(
    farm_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("season.view")),
):
    farm = _get_or_404(db, farm_models.Farm, farm_id, "Farm")
    assert_farm_scope(db, user, "season.view", farm.id)
    return db.query(farm_models.Season).filter(farm_models.Season.farm_id == farm_id).order_by(farm_models.Season.start_date.desc()).all()
