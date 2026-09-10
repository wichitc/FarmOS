from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ...ai import agent_gateway
from ...ai import copilot
from ...ai import models as ai_models
from ...ai import schemas as ai_schemas
from ...core.deps import assert_farm_scope, require_permission
from ...database import get_db
from ...foundation import models as fm
from ...foundation import workflow_engine
from ...foundation.audit import record_audit

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


def _get_or_404(db: Session, model, obj_id: str, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


def _assert_optional_farm_scope(db: Session, user: fm.User, permission_code: str, farm_id: Optional[str]) -> None:
    if farm_id is not None:
        assert_farm_scope(db, user, permission_code, farm_id)


def _correlation_id(request: Request) -> str:
    return request.headers.get("x-correlation-id", "")


# ---------------------------------------------------------------------------
# AI Model Registry (FR-AIML-001, ADR-008)
# ---------------------------------------------------------------------------

@router.get("/models", response_model=list[ai_schemas.AIModelOut])
def list_models(db: Session = Depends(get_db), user: fm.User = Depends(require_permission("ai.model.view"))):
    return db.query(ai_models.AIModel).order_by(ai_models.AIModel.code.asc()).all()


@router.get("/models/{model_id}/versions", response_model=list[ai_schemas.ModelVersionOut])
def list_model_versions(
    model_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("ai.model.view")),
):
    _get_or_404(db, ai_models.AIModel, model_id, "AI model")
    return (
        db.query(ai_models.ModelVersion)
        .filter(ai_models.ModelVersion.model_id == model_id)
        .order_by(ai_models.ModelVersion.released_at.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Predictions (AI-001 envelope)
# ---------------------------------------------------------------------------

@router.get("/predictions", response_model=list[ai_schemas.PredictionOut])
def list_predictions(
    entity_type: Optional[str] = Query(default=None),
    entity_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("ai.prediction.view")),
):
    query = db.query(ai_models.Prediction)
    if entity_type:
        query = query.filter(ai_models.Prediction.entity_type == entity_type)
    if entity_id:
        query = query.filter(ai_models.Prediction.entity_id == entity_id)
    return query.order_by(ai_models.Prediction.predicted_at.desc()).all()


@router.post("/predictions/{prediction_id}/feedback", response_model=ai_schemas.PredictionFeedbackOut, status_code=201)
def submit_prediction_feedback(
    prediction_id: str,
    payload: ai_schemas.PredictionFeedbackCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("ai.prediction.manage")),
):
    _get_or_404(db, ai_models.Prediction, prediction_id, "Prediction")
    if payload.status not in ai_models.FEEDBACK_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown feedback status '{payload.status}'")

    feedback = ai_models.PredictionFeedback(
        tenant_id=current_user.tenant_id,
        prediction_id=prediction_id,
        status=payload.status,
        corrected_value=payload.corrected_value,
        notes=payload.notes,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(feedback)
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="prediction_feedback.create",
        entity_type="ai_prediction_feedback",
        entity_id=feedback.id,
        new_values={"prediction_id": prediction_id, "status": payload.status},
    )
    db.commit()
    return feedback


# ---------------------------------------------------------------------------
# Agent Action Gateway (FR-AGENT-001/002, AI-004)
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


@router.post("/agent-actions", response_model=ai_schemas.AgentActionOut, status_code=201)
def propose_agent_action(
    payload: ai_schemas.AgentActionPropose,
    request: Request,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("ai.agent.propose")),
):
    _assert_optional_farm_scope(db, current_user, "ai.agent.propose", payload.farm_id)
    action = agent_gateway.propose_action(
        db,
        tenant_id=current_user.tenant_id,
        actor=current_user,
        agent_code=payload.agent_code,
        action_type=payload.action_type,
        requested_level=payload.requested_level,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        farm_id=payload.farm_id,
        rationale=payload.rationale,
        input_context=payload.input_context,
        correlation_id=_correlation_id(request),
    )
    db.commit()
    return action


@router.get("/agent-actions", response_model=list[ai_schemas.AgentActionOut])
def list_agent_actions(
    farm_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("ai.agent.propose")),
):
    if farm_id:
        assert_farm_scope(db, user, "ai.agent.propose", farm_id)
    query = db.query(ai_models.AgentAction)
    if farm_id:
        query = query.filter(ai_models.AgentAction.farm_id == farm_id)
    if status:
        query = query.filter(ai_models.AgentAction.status == status)
    return query.order_by(ai_models.AgentAction.created_at.desc()).all()


@router.get("/agent-actions/{action_id}", response_model=ai_schemas.AgentActionOut)
def get_agent_action(
    action_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("ai.agent.propose")),
):
    action = _get_or_404(db, ai_models.AgentAction, action_id, "Agent action")
    _assert_optional_farm_scope(db, user, "ai.agent.propose", action.farm_id)
    return action


@router.post("/agent-actions/{action_id}/submit", response_model=ai_schemas.AgentActionOut)
def submit_agent_action(
    action_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("ai.agent.approve")),
):
    action = _get_or_404(db, ai_models.AgentAction, action_id, "Agent action")
    _assert_optional_farm_scope(db, current_user, "ai.agent.approve", action.farm_id)
    definition = _active_definition(db, current_user.tenant_id, "agent_action")
    agent_gateway.submit_for_approval(
        db, action=action, actor=current_user, definition=definition, correlation_id=_correlation_id(request)
    )
    db.commit()
    return action


def _decide_agent_action(action_name: str):
    def handler(
        action_id: str,
        payload: ai_schemas.ApprovalDecisionRequest,
        request: Request,
        db: Session = Depends(get_db),
        current_user: fm.User = Depends(require_permission("ai.agent.approve")),
    ):
        action = _get_or_404(db, ai_models.AgentAction, action_id, "Agent action")
        _assert_optional_farm_scope(db, current_user, "ai.agent.approve", action.farm_id)
        if not action.workflow_instance_id:
            raise HTTPException(status_code=409, detail="Action has not been submitted for approval")

        instance = _get_or_404(db, fm.WorkflowInstance, action.workflow_instance_id, "Workflow instance")
        definition = db.get(fm.WorkflowDefinition, instance.workflow_definition_id)
        workflow_engine.decide(
            db,
            tenant_id=current_user.tenant_id,
            actor=current_user,
            instance=instance,
            definition=definition,
            action=action_name,
            reason=payload.reason,
            correlation_id=_correlation_id(request),
        )
        if instance.status == "approved":
            action.status = "approved"
        elif instance.status in ("rejected", "cancelled"):
            action.status = "rejected"
        elif instance.status == "draft":
            action.status = "proposed"
        action.updated_by = current_user.id
        db.commit()
        return action

    return handler


router.add_api_route(
    "/agent-actions/{action_id}/approve",
    _decide_agent_action("approve"),
    methods=["POST"],
    response_model=ai_schemas.AgentActionOut,
)
router.add_api_route(
    "/agent-actions/{action_id}/reject",
    _decide_agent_action("reject"),
    methods=["POST"],
    response_model=ai_schemas.AgentActionOut,
)


@router.post("/agent-actions/{action_id}/execute", response_model=ai_schemas.AgentActionOut)
def execute_agent_action(
    action_id: str,
    payload: ai_schemas.AgentActionExecuteRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("ai.agent.execute")),
):
    action = _get_or_404(db, ai_models.AgentAction, action_id, "Agent action")
    _assert_optional_farm_scope(db, current_user, "ai.agent.execute", action.farm_id)
    agent_gateway.execute_action(
        db,
        action=action,
        actor=current_user,
        confirmed=payload.confirmed,
        result=payload.result,
        correlation_id=_correlation_id(request),
    )
    db.commit()
    return action


# ---------------------------------------------------------------------------
# Agent policy grants (the only path to L4)
# ---------------------------------------------------------------------------

@router.post("/agent-policy-grants", response_model=ai_schemas.AgentPolicyGrantOut, status_code=201)
def create_policy_grant(
    payload: ai_schemas.AgentPolicyGrantCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("ai.agent.policy.manage")),
):
    grant = ai_models.AgentPolicyGrant(
        tenant_id=current_user.tenant_id,
        action_type=payload.action_type,
        is_active=True,
        granted_by=current_user.id,
        granted_at=datetime.now(timezone.utc),
        notes=payload.notes,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(grant)
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="agent_policy_grant.create",
        entity_type="agent_policy_grant",
        entity_id=grant.id,
        new_values={"action_type": grant.action_type},
    )
    db.commit()
    return grant


@router.get("/agent-policy-grants", response_model=list[ai_schemas.AgentPolicyGrantOut])
def list_policy_grants(
    db: Session = Depends(get_db), user: fm.User = Depends(require_permission("ai.agent.policy.manage"))
):
    return db.query(ai_models.AgentPolicyGrant).order_by(ai_models.AgentPolicyGrant.granted_at.desc()).all()


@router.post("/agent-policy-grants/{grant_id}/revoke", response_model=ai_schemas.AgentPolicyGrantOut)
def revoke_policy_grant(
    grant_id: str,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("ai.agent.policy.manage")),
):
    grant = _get_or_404(db, ai_models.AgentPolicyGrant, grant_id, "Policy grant")
    grant.is_active = False
    grant.updated_by = current_user.id
    db.flush()
    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="agent_policy_grant.revoke",
        entity_type="agent_policy_grant",
        entity_id=grant.id,
        new_values={"is_active": False},
    )
    db.commit()
    return grant


# ---------------------------------------------------------------------------
# Copilot (FR-COPILOT-001)
# ---------------------------------------------------------------------------

@router.post("/copilot/ask", response_model=ai_schemas.CopilotAskResponse)
def ask_copilot(
    payload: ai_schemas.CopilotAskRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("ai.copilot.use")),
):
    _assert_optional_farm_scope(db, current_user, "ai.copilot.use", payload.farm_id)

    if payload.conversation_id:
        conversation = _get_or_404(db, ai_models.CopilotConversation, payload.conversation_id, "Conversation")
        _assert_optional_farm_scope(db, current_user, "ai.copilot.use", conversation.farm_id)
    else:
        conversation = ai_models.CopilotConversation(
            tenant_id=current_user.tenant_id,
            farm_id=payload.farm_id,
            title=payload.question[:255],
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        db.add(conversation)
        db.flush()

    db.add(
        ai_models.CopilotMessage(
            tenant_id=current_user.tenant_id,
            conversation_id=conversation.id,
            role="user",
            content=payload.question,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
    )

    result = copilot.answer_question(
        db, tenant_id=current_user.tenant_id, farm_id=payload.farm_id, question=payload.question
    )

    db.add(
        ai_models.CopilotMessage(
            tenant_id=current_user.tenant_id,
            conversation_id=conversation.id,
            role="assistant",
            content=result.content,
            citations=result.citations,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
    )
    db.commit()
    return ai_schemas.CopilotAskResponse(conversation_id=conversation.id, answer=result.content, citations=result.citations)
