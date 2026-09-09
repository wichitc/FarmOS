from datetime import datetime, timedelta, timezone

from app.irrigation.recommendation import recommend_fertigation, recommend_irrigation

from .conftest import unique_slug
from .test_farm import _build_hierarchy


def test_recommend_irrigation_skips_when_rain_forecast():
    rec = recommend_irrigation(
        soil_moisture_pct=20, target_moisture_pct=35, forecast_rain_mm=15, area_hectares=1.0
    )
    assert rec.should_irrigate is False
    assert "rainfall" in rec.reason.lower()


def test_recommend_irrigation_skips_when_moisture_sufficient():
    rec = recommend_irrigation(
        soil_moisture_pct=40, target_moisture_pct=35, forecast_rain_mm=0, area_hectares=1.0
    )
    assert rec.should_irrigate is False
    assert rec.recommended_volume_liters is None


def test_recommend_irrigation_recommends_when_dry():
    rec = recommend_irrigation(
        soil_moisture_pct=20, target_moisture_pct=35, forecast_rain_mm=0, area_hectares=2.0
    )
    assert rec.should_irrigate is True
    assert rec.recommended_volume_liters == 15 * 2.0 * 150.0
    assert rec.recommended_duration_minutes > 0


def test_recommend_fertigation_computes_quantity_from_n_target():
    rec = recommend_fertigation(target_n_kg=3.0, fertilizer_composition={"N": 15, "P": 15, "K": 15})
    assert rec.recommended_quantity_kg == 20.0
    assert rec.breakdown_kg["N"] == 3.0
    assert rec.breakdown_kg["P"] == 3.0


def test_recommend_fertigation_handles_zero_nitrogen():
    rec = recommend_fertigation(target_n_kg=3.0, fertilizer_composition={"N": 0, "K": 40})
    assert rec.recommended_quantity_kg == 0.0


def _create_farm_with_plot(client, headers, farm_code="IRRFARM"):
    farm, _zone, plot, _block, _row = _build_hierarchy(client, headers, farm_code=farm_code)
    return farm, plot


def test_irrigation_plan_full_lifecycle(client, tenant):
    headers = tenant.auth_headers(client)
    farm, plot = _create_farm_with_plot(client, headers, farm_code="IRRFARM1")

    create_res = client.post(
        f"/api/v1/irrigation/farms/{farm['id']}/plans",
        json={"plot_id": plot["id"], "source": "manual", "recommended_volume_liters": 500, "reason": "dry topsoil"},
        headers=headers,
    )
    assert create_res.status_code == 201, create_res.text
    plan = create_res.json()
    assert plan["status"] == "draft"

    submit_res = client.post(f"/api/v1/irrigation/plans/{plan['id']}/submit", headers=headers)
    assert submit_res.status_code == 200, submit_res.text
    submitted = submit_res.json()
    assert submitted["status"] == "pending_approval"
    assert submitted["workflow_instance_id"]

    approve_res = client.post(f"/api/v1/irrigation/plans/{plan['id']}/approve", json={}, headers=headers)
    assert approve_res.status_code == 200, approve_res.text
    assert approve_res.json()["status"] == "approved"

    execute_res = client.post(
        f"/api/v1/irrigation/plans/{plan['id']}/execute",
        json={"actual_volume_liters": 480, "actual_duration_minutes": 12, "safety_checks": {"max_runtime_ok": True}},
        headers=headers,
    )
    assert execute_res.status_code == 201, execute_res.text
    event = execute_res.json()
    assert event["plan_id"] == plan["id"]
    assert event["actual_volume_liters"] == 480

    final_res = client.get(f"/api/v1/irrigation/plans/{plan['id']}", headers=headers)
    assert final_res.json()["status"] == "completed"


def test_irrigation_plan_reject_path_blocks_execution(client, tenant):
    headers = tenant.auth_headers(client)
    farm, plot = _create_farm_with_plot(client, headers, farm_code="IRRFARM2")

    plan = client.post(
        f"/api/v1/irrigation/farms/{farm['id']}/plans", json={"plot_id": plot["id"]}, headers=headers
    ).json()
    client.post(f"/api/v1/irrigation/plans/{plan['id']}/submit", headers=headers)

    reject_res = client.post(
        f"/api/v1/irrigation/plans/{plan['id']}/reject", json={"reason": "insufficient water rights"}, headers=headers
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["status"] == "rejected"

    execute_res = client.post(f"/api/v1/irrigation/plans/{plan['id']}/execute", json={}, headers=headers)
    assert execute_res.status_code == 409


def test_execute_blocked_unless_approved(client, tenant):
    headers = tenant.auth_headers(client)
    farm, plot = _create_farm_with_plot(client, headers, farm_code="IRRFARM3")

    plan = client.post(
        f"/api/v1/irrigation/farms/{farm['id']}/plans", json={"plot_id": plot["id"]}, headers=headers
    ).json()

    execute_res = client.post(f"/api/v1/irrigation/plans/{plan['id']}/execute", json={}, headers=headers)
    assert execute_res.status_code == 409


def test_seeded_approval_workflows_exist_for_new_tenant(client, tenant):
    headers = tenant.auth_headers(client)
    definitions = client.get("/api/v1/workflows/definitions", headers=headers).json()
    entity_types = {d["entity_type"] for d in definitions}
    assert "irrigation_plan" in entity_types
    assert "fertigation_plan" in entity_types


def test_fertigation_plan_tree_level_granularity(client, tenant):
    headers = tenant.auth_headers(client)
    farm, zone, plot, block, row = _build_hierarchy(client, headers, farm_code="FERTFARM1")
    crop = client.post(
        "/api/v1/master-data/crops",
        json={"code": f"durian-fert-{tenant.tenant_slug}", "name_en": "Durian", "name_th": "ทุเรียน"},
        headers=headers,
    ).json()
    tree = client.post(
        f"/api/v1/farm/rows/{row['id']}/trees", json={"crop_id": crop["id"]}, headers=headers
    ).json()

    fertilizer = client.post(
        "/api/v1/irrigation/fertilizers",
        json={"code": "npk-15-15-15", "name": "NPK 15-15-15", "composition": {"N": 15, "P": 15, "K": 15}},
        headers=headers,
    )
    assert fertilizer.status_code == 201, fertilizer.text
    fertilizer_id = fertilizer.json()["id"]

    plan = client.post(
        f"/api/v1/irrigation/farms/{farm['id']}/fertigation-plans",
        json={"plot_id": plot["id"], "fertilizer_id": fertilizer_id, "target_n_kg": 3.0, "recommended_quantity_kg": 20.0},
        headers=headers,
    )
    assert plan.status_code == 201, plan.text
    plan_id = plan.json()["id"]

    client.post(f"/api/v1/irrigation/fertigation-plans/{plan_id}/submit", headers=headers)
    approve_res = client.post(f"/api/v1/irrigation/fertigation-plans/{plan_id}/approve", json={}, headers=headers)
    assert approve_res.status_code == 200, approve_res.text

    execute_res = client.post(
        f"/api/v1/irrigation/fertigation-plans/{plan_id}/execute",
        json={"tree_id": tree["id"], "actual_quantity_kg": 19.5, "actual_breakdown": {"N": 2.9, "P": 2.9, "K": 2.9}},
        headers=headers,
    )
    assert execute_res.status_code == 201, execute_res.text
    event = execute_res.json()
    assert event["tree_id"] == tree["id"]


def test_weather_station_preferred_over_forecast(client, tenant):
    headers = tenant.auth_headers(client)
    farm = client.post("/api/v1/farm/farms", json={"code": "WXFARM1", "name": "Weather Farm"}, headers=headers).json()

    now = datetime.now(timezone.utc)
    client.post(
        "/api/v1/weather/readings",
        json={"farm_id": farm["id"], "metric": "rainfall_mm", "value": 5.0, "source": "forecast", "observed_at": (now + timedelta(hours=6)).isoformat()},
        headers=headers,
    )
    client.post(
        "/api/v1/weather/readings",
        json={"farm_id": farm["id"], "metric": "rainfall_mm", "value": 2.0, "source": "station", "observed_at": now.isoformat()},
        headers=headers,
    )

    current_res = client.get(
        "/api/v1/weather/current", params={"farm_id": farm["id"], "metric": "rainfall_mm"}, headers=headers
    )
    assert current_res.status_code == 200, current_res.text
    current = current_res.json()
    assert current["source"] == "station"
    assert current["value"] == 2.0

    list_res = client.get("/api/v1/weather/readings", params={"farm_id": farm["id"]}, headers=headers)
    assert len(list_res.json()) == 2


def test_irrigation_plan_farm_scoped_abac(client, tenant):
    admin_headers = tenant.auth_headers(client)
    farm_a = client.post("/api/v1/farm/farms", json={"code": "IRRA", "name": "Irr Farm A"}, headers=admin_headers).json()
    farm_b = client.post("/api/v1/farm/farms", json={"code": "IRRB", "name": "Irr Farm B"}, headers=admin_headers).json()

    plan_a = client.post(f"/api/v1/irrigation/farms/{farm_a['id']}/plans", json={}, headers=admin_headers).json()
    plan_b = client.post(f"/api/v1/irrigation/farms/{farm_b['id']}/plans", json={}, headers=admin_headers).json()

    email = f"irrmgr-{unique_slug('u')}@example.com"
    password = "pw-for-testing-123"
    user = client.post(
        "/api/v1/users", json={"email": email, "password": password, "full_name": "Irrigation Manager"}, headers=admin_headers
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

    ok_res = client.get(f"/api/v1/irrigation/plans/{plan_a['id']}", headers=manager_headers)
    assert ok_res.status_code == 200

    denied_res = client.get(f"/api/v1/irrigation/plans/{plan_b['id']}", headers=manager_headers)
    assert denied_res.status_code == 403
