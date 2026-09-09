from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.deps import get_current_user, require_permission
from ...core.security import hash_password
from ...database import get_db
from ...foundation import models as fm
from ...foundation.audit import record_audit
from ...foundation.schemas import UserCreate, UserOut

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(get_current_user),
):
    # RLS already restricts this to the caller's own tenant; no explicit
    # tenant_id filter needed (and adding one would be redundant, not safer).
    return db.query(fm.User).order_by(fm.User.email.asc()).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("platform.user.manage")),
):
    user = fm.User(
        tenant_id=current_user.tenant_id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A user with this email already exists") from exc

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="user.create",
        entity_type="user",
        entity_id=user.id,
        new_values={"email": user.email, "full_name": user.full_name},
    )
    db.commit()
    return user
