from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..core.deps import user_has_permission
from . import models as fm
from .audit import record_audit
from .notifications import default_sender

_CONDITION_OPS = {
    "amount_gte": lambda ctx, value: ctx.get("amount", 0) >= value,
    "amount_lt": lambda ctx, value: ctx.get("amount", 0) < value,
}


def _step_applies(step: dict, context: dict) -> bool:
    condition = step.get("condition")
    if not condition:
        return True
    return all(_CONDITION_OPS[key](context, value) for key, value in condition.items() if key in _CONDITION_OPS)


def _applicable_steps(definition: fm.WorkflowDefinition, context: dict) -> list[dict]:
    steps = sorted(definition.steps, key=lambda s: s["step"])
    return [s for s in steps if _step_applies(s, context)]


def submit(
    db: Session,
    *,
    tenant_id: str,
    actor: fm.User,
    definition: fm.WorkflowDefinition,
    entity_type: str,
    entity_id: str,
    context: dict,
    correlation_id: Optional[str] = None,
) -> fm.WorkflowInstance:
    applicable = _applicable_steps(definition, context)
    if not applicable:
        raise HTTPException(status_code=400, detail="No approval steps apply to this submission")

    instance = fm.WorkflowInstance(
        tenant_id=tenant_id,
        workflow_definition_id=definition.id,
        entity_type=entity_type,
        entity_id=entity_id,
        status="submitted",
        current_step_index=0,
        context=context,
        submitted_by=actor.id,
    )
    db.add(instance)
    db.flush()

    db.add(
        fm.WorkflowStepEvent(
            tenant_id=tenant_id,
            workflow_instance_id=instance.id,
            step_index=0,
            action="submit",
            actor_user_id=actor.id,
        )
    )
    record_audit(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor.id,
        action="workflow.submit",
        entity_type="workflow_instance",
        entity_id=instance.id,
        new_values={"status": instance.status, "entity_type": entity_type, "entity_id": entity_id},
        correlation_id=correlation_id,
    )
    _notify_approvers(db, instance, definition, applicable[0], tenant_id)
    return instance


def _notify_approvers(db: Session, instance: fm.WorkflowInstance, definition, step: dict, tenant_id: str) -> None:
    role_code = step.get("approver_role_code")
    if not role_code:
        return
    approvers = (
        db.query(fm.User)
        .join(fm.UserRoleAssignment, fm.UserRoleAssignment.user_id == fm.User.id)
        .join(fm.Role, fm.Role.id == fm.UserRoleAssignment.role_id)
        .filter(fm.Role.code == role_code, fm.User.tenant_id == tenant_id)
        .all()
    )
    for approver in approvers:
        default_sender.send(
            db,
            tenant_id=tenant_id,
            user_id=approver.id,
            title=f"Approval needed: {instance.entity_type}",
            body=f"'{definition.name}' step {step['step']} is waiting on your approval.",
            severity="medium",
            related_entity_type="workflow_instance",
            related_entity_id=instance.id,
        )


def _require_current_step_approver(
    db: Session, instance: fm.WorkflowInstance, definition: fm.WorkflowDefinition, actor: fm.User
) -> dict:
    applicable = _applicable_steps(definition, instance.context)
    if instance.current_step_index >= len(applicable):
        raise HTTPException(status_code=409, detail="Workflow instance has no remaining steps")
    step = applicable[instance.current_step_index]
    role_code = step.get("approver_role_code")
    if role_code:
        has_role = (
            db.query(fm.UserRoleAssignment)
            .join(fm.Role, fm.Role.id == fm.UserRoleAssignment.role_id)
            .filter(fm.UserRoleAssignment.user_id == actor.id, fm.Role.code == role_code)
            .first()
        )
        if not has_role and not user_has_permission(db, actor, "workflow.instance.approve"):
            raise HTTPException(status_code=403, detail=f"Requires role '{role_code}' or workflow.instance.approve")
    return step, applicable


def decide(
    db: Session,
    *,
    tenant_id: str,
    actor: fm.User,
    instance: fm.WorkflowInstance,
    definition: fm.WorkflowDefinition,
    action: str,
    reason: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> fm.WorkflowInstance:
    if instance.status != "submitted":
        raise HTTPException(status_code=409, detail=f"Cannot {action} a workflow in status '{instance.status}'")
    if action not in ("approve", "reject", "return", "cancel"):
        raise HTTPException(status_code=400, detail=f"Unsupported action '{action}'")

    step, applicable = _require_current_step_approver(db, instance, definition, actor)
    old_status = instance.status

    if action == "approve":
        if instance.current_step_index + 1 >= len(applicable):
            instance.status = "approved"
        else:
            instance.current_step_index += 1
            _notify_approvers(db, instance, definition, applicable[instance.current_step_index], tenant_id)
    elif action == "reject":
        instance.status = "rejected"
    elif action == "return":
        instance.status = "draft"
        instance.current_step_index = 0
    elif action == "cancel":
        instance.status = "cancelled"

    db.add(
        fm.WorkflowStepEvent(
            tenant_id=tenant_id,
            workflow_instance_id=instance.id,
            step_index=step["step"],
            action=action,
            actor_user_id=actor.id,
            reason=reason,
        )
    )
    record_audit(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor.id,
        action=f"workflow.{action}",
        entity_type="workflow_instance",
        entity_id=instance.id,
        old_values={"status": old_status},
        new_values={"status": instance.status},
        reason=reason,
        correlation_id=correlation_id,
    )

    if instance.submitted_by and action in ("approve", "reject", "return"):
        default_sender.send(
            db,
            tenant_id=tenant_id,
            user_id=instance.submitted_by,
            title=f"Your submission was {instance.status}",
            body=reason or "",
            severity="info" if action == "approve" else "medium",
            related_entity_type="workflow_instance",
            related_entity_id=instance.id,
        )
    db.flush()
    return instance
