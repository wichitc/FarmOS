from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ...core.deps import get_current_user, require_permission
from ...database import get_db
from ...foundation import models as fm
from ...foundation import workflow_engine
from ...foundation.audit import record_audit
from ...foundation.schemas import (
    WorkflowDecisionRequest,
    WorkflowDefinitionCreate,
    WorkflowDefinitionOut,
    WorkflowInstanceOut,
    WorkflowSubmitRequest,
)

router = APIRouter(prefix="/api/v1/workflows", tags=["workflow"])


@router.get("/definitions", response_model=list[WorkflowDefinitionOut])
def list_definitions(db: Session = Depends(get_db), _user: fm.User = Depends(get_current_user)):
    return db.query(fm.WorkflowDefinition).order_by(fm.WorkflowDefinition.name.asc()).all()


@router.post("/definitions", response_model=WorkflowDefinitionOut, status_code=201)
def create_definition(
    payload: WorkflowDefinitionCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("workflow.definition.manage")),
):
    definition = fm.WorkflowDefinition(
        tenant_id=current_user.tenant_id,
        entity_type=payload.entity_type,
        name=payload.name,
        steps=payload.steps,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(definition)
    db.flush()
    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="workflow_definition.create",
        entity_type="workflow_definition",
        entity_id=definition.id,
        new_values={"entity_type": definition.entity_type, "name": definition.name, "steps": definition.steps},
    )
    db.commit()
    return definition


def _correlation_id(request: Request) -> str:
    return request.headers.get("x-correlation-id", request.headers.get("X-Correlation-Id", ""))


@router.post("/instances", response_model=WorkflowInstanceOut, status_code=201)
def submit_instance(
    payload: WorkflowSubmitRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("workflow.instance.submit")),
):
    definition = db.get(fm.WorkflowDefinition, payload.workflow_definition_id)
    if not definition or not definition.is_active:
        raise HTTPException(status_code=404, detail="Workflow definition not found or inactive")

    instance = workflow_engine.submit(
        db,
        tenant_id=current_user.tenant_id,
        actor=current_user,
        definition=definition,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        context=payload.context,
        correlation_id=_correlation_id(request),
    )
    db.commit()
    return instance


@router.get("/instances", response_model=list[WorkflowInstanceOut])
def list_instances(db: Session = Depends(get_db), _user: fm.User = Depends(get_current_user)):
    return db.query(fm.WorkflowInstance).order_by(fm.WorkflowInstance.created_at.desc()).all()


def _decide(action: str):
    def handler(
        instance_id: str,
        payload: WorkflowDecisionRequest,
        request: Request,
        db: Session = Depends(get_db),
        current_user: fm.User = Depends(get_current_user),
    ):
        instance = db.get(fm.WorkflowInstance, instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Workflow instance not found")
        definition = db.get(fm.WorkflowDefinition, instance.workflow_definition_id)
        result = workflow_engine.decide(
            db,
            tenant_id=current_user.tenant_id,
            actor=current_user,
            instance=instance,
            definition=definition,
            action=action,
            reason=payload.reason,
            correlation_id=_correlation_id(request),
        )
        db.commit()
        return result

    return handler


router.add_api_route(
    "/instances/{instance_id}/approve", _decide("approve"), methods=["POST"], response_model=WorkflowInstanceOut
)
router.add_api_route(
    "/instances/{instance_id}/reject", _decide("reject"), methods=["POST"], response_model=WorkflowInstanceOut
)
router.add_api_route(
    "/instances/{instance_id}/return", _decide("return"), methods=["POST"], response_model=WorkflowInstanceOut
)
router.add_api_route(
    "/instances/{instance_id}/cancel", _decide("cancel"), methods=["POST"], response_model=WorkflowInstanceOut
)
