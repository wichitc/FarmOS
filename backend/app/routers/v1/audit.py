from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...core.deps import require_permission
from ...database import get_db
from ...foundation import models as fm
from ...foundation.schemas import AuditEntryOut

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("", response_model=list[AuditEntryOut])
def list_audit_entries(
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
    _user: fm.User = Depends(require_permission("platform.audit.view")),
):
    q = db.query(fm.AuditEntry)
    if entity_type:
        q = q.filter(fm.AuditEntry.entity_type == entity_type)
    if entity_id:
        q = q.filter(fm.AuditEntry.entity_id == entity_id)
    return q.order_by(fm.AuditEntry.created_at.desc()).limit(limit).all()
