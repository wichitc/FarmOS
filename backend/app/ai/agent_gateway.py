"""Agent Action Gateway (FR-AGENT-001/002, AI-004; docs/09-SECURITY-
ARCHITECTURE.md §6). The shared enforcement point every autonomous-agent
action routes through - so L0-L4 classification lives in one place
(mirrors ADR-008's rationale for the model registry: one place to audit,
not N per-agent implementations).

Level semantics adopted here (FR-AGENT-002 names L0-L4 but does not fully
spell out execution mechanics per level, so this is the concrete
interpretation this implementation commits to):

  L0  read-only        - observation/analysis only, no state change. Always allowed.
  L1  advisory          - non-binding artifacts only (e.g. a notification). Always allowed.
  L2  supervised exec   - executes immediately, but only alongside an explicit
                           human confirmation supplied in the *same* request
                           (no async approval queue).
  L3  approved exec     - submitted through `foundation.workflow_engine` (the
                           same mechanism every human-submitted Plan entity
                           uses) and only executes once that instance reaches
                           "approved".
  L4  autonomous exec   - executes with no per-instance human step at all,
                           but only while an active `AgentPolicyGrant` exists
                           for that `action_type`.

FR-AGENT-002's "must never execute above L2 without an explicit auditable
policy grant" for pesticide/pump/procurement/financial/deletion/device-
config actions is enforced as a *ceiling*: `resolve_effective_level` caps
those `action_type`s at L2 unless an active grant exists, and separately,
L4 always requires a grant regardless of action_type (that's what L4
means). Both checks happen once, here, at propose time - not duplicated
per agent or per router.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..foundation import models as fm
from ..foundation import workflow_engine
from ..foundation.audit import record_audit
from . import models as ai_models


def _active_grant(db: Session, tenant_id: str, action_type: str) -> Optional[ai_models.AgentPolicyGrant]:
    return (
        db.query(ai_models.AgentPolicyGrant)
        .filter(
            ai_models.AgentPolicyGrant.tenant_id == tenant_id,
            ai_models.AgentPolicyGrant.action_type == action_type,
            ai_models.AgentPolicyGrant.is_active.is_(True),
        )
        .first()
    )


def resolve_effective_level(
    db: Session, *, tenant_id: str, action_type: str, requested_level: str
) -> tuple[str, Optional[ai_models.AgentPolicyGrant]]:
    if requested_level not in ai_models.ACTION_LEVELS:
        raise HTTPException(status_code=422, detail=f"Unknown action level '{requested_level}'")

    grant = _active_grant(db, tenant_id, action_type)
    level = requested_level

    if level == "L4" and grant is None:
        level = "L3"

    floor_required = action_type in ai_models.ACTION_LEVEL_FLOORS
    if floor_required and level in ("L3", "L4") and grant is None:
        level = "L2"

    return level, grant


def propose_action(
    db: Session,
    *,
    tenant_id: str,
    actor: Optional[fm.User],
    agent_code: str,
    action_type: str,
    requested_level: str,
    entity_type: str,
    entity_id: str,
    farm_id: Optional[str],
    rationale: str,
    input_context: dict,
    correlation_id: Optional[str] = None,
) -> ai_models.AgentAction:
    """Observe -> Analyze -> Recommend. Records the proposal at its
    resolved (possibly downgraded) level; nothing executes yet."""
    level, grant = resolve_effective_level(
        db, tenant_id=tenant_id, action_type=action_type, requested_level=requested_level
    )

    action = ai_models.AgentAction(
        tenant_id=tenant_id,
        agent_code=agent_code,
        action_type=action_type,
        level=level,
        entity_type=entity_type,
        entity_id=entity_id,
        farm_id=farm_id,
        rationale=rationale,
        input_context=input_context,
        status="proposed",
        policy_grant_id=grant.id if (level == "L4" and grant) else None,
        created_by=actor.id if actor else None,
        updated_by=actor.id if actor else None,
    )
    db.add(action)
    db.flush()

    record_audit(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor.id if actor else None,
        action="agent_action.propose",
        entity_type="agent_action",
        entity_id=action.id,
        new_values={"agent_code": agent_code, "action_type": action_type, "level": level},
        correlation_id=correlation_id,
    )
    return action


def submit_for_approval(
    db: Session,
    *,
    action: ai_models.AgentAction,
    actor: fm.User,
    definition: fm.WorkflowDefinition,
    correlation_id: Optional[str] = None,
) -> ai_models.AgentAction:
    if action.level != "L3":
        raise HTTPException(status_code=409, detail=f"Only L3 actions are submitted for approval (this action is {action.level})")
    if action.status != "proposed":
        raise HTTPException(status_code=409, detail=f"Cannot submit an action in status '{action.status}'")

    instance = workflow_engine.submit(
        db,
        tenant_id=action.tenant_id,
        actor=actor,
        definition=definition,
        entity_type="agent_action",
        entity_id=action.id,
        context={"action_type": action.action_type, "farm_id": action.farm_id},
        correlation_id=correlation_id,
    )
    action.workflow_instance_id = instance.id
    action.status = "pending_approval"
    action.updated_by = actor.id
    db.flush()
    return action


def execute_action(
    db: Session,
    *,
    action: ai_models.AgentAction,
    actor: Optional[fm.User],
    confirmed: bool = False,
    result: Optional[dict] = None,
    correlation_id: Optional[str] = None,
) -> ai_models.AgentAction:
    """Execute -> Verify. `result` is the caller-reported outcome (no live
    actuation integration exists yet - same "caller reports what actually
    happened" shape as `IrrigationEvent.actual_volume_liters`)."""
    if action.status not in ("proposed", "approved"):
        raise HTTPException(status_code=409, detail=f"Cannot execute an action in status '{action.status}'")

    if action.level in ("L0", "L1"):
        pass  # always allowed
    elif action.level == "L2":
        if action.status != "proposed":
            raise HTTPException(status_code=409, detail="L2 actions execute directly from 'proposed', not via approval")
        if not confirmed:
            raise HTTPException(status_code=409, detail="L2 actions require an explicit human confirmation to execute")
    elif action.level == "L3":
        if action.status != "approved":
            raise HTTPException(status_code=409, detail="L3 actions require an approved workflow instance before executing")
    elif action.level == "L4":
        grant = _active_grant(db, action.tenant_id, action.action_type)
        if grant is None:
            raise HTTPException(
                status_code=409,
                detail="L4 action has no active policy grant at execution time - resubmit for L3 approval",
            )
        action.policy_grant_id = grant.id

    action.status = "executed"
    action.result = result or {}
    action.executed_at = datetime.now(timezone.utc)
    action.updated_by = actor.id if actor else None
    db.flush()

    record_audit(
        db,
        tenant_id=action.tenant_id,
        actor_user_id=actor.id if actor else None,
        action="agent_action.execute",
        entity_type="agent_action",
        entity_id=action.id,
        new_values={"level": action.level, "result": action.result},
        correlation_id=correlation_id,
    )
    return action
