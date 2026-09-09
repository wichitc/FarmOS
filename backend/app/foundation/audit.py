from typing import Optional

from sqlalchemy.orm import Session

from . import models as fm


def record_audit(
    db: Session,
    *,
    tenant_id: str,
    actor_user_id: Optional[str],
    action: str,
    entity_type: str,
    entity_id: str,
    old_values: Optional[dict] = None,
    new_values: Optional[dict] = None,
    reason: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> fm.AuditEntry:
    """Writes one append-only audit record (BR-004, FR-PLT-007).

    Called in the same transaction/session as the state change it documents,
    never fire-and-forget, so an audit record can never be silently lost to a
    downstream failure (09-SECURITY-ARCHITECTURE.md §7).
    """
    entry = fm.AuditEntry(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values=old_values,
        new_values=new_values,
        reason=reason,
        correlation_id=correlation_id,
    )
    db.add(entry)
    db.flush()
    return entry
