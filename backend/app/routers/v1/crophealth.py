from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.deps import assert_farm_scope, require_permission
from ...crophealth import models as ch_models
from ...crophealth import schemas as ch_schemas
from ...crophealth.risk import compute_disease_risk
from ...database import get_db
from ...farm import models as farm_models
from ...foundation import models as fm
from ...foundation import workflow_engine
from ...foundation.audit import record_audit
from ...vision import models as vision_models
from ...weather.provider import current_reading

router = APIRouter(prefix="/api/v1/crop-health", tags=["crop-health"])


def _get_or_404(db: Session, model, obj_id: str, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


def _correlation_id(request: Request) -> str:
    return request.headers.get("x-correlation-id", "")


# ---------------------------------------------------------------------------
# Disease master data
# ---------------------------------------------------------------------------

@router.post("/diseases", response_model=ch_schemas.DiseaseOut, status_code=201)
def create_disease(
    payload: ch_schemas.DiseaseCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("crophealth.disease.manage")),
):
    if payload.pathogen_type not in ch_models.DISEASE_PATHOGEN_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown pathogen_type '{payload.pathogen_type}'")

    disease = ch_models.Disease(
        tenant_id=current_user.tenant_id,
        code=payload.code,
        name_en=payload.name_en,
        name_th=payload.name_th,
        pathogen_type=payload.pathogen_type,
        symptoms=payload.symptoms,
        susceptible_crop_codes=payload.susceptible_crop_codes,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(disease)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A disease with this code already exists") from exc

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="disease.create",
        entity_type="disease",
        entity_id=disease.id,
        new_values={"code": disease.code, "pathogen_type": disease.pathogen_type},
    )
    db.commit()
    return disease


@router.get("/diseases", response_model=list[ch_schemas.DiseaseOut])
def list_diseases(
    db: Session = Depends(get_db),
    _user: fm.User = Depends(require_permission("crophealth.disease.view")),
):
    return db.query(ch_models.Disease).order_by(ch_models.Disease.name_en.asc()).all()


# ---------------------------------------------------------------------------
# Disease risk (FR-HEALTH-002/004)
# ---------------------------------------------------------------------------

@router.post("/farms/{farm_id}/risk", response_model=ch_schemas.DiseaseRiskOut)
def compute_farm_disease_risk(
    farm_id: str,
    payload: ch_schemas.DiseaseRiskRequest,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("crophealth.incident.view")),
):
    """Gathers real signals already in the platform (weather readings from
    Phase 8, recent confirmed incidents, recent Vision AI detection
    confidence from Phase 9) and runs them through the rule-based engine -
    explicit `humidity_pct`/`rainfall_mm_7d`/`leaf_wetness_hours` in the
    payload override the auto-gathered weather reading when given (e.g. a
    field-measured leaf-wetness sensor has no farm-level weather-reading
    equivalent yet, so it's always caller-supplied)."""
    farm = _get_or_404(db, farm_models.Farm, farm_id, "Farm")
    assert_farm_scope(db, user, "crophealth.incident.view", farm.id)

    humidity = payload.humidity_pct
    if humidity is None:
        reading = current_reading(db, farm_id=farm.id, metric="humidity_pct")
        humidity = reading.value if reading else None

    rainfall = payload.rainfall_mm_7d
    if rainfall is None:
        reading = current_reading(db, farm_id=farm.id, metric="rainfall_mm")
        rainfall = reading.value if reading else None

    since = datetime.now(timezone.utc) - timedelta(days=30)
    incident_query = db.query(ch_models.DiseaseIncident).filter(
        ch_models.DiseaseIncident.farm_id == farm.id,
        ch_models.DiseaseIncident.status.notin_(("resolved",)),
        ch_models.DiseaseIncident.created_at >= since,
    )
    if payload.plot_id:
        incident_query = incident_query.filter(ch_models.DiseaseIncident.plot_id == payload.plot_id)
    recent_incident_count = incident_query.count()

    detection_query = (
        db.query(func.max(vision_models.Detection.confidence))
        .join(vision_models.Camera, vision_models.Camera.id == vision_models.Detection.camera_id)
        .filter(vision_models.Camera.farm_id == farm.id, vision_models.Detection.validation_status == "confirmed")
    )
    if payload.plot_id:
        detection_query = detection_query.filter(vision_models.Detection.plot_id == payload.plot_id)
    recent_detection_confidence = detection_query.scalar()

    result = compute_disease_risk(
        humidity_pct=humidity,
        rainfall_mm_7d=rainfall,
        leaf_wetness_hours=payload.leaf_wetness_hours,
        recent_confirmed_incident_count=recent_incident_count,
        recent_vision_detection_confidence=recent_detection_confidence,
    )
    return ch_schemas.DiseaseRiskOut(
        risk_score=result.risk_score,
        band=result.band,
        confidence=result.confidence,
        evidence=result.evidence,
        recommendations=result.recommendations,
    )


# ---------------------------------------------------------------------------
# Disease incidents (FR-HEALTH-001)
# ---------------------------------------------------------------------------

@router.post("/farms/{farm_id}/incidents", response_model=ch_schemas.DiseaseIncidentOut, status_code=201)
def create_incident(
    farm_id: str,
    payload: ch_schemas.DiseaseIncidentCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("crophealth.incident.manage")),
):
    farm = _get_or_404(db, farm_models.Farm, farm_id, "Farm")
    assert_farm_scope(db, current_user, "crophealth.incident.manage", farm.id)
    _get_or_404(db, ch_models.Disease, payload.disease_id, "Disease")

    if payload.source_detection_id:
        # FR-CCTV-004: only a human-confirmed detection can create an
        # incident - an unreviewed or rejected one cannot.
        detection = _get_or_404(db, vision_models.Detection, payload.source_detection_id, "Detection")
        if detection.validation_status != "confirmed":
            raise HTTPException(
                status_code=422,
                detail=f"Detection must be confirmed before it can create an incident (status is '{detection.validation_status}')",
            )

    incident = ch_models.DiseaseIncident(
        tenant_id=current_user.tenant_id,
        farm_id=farm.id,
        plot_id=payload.plot_id,
        tree_id=payload.tree_id,
        disease_id=payload.disease_id,
        source_detection_id=payload.source_detection_id,
        risk_score=payload.risk_score,
        confidence=payload.confidence,
        evidence=payload.evidence,
        notes=payload.notes,
        reported_by=current_user.id,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(incident)
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="disease_incident.create",
        entity_type="disease_incident",
        entity_id=incident.id,
        new_values={"farm_id": farm.id, "disease_id": payload.disease_id, "status": incident.status},
    )
    db.commit()
    return incident


@router.get("/farms/{farm_id}/incidents", response_model=list[ch_schemas.DiseaseIncidentOut])
def list_incidents(
    farm_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("crophealth.incident.view")),
):
    assert_farm_scope(db, user, "crophealth.incident.view", farm_id)
    return (
        db.query(ch_models.DiseaseIncident)
        .filter(ch_models.DiseaseIncident.farm_id == farm_id)
        .order_by(ch_models.DiseaseIncident.created_at.desc())
        .all()
    )


@router.get("/incidents/{incident_id}", response_model=ch_schemas.DiseaseIncidentOut)
def get_incident(
    incident_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("crophealth.incident.view")),
):
    incident = _get_or_404(db, ch_models.DiseaseIncident, incident_id, "Disease incident")
    assert_farm_scope(db, user, "crophealth.incident.view", incident.farm_id)
    return incident


@router.patch("/incidents/{incident_id}/status", response_model=ch_schemas.DiseaseIncidentOut)
def update_incident_status(
    incident_id: str,
    payload: ch_schemas.IncidentStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("crophealth.incident.manage")),
):
    incident = _get_or_404(db, ch_models.DiseaseIncident, incident_id, "Disease incident")
    assert_farm_scope(db, current_user, "crophealth.incident.manage", incident.farm_id)

    allowed = ch_models.INCIDENT_ALLOWED_TRANSITIONS.get(incident.status, ())
    if payload.status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot move a '{incident.status}' incident to '{payload.status}' (allowed: {allowed or 'none - terminal state'})",
        )

    old_status = incident.status
    incident.status = payload.status
    if payload.notes:
        incident.notes = f"{incident.notes}\n{payload.notes}" if incident.notes else payload.notes
    incident.updated_by = current_user.id
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="disease_incident.status_change",
        entity_type="disease_incident",
        entity_id=incident.id,
        old_values={"status": old_status},
        new_values={"status": incident.status},
        reason=payload.notes,
    )
    db.commit()
    return incident


# ---------------------------------------------------------------------------
# Treatment plans (FR-HEALTH-003) - same approval-gated lifecycle shape as
# Irrigation/Fertigation plans (Phase 8): draft -> pending_approval ->
# approved/rejected -> completed.
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


@router.post("/treatment-plans", response_model=ch_schemas.TreatmentPlanOut, status_code=201)
def create_treatment_plan(
    payload: ch_schemas.TreatmentPlanCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("crophealth.treatment.manage")),
):
    incident = _get_or_404(db, ch_models.DiseaseIncident, payload.incident_id, "Disease incident")
    assert_farm_scope(db, current_user, "crophealth.treatment.manage", incident.farm_id)

    plan = ch_models.TreatmentPlan(
        tenant_id=current_user.tenant_id,
        incident_id=incident.id,
        farm_id=incident.farm_id,
        method=payload.method,
        chemical_or_treatment=payload.chemical_or_treatment,
        work_task_ref=payload.work_task_ref,
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
        action="treatment_plan.create",
        entity_type="treatment_plan",
        entity_id=plan.id,
        new_values={"incident_id": incident.id},
    )
    db.commit()
    return plan


@router.get("/farms/{farm_id}/treatment-plans", response_model=list[ch_schemas.TreatmentPlanOut])
def list_treatment_plans(
    farm_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("crophealth.treatment.view")),
):
    assert_farm_scope(db, user, "crophealth.treatment.view", farm_id)
    return (
        db.query(ch_models.TreatmentPlan)
        .filter(ch_models.TreatmentPlan.farm_id == farm_id)
        .order_by(ch_models.TreatmentPlan.created_at.desc())
        .all()
    )


@router.get("/treatment-plans/{plan_id}", response_model=ch_schemas.TreatmentPlanOut)
def get_treatment_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("crophealth.treatment.view")),
):
    plan = _get_or_404(db, ch_models.TreatmentPlan, plan_id, "Treatment plan")
    assert_farm_scope(db, user, "crophealth.treatment.view", plan.farm_id)
    return plan


@router.post("/treatment-plans/{plan_id}/submit", response_model=ch_schemas.TreatmentPlanOut)
def submit_treatment_plan(
    plan_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("crophealth.treatment.manage")),
):
    plan = _get_or_404(db, ch_models.TreatmentPlan, plan_id, "Treatment plan")
    assert_farm_scope(db, current_user, "crophealth.treatment.manage", plan.farm_id)
    if plan.status != "draft":
        raise HTTPException(status_code=409, detail=f"Cannot submit a plan in status '{plan.status}'")

    definition = _active_definition(db, current_user.tenant_id, "treatment_plan")
    instance = workflow_engine.submit(
        db,
        tenant_id=current_user.tenant_id,
        actor=current_user,
        definition=definition,
        entity_type="treatment_plan",
        entity_id=plan.id,
        context={"farm_id": plan.farm_id, "incident_id": plan.incident_id},
        correlation_id=_correlation_id(request),
    )
    plan.workflow_instance_id = instance.id
    plan.status = "pending_approval"
    plan.updated_by = current_user.id
    db.commit()
    return plan


def _decide_treatment(action: str):
    """See `routers.v1.irrigation._decide_irrigation`'s docstring - same
    layered farm-scope gate on top of the workflow engine's own
    (farm-unaware) role/permission check."""

    def handler(
        plan_id: str,
        payload: ch_schemas.ApprovalDecisionRequest,
        request: Request,
        db: Session = Depends(get_db),
        current_user: fm.User = Depends(require_permission("crophealth.treatment.manage")),
    ):
        plan = _get_or_404(db, ch_models.TreatmentPlan, plan_id, "Treatment plan")
        assert_farm_scope(db, current_user, "crophealth.treatment.manage", plan.farm_id)
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
            # Sync the linked incident forward too, when that's a legal
            # transition from wherever it currently sits (e.g. a re-approval
            # after "monitoring" looped back doesn't clobber a state a
            # human already advanced manually in the meantime).
            incident = db.get(ch_models.DiseaseIncident, plan.incident_id)
            if incident and "treatment_planned" in ch_models.INCIDENT_ALLOWED_TRANSITIONS.get(incident.status, ()):
                incident.status = "treatment_planned"
                incident.updated_by = current_user.id
        elif instance.status in ("rejected", "cancelled"):
            plan.status = "rejected"
        elif instance.status == "draft":
            plan.status = "draft"
        plan.updated_by = current_user.id
        db.commit()
        return plan

    return handler


router.add_api_route(
    "/treatment-plans/{plan_id}/approve",
    _decide_treatment("approve"),
    methods=["POST"],
    response_model=ch_schemas.TreatmentPlanOut,
)
router.add_api_route(
    "/treatment-plans/{plan_id}/reject",
    _decide_treatment("reject"),
    methods=["POST"],
    response_model=ch_schemas.TreatmentPlanOut,
)


@router.post("/treatment-plans/{plan_id}/execute", response_model=ch_schemas.TreatmentEventOut, status_code=201)
def execute_treatment_plan(
    plan_id: str,
    payload: ch_schemas.TreatmentEventCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("crophealth.treatment.manage")),
):
    plan = _get_or_404(db, ch_models.TreatmentPlan, plan_id, "Treatment plan")
    assert_farm_scope(db, current_user, "crophealth.treatment.manage", plan.farm_id)
    if plan.status != "approved":
        raise HTTPException(status_code=409, detail="Only an approved plan can be executed")

    event = ch_models.TreatmentEvent(
        tenant_id=current_user.tenant_id,
        plan_id=plan.id,
        farm_id=plan.farm_id,
        applied_at=payload.applied_at or datetime.now(timezone.utc),
        executed_by=current_user.id,
        actual_method=payload.actual_method,
        notes=payload.notes,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(event)
    plan.status = "completed"
    plan.updated_by = current_user.id

    incident = db.get(ch_models.DiseaseIncident, plan.incident_id)
    if incident and "treatment_applied" in ch_models.INCIDENT_ALLOWED_TRANSITIONS.get(incident.status, ()):
        incident.status = "treatment_applied"
        incident.updated_by = current_user.id

    db.flush()
    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="treatment_plan.execute",
        entity_type="treatment_event",
        entity_id=event.id,
        new_values={"plan_id": plan.id},
    )
    db.commit()
    return event
