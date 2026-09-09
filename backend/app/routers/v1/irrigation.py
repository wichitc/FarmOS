from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.deps import assert_farm_scope, require_permission
from ...database import get_db
from ...farm import models as farm_models
from ...foundation import models as fm
from ...foundation import workflow_engine
from ...foundation.audit import record_audit
from ...irrigation import models as irr_models
from ...irrigation import schemas as irr_schemas
from ...twins import models as twin_models

router = APIRouter(prefix="/api/v1/irrigation", tags=["irrigation"])


def _get_or_404(db: Session, model, obj_id: str, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


def _farm_id_for_plot(db: Session, plot_id: str) -> str:
    plot = _get_or_404(db, farm_models.Plot, plot_id, "Plot")
    zone = db.get(farm_models.Zone, plot.zone_id)
    return zone.farm_id


def _correlation_id(request: Request) -> str:
    return request.headers.get("x-correlation-id", "")


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
        # Should not happen for a tenant provisioned after Phase 8 landed
        # (see foundation.seed._seed_mandatory_approval_workflows) - this
        # guards the approval floor rather than silently allowing execution
        # with no approval path at all.
        raise HTTPException(
            status_code=409,
            detail=f"No active approval workflow configured for '{entity_type}' - contact your tenant admin",
        )
    return definition


# ---------------------------------------------------------------------------
# Irrigation plans
# ---------------------------------------------------------------------------

@router.post("/farms/{farm_id}/plans", response_model=irr_schemas.IrrigationPlanOut, status_code=201)
def create_irrigation_plan(
    farm_id: str,
    payload: irr_schemas.IrrigationPlanCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("irrigation.plan.manage")),
):
    farm = _get_or_404(db, farm_models.Farm, farm_id, "Farm")
    assert_farm_scope(db, current_user, "irrigation.plan.manage", farm.id)
    if payload.plot_id and _farm_id_for_plot(db, payload.plot_id) != farm.id:
        raise HTTPException(status_code=422, detail="plot_id does not belong to this farm")
    if payload.source_twin_id:
        _get_or_404(db, twin_models.DigitalTwin, payload.source_twin_id, "Twin")

    plan = irr_models.IrrigationPlan(
        tenant_id=current_user.tenant_id,
        farm_id=farm.id,
        plot_id=payload.plot_id,
        source_twin_id=payload.source_twin_id,
        source=payload.source,
        recommended_volume_liters=payload.recommended_volume_liters,
        recommended_duration_minutes=payload.recommended_duration_minutes,
        reason=payload.reason,
        scheduled_for=payload.scheduled_for,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(plan)
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="irrigation_plan.create",
        entity_type="irrigation_plan",
        entity_id=plan.id,
        new_values={"farm_id": farm.id, "plot_id": payload.plot_id},
    )
    db.commit()
    return plan


@router.get("/farms/{farm_id}/plans", response_model=list[irr_schemas.IrrigationPlanOut])
def list_irrigation_plans(
    farm_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("irrigation.plan.view")),
):
    assert_farm_scope(db, user, "irrigation.plan.view", farm_id)
    return (
        db.query(irr_models.IrrigationPlan)
        .filter(irr_models.IrrigationPlan.farm_id == farm_id)
        .order_by(irr_models.IrrigationPlan.created_at.desc())
        .all()
    )


@router.get("/plans/{plan_id}", response_model=irr_schemas.IrrigationPlanOut)
def get_irrigation_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("irrigation.plan.view")),
):
    plan = _get_or_404(db, irr_models.IrrigationPlan, plan_id, "Irrigation plan")
    assert_farm_scope(db, user, "irrigation.plan.view", plan.farm_id)
    return plan


@router.post("/plans/{plan_id}/submit", response_model=irr_schemas.IrrigationPlanOut)
def submit_irrigation_plan(
    plan_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("irrigation.plan.manage")),
):
    plan = _get_or_404(db, irr_models.IrrigationPlan, plan_id, "Irrigation plan")
    assert_farm_scope(db, current_user, "irrigation.plan.manage", plan.farm_id)
    if plan.status != "draft":
        raise HTTPException(status_code=409, detail=f"Cannot submit a plan in status '{plan.status}'")

    definition = _active_definition(db, current_user.tenant_id, "irrigation_plan")
    instance = workflow_engine.submit(
        db,
        tenant_id=current_user.tenant_id,
        actor=current_user,
        definition=definition,
        entity_type="irrigation_plan",
        entity_id=plan.id,
        context={"farm_id": plan.farm_id, "plot_id": plan.plot_id},
        correlation_id=_correlation_id(request),
    )
    plan.workflow_instance_id = instance.id
    plan.status = "pending_approval"
    plan.updated_by = current_user.id
    db.commit()
    return plan


def _decide_irrigation(action: str):
    """`workflow_engine.decide` already checks the approver's role/permission
    (see `_require_current_step_approver`) but that check is role-based with
    no farm-scope awareness (it's generic across every entity type Phase 3's
    workflow engine serves). The `assert_farm_scope` call below is this
    domain's own additional gate, closing that gap specifically for a
    hardcoded-approval-floor action - deliberately layered, not redundant."""

    def handler(
        plan_id: str,
        payload: irr_schemas.ApprovalDecisionRequest,
        request: Request,
        db: Session = Depends(get_db),
        current_user: fm.User = Depends(require_permission("irrigation.plan.manage")),
    ):
        plan = _get_or_404(db, irr_models.IrrigationPlan, plan_id, "Irrigation plan")
        assert_farm_scope(db, current_user, "irrigation.plan.manage", plan.farm_id)
        if not plan.workflow_instance_id:
            raise HTTPException(status_code=409, detail="Plan has not been submitted for approval")

        instance = _get_or_404(db, fm.WorkflowInstance, plan.workflow_instance_id, "Workflow instance")
        definition = db.get(fm.WorkflowDefinition, instance.workflow_definition_id)
        workflow_engine.decide(
            db,
            tenant_id=current_user.tenant_id,
            actor=current_user,
            instance=instance,
            definition=definition,
            action=action,
            reason=payload.reason,
            correlation_id=_correlation_id(request),
        )
        # Sync the domain entity's status from the generic engine's result -
        # kept here (not inside workflow_engine, which stays domain-agnostic)
        # since only this router knows what an IrrigationPlan's statuses mean.
        if instance.status == "approved":
            plan.status = "approved"
        elif instance.status in ("rejected", "cancelled"):
            plan.status = "rejected"
        elif instance.status == "draft":
            plan.status = "draft"
        plan.updated_by = current_user.id
        db.commit()
        return plan

    return handler


router.add_api_route(
    "/plans/{plan_id}/approve", _decide_irrigation("approve"), methods=["POST"], response_model=irr_schemas.IrrigationPlanOut
)
router.add_api_route(
    "/plans/{plan_id}/reject", _decide_irrigation("reject"), methods=["POST"], response_model=irr_schemas.IrrigationPlanOut
)


@router.post("/plans/{plan_id}/execute", response_model=irr_schemas.IrrigationEventOut, status_code=201)
def execute_irrigation_plan(
    plan_id: str,
    payload: irr_schemas.IrrigationEventCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("irrigation.plan.manage")),
):
    plan = _get_or_404(db, irr_models.IrrigationPlan, plan_id, "Irrigation plan")
    assert_farm_scope(db, current_user, "irrigation.plan.manage", plan.farm_id)
    if plan.status != "approved":
        raise HTTPException(status_code=409, detail="Only an approved plan can be executed")

    event = irr_models.IrrigationEvent(
        tenant_id=current_user.tenant_id,
        plan_id=plan.id,
        farm_id=plan.farm_id,
        plot_id=plan.plot_id,
        actual_volume_liters=payload.actual_volume_liters,
        actual_duration_minutes=payload.actual_duration_minutes,
        started_at=payload.started_at or datetime.now(timezone.utc),
        ended_at=payload.ended_at,
        executed_by=current_user.id,
        safety_checks=payload.safety_checks,
        notes=payload.notes,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(event)
    plan.status = "completed"
    plan.updated_by = current_user.id
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="irrigation_plan.execute",
        entity_type="irrigation_event",
        entity_id=event.id,
        new_values={"plan_id": plan.id, "actual_volume_liters": event.actual_volume_liters},
    )
    db.commit()
    return event


# ---------------------------------------------------------------------------
# Fertilizer master data
# ---------------------------------------------------------------------------

@router.post("/fertilizers", response_model=irr_schemas.FertilizerOut, status_code=201)
def create_fertilizer(
    payload: irr_schemas.FertilizerCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("fertilizer.manage")),
):
    fertilizer = irr_models.Fertilizer(
        tenant_id=current_user.tenant_id,
        code=payload.code,
        name=payload.name,
        composition=payload.composition,
        stock_ref=payload.stock_ref,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(fertilizer)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A fertilizer with this code already exists") from exc

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="fertilizer.create",
        entity_type="fertilizer",
        entity_id=fertilizer.id,
        new_values={"code": fertilizer.code},
    )
    db.commit()
    return fertilizer


@router.get("/fertilizers", response_model=list[irr_schemas.FertilizerOut])
def list_fertilizers(
    db: Session = Depends(get_db),
    _user: fm.User = Depends(require_permission("fertilizer.view")),
):
    return db.query(irr_models.Fertilizer).order_by(irr_models.Fertilizer.name.asc()).all()


# ---------------------------------------------------------------------------
# Fertigation plans (same shape as irrigation plans)
# ---------------------------------------------------------------------------

@router.post("/farms/{farm_id}/fertigation-plans", response_model=irr_schemas.FertigationPlanOut, status_code=201)
def create_fertigation_plan(
    farm_id: str,
    payload: irr_schemas.FertigationPlanCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("fertigation.plan.manage")),
):
    farm = _get_or_404(db, farm_models.Farm, farm_id, "Farm")
    assert_farm_scope(db, current_user, "fertigation.plan.manage", farm.id)
    if payload.plot_id and _farm_id_for_plot(db, payload.plot_id) != farm.id:
        raise HTTPException(status_code=422, detail="plot_id does not belong to this farm")
    _get_or_404(db, irr_models.Fertilizer, payload.fertilizer_id, "Fertilizer")

    plan = irr_models.FertigationPlan(
        tenant_id=current_user.tenant_id,
        farm_id=farm.id,
        plot_id=payload.plot_id,
        fertilizer_id=payload.fertilizer_id,
        source=payload.source,
        target_n_kg=payload.target_n_kg,
        target_p_kg=payload.target_p_kg,
        target_k_kg=payload.target_k_kg,
        recommended_quantity_kg=payload.recommended_quantity_kg,
        reason=payload.reason,
        scheduled_for=payload.scheduled_for,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(plan)
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="fertigation_plan.create",
        entity_type="fertigation_plan",
        entity_id=plan.id,
        new_values={"farm_id": farm.id, "fertilizer_id": payload.fertilizer_id},
    )
    db.commit()
    return plan


@router.get("/farms/{farm_id}/fertigation-plans", response_model=list[irr_schemas.FertigationPlanOut])
def list_fertigation_plans(
    farm_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("fertigation.plan.view")),
):
    assert_farm_scope(db, user, "fertigation.plan.view", farm_id)
    return (
        db.query(irr_models.FertigationPlan)
        .filter(irr_models.FertigationPlan.farm_id == farm_id)
        .order_by(irr_models.FertigationPlan.created_at.desc())
        .all()
    )


@router.get("/fertigation-plans/{plan_id}", response_model=irr_schemas.FertigationPlanOut)
def get_fertigation_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("fertigation.plan.view")),
):
    plan = _get_or_404(db, irr_models.FertigationPlan, plan_id, "Fertigation plan")
    assert_farm_scope(db, user, "fertigation.plan.view", plan.farm_id)
    return plan


@router.post("/fertigation-plans/{plan_id}/submit", response_model=irr_schemas.FertigationPlanOut)
def submit_fertigation_plan(
    plan_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("fertigation.plan.manage")),
):
    plan = _get_or_404(db, irr_models.FertigationPlan, plan_id, "Fertigation plan")
    assert_farm_scope(db, current_user, "fertigation.plan.manage", plan.farm_id)
    if plan.status != "draft":
        raise HTTPException(status_code=409, detail=f"Cannot submit a plan in status '{plan.status}'")

    definition = _active_definition(db, current_user.tenant_id, "fertigation_plan")
    instance = workflow_engine.submit(
        db,
        tenant_id=current_user.tenant_id,
        actor=current_user,
        definition=definition,
        entity_type="fertigation_plan",
        entity_id=plan.id,
        context={"farm_id": plan.farm_id, "plot_id": plan.plot_id},
        correlation_id=_correlation_id(request),
    )
    plan.workflow_instance_id = instance.id
    plan.status = "pending_approval"
    plan.updated_by = current_user.id
    db.commit()
    return plan


def _decide_fertigation(action: str):
    """See `_decide_irrigation`'s docstring - same layered farm-scope gate
    on top of the workflow engine's own role/permission check."""

    def handler(
        plan_id: str,
        payload: irr_schemas.ApprovalDecisionRequest,
        request: Request,
        db: Session = Depends(get_db),
        current_user: fm.User = Depends(require_permission("fertigation.plan.manage")),
    ):
        plan = _get_or_404(db, irr_models.FertigationPlan, plan_id, "Fertigation plan")
        assert_farm_scope(db, current_user, "fertigation.plan.manage", plan.farm_id)
        if not plan.workflow_instance_id:
            raise HTTPException(status_code=409, detail="Plan has not been submitted for approval")

        instance = _get_or_404(db, fm.WorkflowInstance, plan.workflow_instance_id, "Workflow instance")
        definition = db.get(fm.WorkflowDefinition, instance.workflow_definition_id)
        workflow_engine.decide(
            db,
            tenant_id=current_user.tenant_id,
            actor=current_user,
            instance=instance,
            definition=definition,
            action=action,
            reason=payload.reason,
            correlation_id=_correlation_id(request),
        )
        if instance.status == "approved":
            plan.status = "approved"
        elif instance.status in ("rejected", "cancelled"):
            plan.status = "rejected"
        elif instance.status == "draft":
            plan.status = "draft"
        plan.updated_by = current_user.id
        db.commit()
        return plan

    return handler


router.add_api_route(
    "/fertigation-plans/{plan_id}/approve",
    _decide_fertigation("approve"),
    methods=["POST"],
    response_model=irr_schemas.FertigationPlanOut,
)
router.add_api_route(
    "/fertigation-plans/{plan_id}/reject",
    _decide_fertigation("reject"),
    methods=["POST"],
    response_model=irr_schemas.FertigationPlanOut,
)


@router.post("/fertigation-plans/{plan_id}/execute", response_model=irr_schemas.FertigationEventOut, status_code=201)
def execute_fertigation_plan(
    plan_id: str,
    payload: irr_schemas.FertigationEventCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("fertigation.plan.manage")),
):
    plan = _get_or_404(db, irr_models.FertigationPlan, plan_id, "Fertigation plan")
    assert_farm_scope(db, current_user, "fertigation.plan.manage", plan.farm_id)
    if plan.status != "approved":
        raise HTTPException(status_code=409, detail="Only an approved plan can be executed")
    if payload.tree_id:
        tree = _get_or_404(db, farm_models.Tree, payload.tree_id, "Tree")
    else:
        tree = None

    event = irr_models.FertigationEvent(
        tenant_id=current_user.tenant_id,
        plan_id=plan.id,
        farm_id=plan.farm_id,
        plot_id=plan.plot_id,
        tree_id=tree.id if tree else None,
        actual_quantity_kg=payload.actual_quantity_kg,
        actual_breakdown=payload.actual_breakdown,
        applied_at=payload.applied_at or datetime.now(timezone.utc),
        executed_by=current_user.id,
        notes=payload.notes,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(event)
    plan.status = "completed"
    plan.updated_by = current_user.id
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="fertigation_plan.execute",
        entity_type="fertigation_event",
        entity_id=event.id,
        new_values={"plan_id": plan.id, "actual_quantity_kg": event.actual_quantity_kg},
    )
    db.commit()
    return event
