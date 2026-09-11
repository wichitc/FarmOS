from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...core.deps import assert_farm_scope, require_permission, user_has_permission
from ...database import get_db
from ...farm import models as farm_models
from ...foundation import models as fm
from ...foundation.audit import record_audit
from ...work import models as work_models
from ...work import schemas as work_schemas

router = APIRouter(prefix="/api/v1/work", tags=["work"])


def _get_or_404(db: Session, model, obj_id: str, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


def _assert_assignee_or_manager(db: Session, user: fm.User, task: work_models.WorkTask) -> None:
    """The assignee runs their own accept/start/complete; a supervisor
    holding `work.task.manage` may act on a worker's behalf (matches
    `workflow_engine._require_current_step_approver`'s role-match-OR-
    broader-permission shape)."""
    if user.id == task.assigned_to:
        return
    if user_has_permission(db, user, "work.task.manage"):
        return
    raise HTTPException(status_code=403, detail="Only the assigned worker or a work.task.manage holder can do this")


@router.post("/farms/{farm_id}/tasks", response_model=work_schemas.WorkTaskOut, status_code=201)
def create_task(
    farm_id: str,
    payload: work_schemas.WorkTaskCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("work.task.manage")),
):
    """Request stage."""
    farm = _get_or_404(db, farm_models.Farm, farm_id, "Farm")
    assert_farm_scope(db, current_user, "work.task.manage", farm.id)
    if payload.work_type not in work_models.WORK_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown work type '{payload.work_type}'")
    if payload.plot_id:
        _get_or_404(db, farm_models.Plot, payload.plot_id, "Plot")

    task = work_models.WorkTask(
        tenant_id=current_user.tenant_id,
        farm_id=farm.id,
        plot_id=payload.plot_id,
        work_type=payload.work_type,
        title=payload.title,
        description=payload.description,
        source_type=payload.source_type,
        source_id=payload.source_id,
        requested_by=current_user.id,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(task)
    db.flush()
    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="work_task.request", entity_type="work_task", entity_id=task.id,
        new_values={"farm_id": farm.id, "work_type": task.work_type},
    )
    db.commit()
    return task


@router.get("/farms/{farm_id}/tasks", response_model=list[work_schemas.WorkTaskOut])
def list_tasks(
    farm_id: str,
    status: Optional[str] = Query(default=None),
    assigned_to: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("work.task.view")),
):
    assert_farm_scope(db, user, "work.task.view", farm_id)
    query = db.query(work_models.WorkTask).filter(work_models.WorkTask.farm_id == farm_id)
    if status:
        query = query.filter(work_models.WorkTask.status == status)
    if assigned_to:
        query = query.filter(work_models.WorkTask.assigned_to == assigned_to)
    return query.order_by(work_models.WorkTask.created_at.desc()).all()


@router.get("/tasks/{task_id}", response_model=work_schemas.WorkTaskOut)
def get_task(
    task_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("work.task.view")),
):
    task = _get_or_404(db, work_models.WorkTask, task_id, "Work task")
    assert_farm_scope(db, user, "work.task.view", task.farm_id)
    return task


@router.post("/tasks/{task_id}/plan", response_model=work_schemas.WorkTaskOut)
def plan_task(
    task_id: str,
    payload: work_schemas.WorkTaskPlanRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("work.task.manage")),
):
    """Plan stage: requested -> planned."""
    task = _get_or_404(db, work_models.WorkTask, task_id, "Work task")
    assert_farm_scope(db, current_user, "work.task.manage", task.farm_id)
    if task.status != "requested":
        raise HTTPException(status_code=409, detail=f"Cannot plan a task in status '{task.status}'")

    task.status = "planned"
    task.scheduled_for = payload.scheduled_for
    task.updated_by = current_user.id
    db.commit()
    return task


@router.post("/tasks/{task_id}/assign", response_model=work_schemas.WorkTaskOut)
def assign_task(
    task_id: str,
    payload: work_schemas.WorkTaskAssignRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("work.task.manage")),
):
    """Assign stage: planned -> assigned."""
    task = _get_or_404(db, work_models.WorkTask, task_id, "Work task")
    assert_farm_scope(db, current_user, "work.task.manage", task.farm_id)
    if task.status != "planned":
        raise HTTPException(status_code=409, detail=f"Cannot assign a task in status '{task.status}'")

    task.status = "assigned"
    task.assigned_to = payload.assigned_to
    task.assigned_at = datetime.now(timezone.utc)
    task.updated_by = current_user.id
    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="work_task.assign", entity_type="work_task", entity_id=task.id,
        new_values={"assigned_to": payload.assigned_to},
    )
    db.commit()
    return task


def _decide_assignment(accept: bool):
    """Accept stage: assigned -> accepted or rejected."""

    def handler(
        task_id: str,
        payload: work_schemas.WorkTaskAcceptDecisionRequest,
        db: Session = Depends(get_db),
        current_user: fm.User = Depends(require_permission("work.task.execute")),
    ):
        task = _get_or_404(db, work_models.WorkTask, task_id, "Work task")
        assert_farm_scope(db, current_user, "work.task.execute", task.farm_id)
        _assert_assignee_or_manager(db, current_user, task)
        if task.status != "assigned":
            raise HTTPException(status_code=409, detail=f"Cannot accept/reject a task in status '{task.status}'")

        if accept:
            task.status = "accepted"
            task.accepted_at = datetime.now(timezone.utc)
        else:
            task.status = "rejected"
            task.cancel_reason = payload.reason
        task.updated_by = current_user.id
        db.commit()
        return task

    return handler


router.add_api_route("/tasks/{task_id}/accept", _decide_assignment(True), methods=["POST"], response_model=work_schemas.WorkTaskOut)
router.add_api_route("/tasks/{task_id}/reject", _decide_assignment(False), methods=["POST"], response_model=work_schemas.WorkTaskOut)


@router.post("/tasks/{task_id}/start", response_model=work_schemas.WorkTaskOut)
def start_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("work.task.execute")),
):
    """Execute stage: accepted -> in_progress."""
    task = _get_or_404(db, work_models.WorkTask, task_id, "Work task")
    assert_farm_scope(db, current_user, "work.task.execute", task.farm_id)
    _assert_assignee_or_manager(db, current_user, task)
    if task.status != "accepted":
        raise HTTPException(status_code=409, detail=f"Cannot start a task in status '{task.status}'")

    task.status = "in_progress"
    task.started_at = datetime.now(timezone.utc)
    task.updated_by = current_user.id
    db.commit()
    return task


@router.post("/tasks/{task_id}/complete", response_model=work_schemas.WorkTaskOut)
def complete_task(
    task_id: str,
    payload: work_schemas.WorkTaskCompleteRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("work.task.execute")),
):
    """Evidence + Complete stage: in_progress -> completed (awaiting
    supervisor review). `evidence` is the photos/measurements/materials/
    labor payload FR-WORK-003's mobile capture UI would populate - stored
    as-is here since there is no capture UI yet to validate its shape
    further."""
    task = _get_or_404(db, work_models.WorkTask, task_id, "Work task")
    assert_farm_scope(db, current_user, "work.task.execute", task.farm_id)
    _assert_assignee_or_manager(db, current_user, task)
    if task.status != "in_progress":
        raise HTTPException(status_code=409, detail=f"Cannot complete a task in status '{task.status}'")

    task.status = "completed"
    task.completed_at = datetime.now(timezone.utc)
    task.evidence = payload.evidence
    task.updated_by = current_user.id
    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="work_task.complete", entity_type="work_task", entity_id=task.id,
        new_values={"evidence_keys": list(payload.evidence.keys())},
    )
    db.commit()
    return task


@router.post("/tasks/{task_id}/review", response_model=work_schemas.WorkTaskOut)
def review_task(
    task_id: str,
    payload: work_schemas.WorkTaskReviewRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("work.task.review")),
):
    """Supervisor Review + Close stage: completed -> closed, or sent back
    to in_progress for rework."""
    task = _get_or_404(db, work_models.WorkTask, task_id, "Work task")
    assert_farm_scope(db, current_user, "work.task.review", task.farm_id)
    if task.status != "completed":
        raise HTTPException(status_code=409, detail=f"Cannot review a task in status '{task.status}'")
    if payload.decision not in ("close", "send_back"):
        raise HTTPException(status_code=422, detail=f"Unknown decision '{payload.decision}'")

    task.status = "closed" if payload.decision == "close" else "in_progress"
    task.reviewed_by = current_user.id
    task.reviewed_at = datetime.now(timezone.utc)
    task.review_notes = payload.notes
    task.updated_by = current_user.id
    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="work_task.review", entity_type="work_task", entity_id=task.id,
        new_values={"decision": payload.decision, "status": task.status},
    )
    db.commit()
    return task


@router.post("/tasks/{task_id}/cancel", response_model=work_schemas.WorkTaskOut)
def cancel_task(
    task_id: str,
    payload: work_schemas.WorkTaskCancelRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("work.task.manage")),
):
    task = _get_or_404(db, work_models.WorkTask, task_id, "Work task")
    assert_farm_scope(db, current_user, "work.task.manage", task.farm_id)
    if task.status in ("closed", "cancelled", "rejected"):
        raise HTTPException(status_code=409, detail=f"Cannot cancel a task in status '{task.status}'")

    task.status = "cancelled"
    task.cancel_reason = payload.reason
    task.updated_by = current_user.id
    db.commit()
    return task
