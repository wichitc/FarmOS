from app.core.deps import set_tenant_context
from app.foundation import models as fm

from .conftest import provision_test_tenant, unique_slug


def _make_super_admin(raw_db, tenant):
    set_tenant_context(raw_db, tenant.tenant_id)
    user = raw_db.get(fm.User, tenant.admin_user_id)
    user.is_platform_super_admin = True
    raw_db.commit()


def _capture_lead(client, email_prefix="lead"):
    res = client.post(
        "/api/v1/crm/leads",
        json={
            "name": "Somchai Farmer",
            "company": "Somchai Durian Orchard",
            "email": f"{email_prefix}-{unique_slug('l')}@example.com",
            "phone": "0812345678",
            "farm_type": "durian",
            "farm_area_rai": 50,
            "interest": "AI irrigation",
            "message": "Interested in a demo",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_public_lead_capture_requires_no_auth(client):
    lead = _capture_lead(client)
    assert lead["status"] == "new"
    assert lead["source"] == "landing_page"


def test_non_super_admin_is_denied_crm_access(client, tenant):
    headers = tenant.auth_headers(client)  # tenant_admin, not platform super admin
    res = client.get("/api/v1/crm/leads", headers=headers)
    assert res.status_code == 403


def test_lead_status_lifecycle_and_validation(client, tenant, raw_db):
    _make_super_admin(raw_db, tenant)
    headers = tenant.auth_headers(client)
    lead = _capture_lead(client, email_prefix="lifecycle")

    invalid_res = client.patch(f"/api/v1/crm/leads/{lead['id']}", json={"status": "bogus"}, headers=headers)
    assert invalid_res.status_code == 422

    qualify_res = client.patch(
        f"/api/v1/crm/leads/{lead['id']}", json={"status": "qualified", "score": 80}, headers=headers
    )
    assert qualify_res.status_code == 200, qualify_res.text
    assert qualify_res.json()["status"] == "qualified"
    assert qualify_res.json()["score"] == 80

    get_res = client.get(f"/api/v1/crm/leads/{lead['id']}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["score"] == 80

    list_res = client.get("/api/v1/crm/leads", params={"status": "qualified"}, headers=headers)
    assert lead["id"] in [l["id"] for l in list_res.json()]


def test_lead_conversion_and_tenant_linking(client, tenant, raw_db):
    _make_super_admin(raw_db, tenant)
    headers = tenant.auth_headers(client)
    lead = _capture_lead(client, email_prefix="convert")

    convert_res = client.post(f"/api/v1/crm/leads/{lead['id']}/convert", headers=headers)
    assert convert_res.status_code == 201, convert_res.text
    customer = convert_res.json()
    assert customer["lead_id"] == lead["id"]
    assert customer["status"] == "trial"
    assert customer["tenant_id"] is None

    double_convert_res = client.post(f"/api/v1/crm/leads/{lead['id']}/convert", headers=headers)
    assert double_convert_res.status_code == 409

    status_after_convert_res = client.patch(f"/api/v1/crm/leads/{lead['id']}", json={"status": "lost"}, headers=headers)
    assert status_after_convert_res.status_code == 409

    new_tenant_res = client.post(
        "/api/v1/tenants",
        json={
            "slug": unique_slug("crmtenant"), "name": "Linked Farm",
            "admin_email": f"linkadmin-{unique_slug('u')}@example.com",
            "admin_password": "pw-for-testing-123", "admin_full_name": "Link Admin",
        },
        headers=headers,
    )
    assert new_tenant_res.status_code == 201, new_tenant_res.text
    new_tenant = new_tenant_res.json()

    link_res = client.post(
        f"/api/v1/crm/customers/{customer['id']}/link-tenant", json={"tenant_id": new_tenant["id"]}, headers=headers
    )
    assert link_res.status_code == 200, link_res.text
    linked = link_res.json()
    assert linked["tenant_id"] == new_tenant["id"]
    assert linked["status"] == "active"

    double_link_res = client.post(
        f"/api/v1/crm/customers/{customer['id']}/link-tenant", json={"tenant_id": new_tenant["id"]}, headers=headers
    )
    assert double_link_res.status_code == 409

    other_lead = _capture_lead(client, email_prefix="convert2")
    other_customer = client.post(f"/api/v1/crm/leads/{other_lead['id']}/convert", headers=headers).json()
    tenant_reuse_res = client.post(
        f"/api/v1/crm/customers/{other_customer['id']}/link-tenant", json={"tenant_id": new_tenant["id"]}, headers=headers
    )
    assert tenant_reuse_res.status_code == 409


def test_opportunity_pipeline(client, tenant, raw_db):
    _make_super_admin(raw_db, tenant)
    headers = tenant.auth_headers(client)
    lead = _capture_lead(client, email_prefix="opp")
    customer = client.post(f"/api/v1/crm/leads/{lead['id']}/convert", headers=headers).json()

    create_res = client.post(
        "/api/v1/crm/opportunities",
        json={"customer_id": customer["id"], "name": "50-rai smart farm package", "stage": "pipeline", "expected_revenue": 500000, "probability_pct": 30},
        headers=headers,
    )
    assert create_res.status_code == 201, create_res.text
    opportunity = create_res.json()
    assert opportunity["stage"] == "pipeline"

    bad_stage_res = client.post(
        "/api/v1/crm/opportunities", json={"name": "bad", "stage": "not-a-stage"}, headers=headers
    )
    assert bad_stage_res.status_code == 422

    update_res = client.patch(
        f"/api/v1/crm/opportunities/{opportunity['id']}", json={"stage": "won", "probability_pct": 100}, headers=headers
    )
    assert update_res.status_code == 200, update_res.text
    assert update_res.json()["stage"] == "won"
    assert update_res.json()["probability_pct"] == 100

    list_res = client.get("/api/v1/crm/opportunities", params={"stage": "won"}, headers=headers)
    assert opportunity["id"] in [o["id"] for o in list_res.json()]


def _create_ticket(client, headers, subject="Cannot see IoT sensor data", priority="high", category="technical"):
    res = client.post(
        "/api/v1/crm/tickets",
        json={"subject": subject, "category": category, "priority": priority, "message": "Please help, sensors show no data."},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_ticket_creation_computes_sla_and_records_first_message(client, tenant):
    headers = tenant.auth_headers(client)
    ticket = _create_ticket(client, headers, priority="urgent")
    assert ticket["status"] == "open"
    assert ticket["sla_due_at"] is not None
    assert ticket["tenant_id"] == tenant.tenant_id

    messages_res = client.get(f"/api/v1/crm/tickets/{ticket['id']}/messages", headers=headers)
    assert messages_res.status_code == 200
    messages = messages_res.json()
    assert len(messages) == 1
    assert messages[0]["author_type"] == "customer"
    assert "sensors show no data" in messages[0]["body"]


def test_ticket_category_and_priority_validation(client, tenant):
    headers = tenant.auth_headers(client)
    bad_category_res = client.post(
        "/api/v1/crm/tickets", json={"subject": "x", "category": "not-a-category", "message": "m"}, headers=headers
    )
    assert bad_category_res.status_code == 422

    bad_priority_res = client.post(
        "/api/v1/crm/tickets", json={"subject": "x", "priority": "not-a-priority", "message": "m"}, headers=headers
    )
    assert bad_priority_res.status_code == 422


def test_ticket_isolated_from_other_tenants(client, tenant, raw_db):
    headers = tenant.auth_headers(client)
    ticket = _create_ticket(client, headers)

    other_tenant = provision_test_tenant(raw_db, "othertenant")
    other_headers = other_tenant.auth_headers(client)

    denied_res = client.get(f"/api/v1/crm/tickets/{ticket['id']}", headers=other_headers)
    assert denied_res.status_code == 403

    list_res = client.get("/api/v1/crm/tickets", headers=other_headers)
    assert ticket["id"] not in [t["id"] for t in list_res.json()]

    own_list_res = client.get("/api/v1/crm/tickets", headers=headers)
    assert ticket["id"] in [t["id"] for t in own_list_res.json()]


def test_platform_admin_sees_and_manages_all_tickets(client, tenant, raw_db):
    _make_super_admin(raw_db, tenant)
    admin_headers = tenant.auth_headers(client)

    other_tenant = provision_test_tenant(raw_db, "ticketother")
    other_headers = other_tenant.auth_headers(client)
    ticket = _create_ticket(client, other_headers)

    admin_get_res = client.get(f"/api/v1/crm/tickets/{ticket['id']}", headers=admin_headers)
    assert admin_get_res.status_code == 200

    resolve_res = client.patch(
        f"/api/v1/crm/tickets/{ticket['id']}", json={"status": "resolved"}, headers=admin_headers
    )
    assert resolve_res.status_code == 200, resolve_res.text
    assert resolve_res.json()["status"] == "resolved"
    assert resolve_res.json()["resolved_at"] is not None

    bad_status_res = client.patch(
        f"/api/v1/crm/tickets/{ticket['id']}", json={"status": "not-a-status"}, headers=admin_headers
    )
    assert bad_status_res.status_code == 422

    # A regular tenant admin (not platform staff) cannot update ticket status.
    regular_denied_res = client.patch(
        f"/api/v1/crm/tickets/{ticket['id']}", json={"status": "closed"}, headers=other_headers
    )
    assert regular_denied_res.status_code == 403


def test_internal_note_hidden_from_customer_but_visible_to_staff(client, tenant, raw_db):
    _make_super_admin(raw_db, tenant)
    admin_headers = tenant.auth_headers(client)

    other_tenant = provision_test_tenant(raw_db, "ticketnote")
    customer_headers = other_tenant.auth_headers(client)
    ticket = _create_ticket(client, customer_headers)

    # Customer cannot force an internal note - forced False.
    customer_reply_res = client.post(
        f"/api/v1/crm/tickets/{ticket['id']}/messages",
        json={"body": "Any update?", "is_internal_note": True},
        headers=customer_headers,
    )
    assert customer_reply_res.status_code == 201
    assert customer_reply_res.json()["is_internal_note"] is False
    assert customer_reply_res.json()["author_type"] == "customer"

    note_res = client.post(
        f"/api/v1/crm/tickets/{ticket['id']}/messages",
        json={"body": "Escalate to engineering internally", "is_internal_note": True},
        headers=admin_headers,
    )
    assert note_res.status_code == 201
    assert note_res.json()["is_internal_note"] is True
    assert note_res.json()["author_type"] == "agent"

    customer_view_res = client.get(f"/api/v1/crm/tickets/{ticket['id']}/messages", headers=customer_headers)
    customer_bodies = [m["body"] for m in customer_view_res.json()]
    assert "Escalate to engineering internally" not in customer_bodies

    staff_view_res = client.get(f"/api/v1/crm/tickets/{ticket['id']}/messages", headers=admin_headers)
    staff_bodies = [m["body"] for m in staff_view_res.json()]
    assert "Escalate to engineering internally" in staff_bodies


def test_customer_reply_reopens_waiting_on_customer_ticket(client, tenant, raw_db):
    _make_super_admin(raw_db, tenant)
    admin_headers = tenant.auth_headers(client)

    other_tenant = provision_test_tenant(raw_db, "ticketreopen")
    customer_headers = other_tenant.auth_headers(client)
    ticket = _create_ticket(client, customer_headers)

    client.patch(f"/api/v1/crm/tickets/{ticket['id']}", json={"status": "waiting_on_customer"}, headers=admin_headers)

    client.post(
        f"/api/v1/crm/tickets/{ticket['id']}/messages", json={"body": "Here is the info you asked for"}, headers=customer_headers
    )

    get_res = client.get(f"/api/v1/crm/tickets/{ticket['id']}", headers=admin_headers)
    assert get_res.json()["status"] == "in_progress"


def _create_campaign(client, headers, code, channel="email"):
    res = client.post(
        "/api/v1/crm/campaigns",
        json={"code": code, "name": "Durian Season Promo", "channel": channel, "budget": 50000},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_campaign_creation_and_validation(client, tenant, raw_db):
    _make_super_admin(raw_db, tenant)
    headers = tenant.auth_headers(client)
    campaign = _create_campaign(client, headers, code=f"promo-{unique_slug('c')}")
    assert campaign["status"] == "draft"
    assert campaign["channel"] == "email"

    bad_channel_res = client.post(
        "/api/v1/crm/campaigns", json={"code": "bad", "name": "x", "channel": "not-a-channel"}, headers=headers
    )
    assert bad_channel_res.status_code == 422

    activate_res = client.patch(f"/api/v1/crm/campaigns/{campaign['id']}", json={"status": "active"}, headers=headers)
    assert activate_res.status_code == 200, activate_res.text
    assert activate_res.json()["status"] == "active"

    bad_status_res = client.patch(f"/api/v1/crm/campaigns/{campaign['id']}", json={"status": "not-a-status"}, headers=headers)
    assert bad_status_res.status_code == 422


def test_lead_capture_attributes_to_campaign(client, tenant, raw_db):
    _make_super_admin(raw_db, tenant)
    headers = tenant.auth_headers(client)
    campaign_code = f"attrib-{unique_slug('c')}"
    campaign = _create_campaign(client, headers, code=campaign_code)

    lead_res = client.post(
        "/api/v1/crm/leads",
        json={"name": "Attributed Farmer", "email": f"attrib-{unique_slug('l')}@example.com", "campaign_code": campaign_code},
    )
    assert lead_res.status_code == 201, lead_res.text
    assert lead_res.json()["campaign_id"] == campaign["id"]

    unknown_campaign_res = client.post(
        "/api/v1/crm/leads",
        json={"name": "Unattributed Farmer", "email": f"noattrib-{unique_slug('l')}@example.com", "campaign_code": "does-not-exist"},
    )
    assert unknown_campaign_res.status_code == 201, unknown_campaign_res.text
    assert unknown_campaign_res.json()["campaign_id"] is None

    leads_res = client.get(f"/api/v1/crm/campaigns/{campaign['id']}/leads", headers=headers)
    assert leads_res.status_code == 200
    assert lead_res.json()["id"] in [l["id"] for l in leads_res.json()]


def _create_coupon(client, headers, code, **overrides):
    payload = {"code": code, "discount_type": "percent", "discount_value": 20}
    payload.update(overrides)
    res = client.post("/api/v1/crm/coupons", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def test_coupon_redemption_lifecycle(client, tenant, raw_db):
    _make_super_admin(raw_db, tenant)
    admin_headers = tenant.auth_headers(client)
    coupon_code = f"SAVE20-{unique_slug('c')}"
    coupon = _create_coupon(client, admin_headers, coupon_code, max_redemptions=1)

    bad_type_res = client.post(
        "/api/v1/crm/coupons", json={"code": "bad", "discount_type": "not-a-type", "discount_value": 5}, headers=admin_headers
    )
    assert bad_type_res.status_code == 422

    redeem_res = client.post(f"/api/v1/crm/coupons/{coupon_code}/redeem", headers=admin_headers)
    assert redeem_res.status_code == 200, redeem_res.text
    assert redeem_res.json()["discount_value"] == 20
    assert redeem_res.json()["coupon"]["redemption_count"] == 1

    over_limit_res = client.post(f"/api/v1/crm/coupons/{coupon_code}/redeem", headers=admin_headers)
    assert over_limit_res.status_code == 409

    unknown_res = client.post("/api/v1/crm/coupons/DOES-NOT-EXIST/redeem", headers=admin_headers)
    assert unknown_res.status_code == 404


def test_expired_coupon_cannot_be_redeemed(client, tenant, raw_db):
    _make_super_admin(raw_db, tenant)
    headers = tenant.auth_headers(client)
    coupon_code = f"EXPIRED-{unique_slug('c')}"
    _create_coupon(client, headers, coupon_code, valid_to="2020-01-01")

    res = client.post(f"/api/v1/crm/coupons/{coupon_code}/redeem", headers=headers)
    assert res.status_code == 409


def _create_message(client, headers, ticket_id, body="Here's a screenshot"):
    res = client.post(f"/api/v1/crm/tickets/{ticket_id}/messages", json={"body": body}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def test_upload_and_download_ticket_attachment(client, tenant):
    """Master-prompt integration, Phase 39 (SEC-005): the first real
    file-upload path in this platform, backed by MinIO."""
    headers = tenant.auth_headers(client)
    ticket = _create_ticket(client, headers)
    message = _create_message(client, headers, ticket["id"])

    upload_res = client.post(
        f"/api/v1/crm/tickets/{ticket['id']}/messages/{message['id']}/attachment",
        files={"file": ("screenshot.png", b"\x89PNG fake png bytes for testing", "image/png")},
        headers=headers,
    )
    assert upload_res.status_code == 200, upload_res.text
    body = upload_res.json()
    assert body["attachment_filename"] == "screenshot.png"
    assert body["attachment_content_type"] == "image/png"
    assert body["attachment_size_bytes"] > 0

    get_res = client.get(f"/api/v1/crm/tickets/{ticket['id']}/messages/{message['id']}/attachment", headers=headers)
    assert get_res.status_code == 200, get_res.text
    attachment = get_res.json()
    assert attachment["filename"] == "screenshot.png"
    assert attachment["download_url"].startswith("http")

    # A second upload to the same message is rejected - one attachment per message.
    second_res = client.post(
        f"/api/v1/crm/tickets/{ticket['id']}/messages/{message['id']}/attachment",
        files={"file": ("again.png", b"more bytes", "image/png")},
        headers=headers,
    )
    assert second_res.status_code == 409


def test_attachment_rejects_disallowed_content_type(client, tenant):
    headers = tenant.auth_headers(client)
    ticket = _create_ticket(client, headers)
    message = _create_message(client, headers, ticket["id"])

    res = client.post(
        f"/api/v1/crm/tickets/{ticket['id']}/messages/{message['id']}/attachment",
        files={"file": ("malware.exe", b"MZ fake executable bytes", "application/x-msdownload")},
        headers=headers,
    )
    assert res.status_code == 422, res.text


def test_attachment_rejects_oversized_file(client, tenant):
    from app.config import settings

    original = settings.max_attachment_size_bytes
    settings.max_attachment_size_bytes = 10
    try:
        headers = tenant.auth_headers(client)
        ticket = _create_ticket(client, headers)
        message = _create_message(client, headers, ticket["id"])

        res = client.post(
            f"/api/v1/crm/tickets/{ticket['id']}/messages/{message['id']}/attachment",
            files={"file": ("big.png", b"x" * 100, "image/png")},
            headers=headers,
        )
        assert res.status_code == 422, res.text
    finally:
        settings.max_attachment_size_bytes = original


def test_attachment_on_internal_note_hidden_from_customer(client, tenant, raw_db):
    _make_super_admin(raw_db, tenant)
    admin_headers = tenant.auth_headers(client)
    other_tenant = provision_test_tenant(raw_db, "attachnote")
    other_headers = other_tenant.auth_headers(client)

    ticket = _create_ticket(client, other_headers)
    note_res = client.post(
        f"/api/v1/crm/tickets/{ticket['id']}/messages", json={"body": "internal only", "is_internal_note": True}, headers=admin_headers
    )
    assert note_res.status_code == 201, note_res.text
    note = note_res.json()

    upload_res = client.post(
        f"/api/v1/crm/tickets/{ticket['id']}/messages/{note['id']}/attachment",
        files={"file": ("internal.pdf", b"%PDF fake bytes", "application/pdf")},
        headers=admin_headers,
    )
    assert upload_res.status_code == 200, upload_res.text

    customer_get_res = client.get(
        f"/api/v1/crm/tickets/{ticket['id']}/messages/{note['id']}/attachment", headers=other_headers
    )
    assert customer_get_res.status_code == 404

    staff_get_res = client.get(
        f"/api/v1/crm/tickets/{ticket['id']}/messages/{note['id']}/attachment", headers=admin_headers
    )
    assert staff_get_res.status_code == 200


def test_agent_reply_emails_the_customer_but_internal_note_does_not(client, tenant, raw_db, monkeypatch):
    """Master-prompt integration, Phase 42: the first real email-
    notification consumer. No live SendGrid key exists in this test
    environment, so `core.email.send_email` is monkeypatched to capture
    the call rather than actually reaching SendGrid - this proves the
    router calls it with the right recipient/content, not that a real
    inbox receives anything."""
    from app.routers.v1 import crm as crm_router

    calls = []
    monkeypatch.setattr(crm_router.email, "send_email", lambda **kw: calls.append(kw) or True)

    _make_super_admin(raw_db, tenant)
    admin_headers = tenant.auth_headers(client)
    other_tenant = provision_test_tenant(raw_db, "emailcust")
    other_headers = other_tenant.auth_headers(client)
    ticket = _create_ticket(client, other_headers)

    note_res = client.post(
        f"/api/v1/crm/tickets/{ticket['id']}/messages", json={"body": "internal only", "is_internal_note": True}, headers=admin_headers
    )
    assert note_res.status_code == 201, note_res.text
    assert calls == []

    reply_res = client.post(
        f"/api/v1/crm/tickets/{ticket['id']}/messages", json={"body": "We're looking into it"}, headers=admin_headers
    )
    assert reply_res.status_code == 201, reply_res.text
    assert len(calls) == 1
    assert calls[0]["to"] == ticket["requester_email"]
    assert "We're looking into it" in calls[0]["body"]

    customer_reply_res = client.post(
        f"/api/v1/crm/tickets/{ticket['id']}/messages", json={"body": "thanks"}, headers=other_headers
    )
    assert customer_reply_res.status_code == 201, customer_reply_res.text
    assert len(calls) == 1
