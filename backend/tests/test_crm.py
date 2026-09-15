from app.core.deps import set_tenant_context
from app.foundation import models as fm

from .conftest import unique_slug


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
