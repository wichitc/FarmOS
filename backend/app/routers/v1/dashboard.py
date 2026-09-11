from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...core.deps import assert_farm_scope, require_permission
from ...dashboard import aggregation
from ...dashboard import schemas as dash_schemas
from ...database import get_db
from ...farm import models as farm_models
from ...foundation import models as fm

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


def _get_or_404(db: Session, model, obj_id: str, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


@router.get("/fleet-summary", response_model=dash_schemas.FleetSummary)
def get_fleet_summary(
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("dashboard.view")),
):
    """FR-DASH-003: tenant-wide fleet/equipment health + inventory + agent
    recommendations rollup. Not narrowed per-farm (matches the existing
    `GET /assets` convention: unscoped unless a `farm_id` filter is given -
    there is none here, this endpoint is inherently tenant-wide)."""
    return aggregation.fleet_summary(db, current_user.tenant_id)


@router.get("/farms/{farm_id}/summary", response_model=dash_schemas.FarmCommandCenterSummary)
def get_farm_summary(
    farm_id: str,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("dashboard.view")),
):
    """FR-DASH-001's per-farm widget rollup. Map/3D-viewer and drag-and-drop
    widget layout persistence (FR-DASH-002) are frontend concerns - out of
    scope for a backend-only build."""
    farm = _get_or_404(db, farm_models.Farm, farm_id, "Farm")
    assert_farm_scope(db, current_user, "dashboard.view", farm.id)
    return aggregation.farm_summary(db, current_user.tenant_id, farm.id)
