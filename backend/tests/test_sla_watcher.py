from datetime import datetime, timedelta, timezone

from app.crm import models as crm_models
from app.crm.service import check_sla_breaches

from .test_crm import _create_ticket, _make_super_admin


def _backdate_sla(raw_db, ticket_id: str, hours_ago: float) -> None:
    ticket = raw_db.get(crm_models.SupportTicket, ticket_id)
    ticket.sla_due_at = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    raw_db.commit()


def test_check_sla_breaches_flags_overdue_open_ticket(client, tenant, raw_db):
    headers = tenant.auth_headers(client)
    ticket = _create_ticket(client, headers, priority="urgent")
    _backdate_sla(raw_db, ticket["id"], hours_ago=1)

    breached = check_sla_breaches(raw_db)
    assert ticket["id"] in [t.id for t in breached]

    row = raw_db.get(crm_models.SupportTicket, ticket["id"])
    assert row.sla_breached_at is not None


def test_check_sla_breaches_ignores_tickets_not_yet_due(client, tenant, raw_db):
    ticket = _create_ticket(client, tenant.auth_headers(client), priority="low")  # sla_due_at far in the future

    breached = check_sla_breaches(raw_db)
    assert ticket["id"] not in [t.id for t in breached]


def test_check_sla_breaches_ignores_resolved_tickets(client, tenant, raw_db):
    _make_super_admin(raw_db, tenant)
    headers = tenant.auth_headers(client)
    ticket = _create_ticket(client, headers, priority="urgent")
    _backdate_sla(raw_db, ticket["id"], hours_ago=1)

    resolve_res = client.patch(f"/api/v1/crm/tickets/{ticket['id']}", json={"status": "resolved"}, headers=headers)
    assert resolve_res.status_code == 200, resolve_res.text

    breached = check_sla_breaches(raw_db)
    assert ticket["id"] not in [t.id for t in breached]

    row = raw_db.get(crm_models.SupportTicket, ticket["id"])
    assert row.sla_breached_at is None


def test_check_sla_breaches_is_idempotent(client, tenant, raw_db):
    headers = tenant.auth_headers(client)
    ticket = _create_ticket(client, headers, priority="urgent")
    _backdate_sla(raw_db, ticket["id"], hours_ago=1)

    first = check_sla_breaches(raw_db)
    assert ticket["id"] in [t.id for t in first]

    second = check_sla_breaches(raw_db)
    assert ticket["id"] not in [t.id for t in second]
