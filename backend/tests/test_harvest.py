from app.harvest.estimation import estimate_yield_range

from .conftest import unique_slug
from .test_farm import _build_hierarchy, _create_crop


def test_estimate_yield_range_returns_low_high_confidence():
    estimate = estimate_yield_range(tree_count=10, avg_fruit_count_per_tree=20, avg_fruit_weight_kg=3.0)
    assert estimate.estimated_yield_kg_low < estimate.estimated_yield_kg_high
    point = 10 * 20 * 3.0
    assert estimate.estimated_yield_kg_low == round(point * 0.8, 1)
    assert estimate.estimated_yield_kg_high == round(point * 1.2, 1)
    assert 0 < estimate.confidence <= 0.85


def test_estimate_yield_range_handles_missing_inputs():
    estimate = estimate_yield_range(tree_count=0, avg_fruit_count_per_tree=20, avg_fruit_weight_kg=3.0)
    assert estimate.estimated_yield_kg_low == 0.0
    assert estimate.estimated_yield_kg_high == 0.0
    assert estimate.confidence == 0.0


def _create_farm(client, headers, code="HFARM"):
    res = client.post("/api/v1/farm/farms", json={"code": code, "name": "Harvest Farm"}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def test_fruit_observation_lifecycle(client, tenant):
    headers = tenant.auth_headers(client)
    crop = _create_crop(client, headers, code=f"durian-harv-{tenant.tenant_slug}")
    farm, _zone, _plot, _block, row = _build_hierarchy(client, headers, farm_code="HFARM1")
    tree = client.post(f"/api/v1/farm/rows/{row['id']}/trees", json={"crop_id": crop["id"]}, headers=headers).json()

    obs_res = client.post(
        f"/api/v1/harvest/farms/{farm['id']}/observations",
        json={"tree_id": tree["id"], "stage": "flowering", "estimated_count": 150},
        headers=headers,
    )
    assert obs_res.status_code == 201, obs_res.text

    list_res = client.get(f"/api/v1/harvest/trees/{tree['id']}/observations", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1
    assert list_res.json()[0]["stage"] == "flowering"


def test_yield_forecast_is_always_a_range(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="HFARM2")

    forecast_res = client.post(
        f"/api/v1/harvest/farms/{farm['id']}/yield-forecasts",
        json={"tree_count": 5, "avg_fruit_count_per_tree": 15, "avg_fruit_weight_kg": 2.5},
        headers=headers,
    )
    assert forecast_res.status_code == 201, forecast_res.text
    forecast = forecast_res.json()
    assert forecast["estimated_yield_kg_low"] < forecast["estimated_yield_kg_high"]

    list_res = client.get(f"/api/v1/harvest/farms/{farm['id']}/yield-forecasts", headers=headers)
    assert len(list_res.json()) == 1


def test_harvest_and_packing_lot_traceability(client, tenant):
    headers = tenant.auth_headers(client)
    farm, _zone, plot, _block, row = _build_hierarchy(client, headers, farm_code="HFARM3")
    crop = _create_crop(client, headers, code=f"durian-trace-{tenant.tenant_slug}")
    tree = client.post(f"/api/v1/farm/rows/{row['id']}/trees", json={"crop_id": crop["id"]}, headers=headers).json()

    lot1 = client.post(
        f"/api/v1/harvest/farms/{farm['id']}/harvest-lots",
        json={"plot_id": plot["id"], "tree_id": tree["id"], "quantity_kg": 12.5, "grade": "A"},
        headers=headers,
    ).json()
    lot2 = client.post(
        f"/api/v1/harvest/farms/{farm['id']}/harvest-lots",
        json={"plot_id": plot["id"], "quantity_kg": 8.0, "grade": "B"},
        headers=headers,
    ).json()

    packing_res = client.post(
        f"/api/v1/harvest/farms/{farm['id']}/packing-lots",
        json={"harvest_lot_ids": [lot1["id"], lot2["id"]]},
        headers=headers,
    )
    assert packing_res.status_code == 201, packing_res.text
    packing_lot = packing_res.json()

    # Public traceability endpoint - no auth headers at all.
    trace_res = client.get(f"/api/v1/harvest/trace/{tenant.tenant_slug}/{packing_lot['qr_code']}")
    assert trace_res.status_code == 200, trace_res.text
    trace = trace_res.json()
    assert trace["farm_name"] == "Farm One"
    assert len(trace["harvest_lots"]) == 2
    assert {hl["grade"] for hl in trace["harvest_lots"]} == {"A", "B"}
    assert any(hl["tree_code"] == tree["code"] for hl in trace["harvest_lots"])


def test_trace_direct_harvest_lot_qr(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="HFARM4")
    lot = client.post(
        f"/api/v1/harvest/farms/{farm['id']}/harvest-lots", json={"quantity_kg": 5.0}, headers=headers
    ).json()

    trace_res = client.get(f"/api/v1/harvest/trace/{tenant.tenant_slug}/{lot['qr_code']}")
    assert trace_res.status_code == 200, trace_res.text
    assert trace_res.json()["harvest_lots"][0]["quantity_kg"] == 5.0


def test_trace_unknown_qr_returns_404(client, tenant):
    res = client.get(f"/api/v1/harvest/trace/{tenant.tenant_slug}/does-not-exist")
    assert res.status_code == 404

    res_bad_tenant = client.get("/api/v1/harvest/trace/no-such-tenant/does-not-exist")
    assert res_bad_tenant.status_code == 404


def test_yield_summary_aggregates_by_plot(client, tenant):
    headers = tenant.auth_headers(client)
    farm, _zone, plot, _block, _row = _build_hierarchy(client, headers, farm_code="HFARM5")

    client.post(f"/api/v1/harvest/farms/{farm['id']}/harvest-lots", json={"plot_id": plot["id"], "quantity_kg": 10}, headers=headers)
    client.post(f"/api/v1/harvest/farms/{farm['id']}/harvest-lots", json={"plot_id": plot["id"], "quantity_kg": 15}, headers=headers)

    summary_res = client.get(f"/api/v1/harvest/farms/{farm['id']}/yield-summary", headers=headers)
    assert summary_res.status_code == 200
    summary = summary_res.json()
    assert len(summary) == 1
    assert summary[0]["total_kg"] == 25
    assert summary[0]["lot_count"] == 2


def test_harvest_lot_farm_scoped_abac(client, tenant):
    admin_headers = tenant.auth_headers(client)
    farm_a = client.post("/api/v1/farm/farms", json={"code": "HA", "name": "Harv Farm A"}, headers=admin_headers).json()
    farm_b = client.post("/api/v1/farm/farms", json={"code": "HB", "name": "Harv Farm B"}, headers=admin_headers).json()

    client.post(f"/api/v1/harvest/farms/{farm_a['id']}/harvest-lots", json={"quantity_kg": 1}, headers=admin_headers)
    client.post(f"/api/v1/harvest/farms/{farm_b['id']}/harvest-lots", json={"quantity_kg": 1}, headers=admin_headers)

    email = f"harvmgr-{unique_slug('u')}@example.com"
    password = "pw-for-testing-123"
    user = client.post(
        "/api/v1/users", json={"email": email, "password": password, "full_name": "Harvest Manager"}, headers=admin_headers
    ).json()
    roles = {r["code"]: r["id"] for r in client.get("/api/v1/roles", headers=admin_headers).json()}
    client.post(
        "/api/v1/role-assignments",
        json={"user_id": user["id"], "role_id": roles["farm_manager"], "scope_type": "farm", "scope_id": farm_a["id"]},
        headers=admin_headers,
    )

    login_res = client.post(
        "/api/v1/auth/login", json={"tenant_slug": tenant.tenant_slug, "email": email, "password": password}
    )
    manager_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    ok_res = client.get(f"/api/v1/harvest/farms/{farm_a['id']}/harvest-lots", headers=manager_headers)
    assert ok_res.status_code == 200

    denied_res = client.get(f"/api/v1/harvest/farms/{farm_b['id']}/harvest-lots", headers=manager_headers)
    assert denied_res.status_code == 403
