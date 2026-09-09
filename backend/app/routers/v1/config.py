from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.deps import require_permission
from ...database import get_db
from ...foundation import models as fm
from ...foundation.audit import record_audit
from ...foundation.schemas import TenantConfigOut, TenantConfigSet

router = APIRouter(prefix="/api/v1/config", tags=["config"])


@router.get("", response_model=list[TenantConfigOut])
def list_config(
    db: Session = Depends(get_db),
    _user: fm.User = Depends(require_permission("platform.config.manage")),
):
    return db.query(fm.TenantConfig).order_by(fm.TenantConfig.key.asc()).all()


@router.put("", response_model=TenantConfigOut)
def set_config(
    payload: TenantConfigSet,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("platform.config.manage")),
):
    existing = (
        db.query(fm.TenantConfig)
        .filter(fm.TenantConfig.tenant_id == current_user.tenant_id, fm.TenantConfig.key == payload.key)
        .one_or_none()
    )
    old_value = existing.value if existing else None
    if existing:
        existing.value = payload.value
        existing.updated_by = current_user.id
        entry = existing
    else:
        entry = fm.TenantConfig(
            tenant_id=current_user.tenant_id,
            key=payload.key,
            value=payload.value,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        db.add(entry)
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="config.set",
        entity_type="tenant_config",
        entity_id=entry.id,
        old_values={"value": old_value},
        new_values={"value": payload.value},
    )
    db.commit()
    return entry
