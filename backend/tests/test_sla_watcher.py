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


def test_check_sla_breaches_emails_the_assigned_staff_member(client, tenant, raw_db, monkeypatch):
    """Master-prompt integration, Phase 42: a breach emails the ticket's
    assigned staff member, the one real recipient this platform can
    resolve. No live SendGrid key exists in this test environment, so
    `core.email.send_email` is monkeypatched to capture the call."""
    from app.crm import service as crm_service

    calls = []
    monkeypatch.setattr(crm_service.email, "send_email", lambda **kw: calls.append(kw) or True)

    _make_super_admin(raw_db, tenant)
    headers = tenant.auth_headers(client)
    ticket = _create_ticket(client, headers, priority="urgent")
    assign_res = client.patch(f"/api/v1/crm/tickets/{ticket['id']}", json={"assigned_to": tenant.admin_user_id}, headers=headers)
    assert assign_res.status_code == 200, assign_res.text
    _backdate_sla(raw_db, ticket["id"], hours_ago=1)

    # No tenant context set here on purpose - `check_sla_breaches` must
    # set it itself per-ticket (this sweep runs with none set at all,
    # the same real bug the watcher script's own loop would have hit).
    check_sla_breaches(raw_db)
    assert len(calls) == 1
    assert calls[0]["to"] == tenant.admin_email


def test_check_sla_breaches_skips_email_for_unassigned_ticket(client, tenant, raw_db, monkeypatch):
    from app.crm import service as crm_service

    calls = []
    monkeypatch.setattr(crm_service.email, "send_email", lambda **kw: calls.append(kw) or True)

    headers = tenant.auth_headers(client)
    ticket = _create_ticket(client, headers, priority="urgent")
    _backdate_sla(raw_db, ticket["id"], hours_ago=1)

    check_sla_breaches(raw_db)
    assert calls == []
