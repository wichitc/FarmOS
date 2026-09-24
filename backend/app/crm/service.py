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

Master-prompt integration, Phase 42: a breach now emails the ticket's
assigned staff member, if it has one - the real recipient this platform
can actually resolve (`SupportTicket.assigned_to` -> `User.email`).
An unassigned ticket gets no email, since there's no staff distribution
list/queue-owner concept to fall back on; that's a documented gap, not
a silent one (see the RTM deferral note).
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..core import email
from ..core.deps import set_tenant_context
from ..foundation import models as fm
from . import models as crm_models

logger = logging.getLogger(__name__)

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

    for ticket in overdue:
        if not ticket.assigned_to or not ticket.tenant_id:
            continue
        # `User` is RLS-protected (unlike `SupportTicket` itself, Phase
        # 20) - this sweep runs with no tenant context set at all (a
        # single global query across every tenant's tickets), so it has
        # to be set per-ticket, right before this lookup, not once for
        # the whole function the way a per-tenant loop would.
        set_tenant_context(db, ticket.tenant_id)
        assignee = db.get(fm.User, ticket.assigned_to)
        if assignee is None:
            continue
        try:
            email.send_email(
                to=assignee.email,
                subject=f"SLA breach: {ticket.subject}",
                body=f"Ticket '{ticket.subject}' (priority: {ticket.priority}) has breached its SLA and is still {ticket.status}.",
            )
        except email.EmailSendError:
            logger.exception("failed to send SLA-breach email for ticket %s", ticket.id)

    return overdue
