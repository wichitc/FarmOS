from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ...ai.service import record_prediction
from ...asset import models as asset_models
from ...asset import schemas as asset_schemas
from ...asset.health_engine import assess_asset_health
from ...core.deps import assert_farm_scope, require_permission
from ...database import get_db
from ...farm import models as farm_models
from ...foundation import models as fm
from ...foundation import workflow_engine
from ...foundation.audit import record_audit
from ...twins import models as twin_models
from ...twins.service import create_twin

router = APIRouter(prefix="/api/v1", tags=["assets"])


def _get_or_404(db: Session, model, obj_id: str, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


def _assert_optional_farm_scope(db: Session, user: fm.User, permission_code: str, farm_id: Optional[str]) -> None:
    """Same rationale as `routers.v1.twins._assert_twin_scope` - an asset
    twin's `farm_id` is nullable (mirrors legacy `Equipment.model_id IS NULL`
    = unscoped), so only narrow with `assert_farm_scope` when there's an
    actual farm to narrow to."""
    if farm_id is not None:
        assert_farm_scope(db, user, permission_code, farm_id)


def _correlation_id(request: Request) -> str:
    return request.headers.get("x-correlation-id", "")


def _set_property(db: Session, *, tenant_id: str, twin_id: str, key: str, value, actor_id: str) -> None:
    if value is None:
        return
    db.add(
        twin_models.TwinProperty(
            tenant_id=tenant_id,
            twin_id=twin_id,
            key=key,
            value=value.isoformat() if hasattr(value, "isoformat") else value,
            created_by=actor_id,
            updated_by=actor_id,
        )
    )


# ---------------------------------------------------------------------------
# Assets (FR-ASSET-001) - a thin registration wrapper over DigitalTwin +
# TwinProperty (ADR-004); no parallel Asset table.
# ---------------------------------------------------------------------------

@router.post("/assets", response_model=asset_schemas.AssetOut, status_code=201)
def register_asset(
    payload: asset_schemas.AssetRegisterRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("asset.manage")),
):
    if payload.farm_id:
        farm = _get_or_404(db, farm_models.Farm, payload.farm_id, "Farm")
        assert_farm_scope(db, current_user, "asset.manage", farm.id)
    twin_type = _get_or_404(db, twin_models.TwinType, payload.twin_type_id, "Twin type")

    twin = create_twin(
        db,
        tenant_id=current_user.tenant_id,
        twin_type=twin_type,
        display_code=payload.display_code,
        farm_id=payload.farm_id,
        current_state=payload.initial_state,
        created_by=current_user.id,
    )

    for key, value in {
        "manufacturer": payload.manufacturer,
        "model": payload.model,
        "serial_no": payload.serial_no,
        "install_date": payload.install_date,
        "warranty_until": payload.warranty_until,
        "documents": payload.documents or None,
    }.items():
        _set_property(db, tenant_id=current_user.tenant_id, twin_id=twin.id, key=key, value=value, actor_id=current_user.id)
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="asset.register",
        entity_type="digital_twin",
        entity_id=twin.id,
        new_values={"display_code": twin.display_code, "twin_type_id": twin_type.id},
    )
    # Read the properties back before commit: `db.commit()` ends the
    # transaction `set_tenant_context` scoped its is_local=true RLS setting
    # to, so a SELECT issued after commit on this same session would be
    # denied - same pitfall documented in `core/deps.py`'s
    # `set_tenant_context` and hit for real in Phase 7's tests.
    asset_out = _asset_out(db, twin)
    db.commit()
    return asset_out


def _asset_out(db: Session, twin: twin_models.DigitalTwin) -> asset_schemas.AssetOut:
    properties = {
        p.key: p.value
        for p in db.query(twin_models.TwinProperty).filter(twin_models.TwinProperty.twin_id == twin.id).all()
    }
    return asset_schemas.AssetOut(
        id=twin.id,
        twin_type_id=twin.twin_type_id,
        farm_id=twin.farm_id,
        display_code=twin.display_code,
        current_state=twin.current_state,
        status=twin.status,
        properties=properties,
    )


@router.get("/assets", response_model=list[asset_schemas.AssetOut])
def list_assets(
    farm_id: Optional[str] = Query(default=None),
    twin_type_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("asset.view")),
):
    if farm_id:
        assert_farm_scope(db, user, "asset.view", farm_id)
    query = db.query(twin_models.DigitalTwin).filter(twin_models.DigitalTwin.deleted_at.is_(None))
    if farm_id:
        query = query.filter(twin_models.DigitalTwin.farm_id == farm_id)
    if twin_type_id:
        query = query.filter(twin_models.DigitalTwin.twin_type_id == twin_type_id)
    else:
        asset_type_ids = [t.id for t in db.query(twin_models.TwinType).filter(twin_models.TwinType.category == "asset").all()]
        if not asset_type_ids:
            return []
        query = query.filter(twin_models.DigitalTwin.twin_type_id.in_(asset_type_ids))
    return [_asset_out(db, twin) for twin in query.order_by(twin_models.DigitalTwin.display_code.asc()).all()]


@router.get("/assets/{twin_id}", response_model=asset_schemas.AssetOut)
def get_asset(
    twin_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("asset.view")),
):
    twin = _get_or_404(db, twin_models.DigitalTwin, twin_id, "Asset")
    _assert_optional_farm_scope(db, user, "asset.view", twin.farm_id)
    return _asset_out(db, twin)


# ---------------------------------------------------------------------------
# Predictive maintenance health assessments (FR-PDM-001/002 - Prediction +
# Recommendation, versioned and audited, never a mutable field)
# ---------------------------------------------------------------------------

@router.post("/assets/{twin_id}/assessments", response_model=asset_schemas.HealthAssessmentOut, status_code=201)
def create_health_assessment(
    twin_id: str,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("asset.assess")),
):
    twin = _get_or_404(db, twin_models.DigitalTwin, twin_id, "Asset")
    _assert_optional_farm_scope(db, current_user, "asset.assess", twin.farm_id)
    twin_type = _get_or_404(db, twin_models.TwinType, twin.twin_type_id, "Twin type")

    result = assess_asset_health(db, twin=twin, twin_type=twin_type)
    assessment = asset_models.HealthAssessment(
        tenant_id=current_user.tenant_id,
        twin_id=twin.id,
        computed_at=datetime.now(timezone.utc),
        score=result.score,
        band=result.band,
        summary=result.summary,
        metrics=[m.model_dump() for m in result.metrics],
        recommendations=result.recommendations,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(assessment)
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="asset_health_assessment.create",
        entity_type="asset_health_assessment",
        entity_id=assessment.id,
        new_values={"twin_id": twin.id, "score": assessment.score, "band": assessment.band},
    )
    # AI-001: every rule-engine output that feeds a downstream decision gets
    # a Prediction envelope recorded against the registry (Phase 15).
    record_prediction(
        db,
        tenant_id=current_user.tenant_id,
        model_code="health_score_rule_engine",
        entity_type="digital_twin",
        entity_id=twin.id,
        input_ref={"twin_type_id": twin_type.id},
        output={"score": result.score, "band": result.band, "recommendations": result.recommendations},
        confidence=None,
        created_by=current_user.id,
    )
    db.commit()
    return assessment


@router.get("/assets/{twin_id}/assessments", response_model=list[asset_schemas.HealthAssessmentOut])
def list_health_assessments(
    twin_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("asset.view")),
):
    twin = _get_or_404(db, twin_models.DigitalTwin, twin_id, "Asset")
    _assert_optional_farm_scope(db, user, "asset.view", twin.farm_id)
    return (
        db.query(asset_models.HealthAssessment)
        .filter(asset_models.HealthAssessment.twin_id == twin_id)
        .order_by(asset_models.HealthAssessment.computed_at.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Maintenance requests (FR-MNT-002): MaintenanceRequest -> (approval) ->
# WorkOrder, same approval-gated lifecycle shape as Phase 8/10's plans.
# ---------------------------------------------------------------------------

def _active_definition(db: Session, tenant_id: str, entity_type: str) -> fm.WorkflowDefinition:
    definition = (
        db.query(fm.WorkflowDefinition)
        .filter(
            fm.WorkflowDefinition.tenant_id == tenant_id,
            fm.WorkflowDefinition.entity_type == entity_type,
            fm.WorkflowDefinition.is_active.is_(True),
        )
        .first()
    )
    if definition is None:
        raise HTTPException(
            status_code=409,
            detail=f"No active approval workflow configured for '{entity_type}' - contact your tenant admin",
        )
    return definition


@router.post("/assets/{twin_id}/maintenance-requests", response_model=asset_schemas.MaintenanceRequestOut, status_code=201)
def create_maintenance_request(
    twin_id: str,
    payload: asset_schemas.MaintenanceRequestCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("asset.maintenance.manage")),
):
    twin = _get_or_404(db, twin_models.DigitalTwin, twin_id, "Asset")
    _assert_optional_farm_scope(db, current_user, "asset.maintenance.manage", twin.farm_id)
    if payload.strategy not in asset_models.MAINTENANCE_STRATEGIES:
        raise HTTPException(status_code=422, detail=f"Unknown strategy '{payload.strategy}'")
    if payload.source_assessment_id:
        _get_or_404(db, asset_models.HealthAssessment, payload.source_assessment_id, "Health assessment")

    request = asset_models.MaintenanceRequest(
        tenant_id=current_user.tenant_id,
        twin_id=twin.id,
        farm_id=twin.farm_id,
        strategy=payload.strategy,
        description=payload.description,
        source_assessment_id=payload.source_assessment_id,
        requested_by=current_user.id,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(request)
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="maintenance_request.create",
        entity_type="maintenance_request",
        entity_id=request.id,
        new_values={"twin_id": twin.id, "strategy": request.strategy},
    )
    db.commit()
    return request


@router.get("/maintenance-requests", response_model=list[asset_schemas.MaintenanceRequestOut])
def list_maintenance_requests(
    farm_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("asset.maintenance.view")),
):
    if farm_id:
        assert_farm_scope(db, user, "asset.maintenance.view", farm_id)
    query = db.query(asset_models.MaintenanceRequest)
    if farm_id:
        query = query.filter(asset_models.MaintenanceRequest.farm_id == farm_id)
    return query.order_by(asset_models.MaintenanceRequest.created_at.desc()).all()


@router.get("/maintenance-requests/{request_id}", response_model=asset_schemas.MaintenanceRequestOut)
def get_maintenance_request(
    request_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("asset.maintenance.view")),
):
    request = _get_or_404(db, asset_models.MaintenanceRequest, request_id, "Maintenance request")
    _assert_optional_farm_scope(db, user, "asset.maintenance.view", request.farm_id)
    return request


@router.post("/maintenance-requests/{request_id}/submit", response_model=asset_schemas.MaintenanceRequestOut)
def submit_maintenance_request(
    request_id: str,
    request_ctx: Request,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("asset.maintenance.manage")),
):
    maint_request = _get_or_404(db, asset_models.MaintenanceRequest, request_id, "Maintenance request")
    _assert_optional_farm_scope(db, current_user, "asset.maintenance.manage", maint_request.farm_id)
    if maint_request.status != "draft":
        raise HTTPException(status_code=409, detail=f"Cannot submit a request in status '{maint_request.status}'")

    definition = _active_definition(db, current_user.tenant_id, "maintenance_request")
    instance = workflow_engine.submit(
        db,
        tenant_id=current_user.tenant_id,
        actor=current_user,
        definition=definition,
        entity_type="maintenance_request",
        entity_id=maint_request.id,
        context={"twin_id": maint_request.twin_id, "farm_id": maint_request.farm_id},
        correlation_id=_correlation_id(request_ctx),
    )
    maint_request.workflow_instance_id = instance.id
    maint_request.status = "pending_approval"
    maint_request.updated_by = current_user.id
    db.commit()
    return maint_request


def _decide_maintenance(action: str):
    """See `routers.v1.irrigation._decide_irrigation`'s docstring - same
    layered farm-scope gate on top of the workflow engine's own
    (farm-unaware) role/permission check."""

    def handler(
        request_id: str,
        payload: asset_schemas.ApprovalDecisionRequest,
        request_ctx: Request,
        db: Session = Depends(get_db),
        current_user: fm.User = Depends(require_permission("asset.maintenance.manage")),
    ):
        maint_request = _get_or_404(db, asset_models.MaintenanceRequest, request_id, "Maintenance request")
        _assert_optional_farm_scope(db, current_user, "asset.maintenance.manage", maint_request.farm_id)
        if not maint_request.workflow_instance_id:
            raise HTTPException(status_code=409, detail="Request has not been submitted for approval")

        instance = _get_or_404(db, fm.WorkflowInstance, maint_request.workflow_instance_id, "Workflow instance")
        definition = db.get(fm.WorkflowDefinition, instance.workflow_definition_id)
        workflow_engine.decide(
            db,
            tenant_id=current_user.tenant_id,
            actor=current_user,
            instance=instance,
            definition=definition,
            action=action,
            reason=payload.reason,
            correlation_id=_correlation_id(request_ctx),
        )
        if instance.status == "approved":
            maint_request.status = "approved"
        elif instance.status in ("rejected", "cancelled"):
            maint_request.status = "rejected"
        elif instance.status == "draft":
            maint_request.status = "draft"
        maint_request.updated_by = current_user.id
        db.commit()
        return maint_request

    return handler


router.add_api_route(
    "/maintenance-requests/{request_id}/approve",
    _decide_maintenance("approve"),
    methods=["POST"],
    response_model=asset_schemas.MaintenanceRequestOut,
)
router.add_api_route(
    "/maintenance-requests/{request_id}/reject",
    _decide_maintenance("reject"),
    methods=["POST"],
    response_model=asset_schemas.MaintenanceRequestOut,
)


@router.post("/maintenance-requests/{request_id}/convert", response_model=asset_schemas.WorkOrderOut, status_code=201)
def convert_to_work_order(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("asset.maintenance.manage")),
):
    """Only an approved MaintenanceRequest can become a WorkOrder - this is
    the Approved Action FR-PDM-002 requires as a separate, separately-
    audited state from the Prediction/Recommendation that led to it."""
    maint_request = _get_or_404(db, asset_models.MaintenanceRequest, request_id, "Maintenance request")
    _assert_optional_farm_scope(db, current_user, "asset.maintenance.manage", maint_request.farm_id)
    if maint_request.status != "approved":
        raise HTTPException(status_code=409, detail="Only an approved request can be converted to a work order")

    work_order = asset_models.WorkOrder(
        tenant_id=current_user.tenant_id,
        twin_id=maint_request.twin_id,
        farm_id=maint_request.farm_id,
        request_id=maint_request.id,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(work_order)
    maint_request.status = "converted"
    maint_request.updated_by = current_user.id
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="maintenance_request.convert",
        entity_type="work_order",
        entity_id=work_order.id,
        new_values={"request_id": maint_request.id},
    )
    db.commit()
    return work_order


# ---------------------------------------------------------------------------
# Work orders
# ---------------------------------------------------------------------------

@router.get("/work-orders", response_model=list[asset_schemas.WorkOrderOut])
def list_work_orders(
    farm_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("asset.maintenance.view")),
):
    if farm_id:
        assert_farm_scope(db, user, "asset.maintenance.view", farm_id)
    query = db.query(asset_models.WorkOrder)
    if farm_id:
        query = query.filter(asset_models.WorkOrder.farm_id == farm_id)
    if status:
        query = query.filter(asset_models.WorkOrder.status == status)
    return query.order_by(asset_models.WorkOrder.created_at.desc()).all()


@router.get("/work-orders/{work_order_id}", response_model=asset_schemas.WorkOrderOut)
def get_work_order(
    work_order_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("asset.maintenance.view")),
):
    work_order = _get_or_404(db, asset_models.WorkOrder, work_order_id, "Work order")
    _assert_optional_farm_scope(db, user, "asset.maintenance.view", work_order.farm_id)
    return work_order


@router.patch("/work-orders/{work_order_id}", response_model=asset_schemas.WorkOrderOut)
def update_work_order(
    work_order_id: str,
    payload: asset_schemas.WorkOrderUpdate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("asset.maintenance.manage")),
):
    work_order = _get_or_404(db, asset_models.WorkOrder, work_order_id, "Work order")
    _assert_optional_farm_scope(db, current_user, "asset.maintenance.manage", work_order.farm_id)
    if payload.status is not None and payload.status not in asset_models.WORK_ORDER_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown status '{payload.status}'")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(work_order, field, value)
    if payload.status == "completed":
        work_order.completed_at = datetime.now(timezone.utc)
        work_order.completed_by = current_user.id
    work_order.updated_by = current_user.id
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="work_order.update",
        entity_type="work_order",
        entity_id=work_order.id,
        new_values=changes,
    )
    db.commit()
    return work_order
