from app.core.deps import set_tenant_context
from app.foundation import models as fm

from .conftest import provision_test_tenant


def _make_super_admin(raw_db, tenant):
    set_tenant_context(raw_db, tenant.tenant_id)
    user = raw_db.get(fm.User, tenant.admin_user_id)
    user.is_platform_super_admin = True
    raw_db.commit()


def test_public_plans_listing_requires_no_auth(client):
    res = client.get("/api/v1/subscriptions/plans")
    assert res.status_code == 200, res.text
    codes = {p["code"] for p in res.json()}
    assert codes == {"free", "farm", "pro", "enterprise"}
    free_plan = next(p for p in res.json() if p["code"] == "free")
    assert free_plan["farm_limit"] == 1
    enterprise_plan = next(p for p in res.json() if p["code"] == "enterprise")
    assert enterprise_plan["farm_limit"] is None


def test_new_tenant_gets_a_default_trialing_free_subscription(client, tenant):
    headers = tenant.auth_headers(client)
    res = client.get("/api/v1/subscriptions/me", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["subscription"]["status"] == "trialing"
    assert body["subscription"]["trial_ends_at"] is not None
    assert body["plan"]["code"] == "free"


def test_usage_reflects_real_farm_and_user_counts(client, tenant):
    headers = tenant.auth_headers(client)
    client.post("/api/v1/farm/farms", json={"code": "SUBF1", "name": "Sub Farm 1"}, headers=headers)

    res = client.get("/api/v1/subscriptions/me", headers=headers)
    assert res.status_code == 200, res.text
    usage_by_resource = {u["resource"]: u for u in res.json()["usage"]}
    assert usage_by_resource["farms"]["used"] == 1
    assert usage_by_resource["farms"]["limit"] == 1
    assert usage_by_resource["farms"]["over_limit"] is False
    # admin user itself counts.
    assert usage_by_resource["users"]["used"] >= 1


def test_non_super_admin_cannot_view_other_tenant_subscription(client, tenant):
    headers = tenant.auth_headers(client)
    other_tenant_id = "00000000-0000-0000-0000-000000000000"
    res = client.get(f"/api/v1/subscriptions/{other_tenant_id}", headers=headers)
    assert res.status_code == 403


def test_platform_admin_can_view_and_change_another_tenants_plan(client, tenant, raw_db):
    _make_super_admin(raw_db, tenant)
    admin_headers = tenant.auth_headers(client)

    other_tenant = provision_test_tenant(raw_db, "subother")

    view_res = client.get(f"/api/v1/subscriptions/{other_tenant.tenant_id}", headers=admin_headers)
    assert view_res.status_code == 200, view_res.text
    assert view_res.json()["plan"]["code"] == "free"

    change_res = client.post(
        f"/api/v1/subscriptions/{other_tenant.tenant_id}/change-plan", json={"plan_code": "pro"}, headers=admin_headers
    )
    assert change_res.status_code == 200, change_res.text
    assert change_res.json()["status"] == "active"

    view_after_res = client.get(f"/api/v1/subscriptions/{other_tenant.tenant_id}", headers=admin_headers)
    assert view_after_res.json()["plan"]["code"] == "pro"

    bad_plan_res = client.post(
        f"/api/v1/subscriptions/{other_tenant.tenant_id}/change-plan", json={"plan_code": "not-a-plan"}, headers=admin_headers
    )
    assert bad_plan_res.status_code == 422


def test_platform_admin_can_cancel_subscription(client, tenant, raw_db):
    _make_super_admin(raw_db, tenant)
    admin_headers = tenant.auth_headers(client)
    other_tenant = provision_test_tenant(raw_db, "subcancel")

    cancel_res = client.post(
        f"/api/v1/subscriptions/{other_tenant.tenant_id}/cancel", json={"reason": "test cleanup"}, headers=admin_headers
    )
    assert cancel_res.status_code == 200, cancel_res.text
    assert cancel_res.json()["status"] == "cancelled"
    assert cancel_res.json()["cancelled_at"] is not None

    double_cancel_res = client.post(
        f"/api/v1/subscriptions/{other_tenant.tenant_id}/cancel", json={}, headers=admin_headers
    )
    assert double_cancel_res.status_code == 409

    change_after_cancel_res = client.post(
        f"/api/v1/subscriptions/{other_tenant.tenant_id}/change-plan", json={"plan_code": "pro"}, headers=admin_headers
    )
    assert change_after_cancel_res.status_code == 409
