"""SLA breach detection (master-prompt integration, Phase 33) - FR-SUPPORT's
`sla_due_at` (Phase 20) was computed at ticket creation but nothing ever
watched for it passing, a deferral flagged explicitly at the time and
again on `iot_models.Alert`'s own docstring ("needs a scheduler this repo
doesn't have"). `check_sla_breaches` is the pure, testable check;
`app/scripts/sla_watcher.py` is the simplest real scheduler this
platform needs to run it - a polling loop, not a cron dependency.

`SupportTicket` is platform-global (`PlatformEntityMixin`, not RLS-
protected - support staff need cross-tenant visibility, Phase 20), so
this check runs once across every tenant's tickets in a single query,
unlike `iot.ingestion.check_offline_devices`'s per-tenant RLS loop.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import models as crm_models

OPEN_TICKET_STATUSES = ("open", "in_progress", "waiting_on_customer")


def check_sla_breaches(db: Session) -> list[crm_models.SupportTicket]:
    """Flags every still-open ticket whose `sla_due_at` has passed and
    that hasn't already been flagged - idempotent, so a repeated sweep
    (this function is meant to be called on a loop) never re-flags or
    double-counts the same breach. Returns the newly-flagged tickets."""
    now = datetime.now(timezone.utc)
    overdue = (
        db.query(crm_models.SupportTicket)
        .filter(
            crm_models.SupportTicket.status.in_(OPEN_TICKET_STATUSES),
            crm_models.SupportTicket.sla_due_at.isnot(None),
            crm_models.SupportTicket.sla_due_at < now,
            crm_models.SupportTicket.sla_breached_at.is_(None),
        )
        .all()
    )
    for ticket in overdue:
        ticket.sla_breached_at = now
    db.commit()
    return overdue
