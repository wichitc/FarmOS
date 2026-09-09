from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...core.deps import get_current_user, require_permission
from ...database import get_db
from ...foundation import models as fm
from ...foundation.audit import record_audit
from ...foundation.schemas import PermissionOut, RoleAssignmentCreate, RoleAssignmentOut, RoleOut

router = APIRouter(prefix="/api/v1", tags=["roles"])


@router.get("/roles", response_model=list[RoleOut])
def list_roles(db: Session = Depends(get_db), _user: fm.User = Depends(get_current_user)):
    return db.query(fm.Role).order_by(fm.Role.name.asc()).all()


@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(db: Session = Depends(get_db), _user: fm.User = Depends(get_current_user)):
    return db.query(fm.Permission).order_by(fm.Permission.code.asc()).all()


@router.post("/role-assignments", response_model=RoleAssignmentOut, status_code=201)
def assign_role(
    payload: RoleAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("platform.role.assign")),
):
    target_user = db.get(fm.User, payload.user_id)
    role = db.get(fm.Role, payload.role_id)
    if not target_user or not role:
        raise HTTPException(status_code=404, detail="User or role not found")

    assignment = fm.UserRoleAssignment(
        tenant_id=current_user.tenant_id,
        user_id=payload.user_id,
        role_id=payload.role_id,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
    )
    db.add(assignment)
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="role.assign",
        entity_type="user_role_assignment",
        entity_id=assignment.id,
        new_values={
            "user_id": payload.user_id,
            "role_id": payload.role_id,
            "scope_type": payload.scope_type,
            "scope_id": payload.scope_id,
        },
    )
    db.commit()
    return assignment
