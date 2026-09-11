from .conftest import unique_slug


def _create_farm(client, headers, code="DASHFARM"):
    res = client.post("/api/v1/farm/farms", json={"code": code, "name": "Dashboard Farm"}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _create_asset_twin_type(client, headers, code="dash-pump-type"):
    res = client.post("/api/v1/twins/types", json={"code": code, "name": "Pump", "category": "asset"}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _register_asset(client, headers, twin_type_id, display_code="DASH-PUMP-1", **extra):
    payload = {"twin_type_id": twin_type_id, "display_code": display_code, **extra}
    res = client.post("/api/v1/assets", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def test_fleet_summary_equipment_health_tiles(client, tenant):
    headers = tenant.auth_headers(client)
    twin_type = _create_asset_twin_type(client, headers, code=f"pump-{tenant.tenant_slug}")

    assessed = _register_asset(
        client, headers, twin_type["id"], display_code="ASSESSED-1",
        initial_state={"temperature_c": 20, "vibration_mm_s": 0.1, "status": "running"},
    )
    unassessed = _register_asset(client, headers, twin_type["id"], display_code="UNASSESSED-1")

    assess_res = client.post(f"/api/v1/assets/{assessed['id']}/assessments", headers=headers)
    assert assess_res.status_code == 201, assess_res.text

    summary_res = client.get("/api/v1/dashboard/fleet-summary", headers=headers)
    assert summary_res.status_code == 200, summary_res.text
    summary = summary_res.json()

    twin_ids = {item["twin_id"] for item in summary["equipment_health"]["equipment"]}
    assert assessed["id"] in twin_ids
    assert unassessed["id"] in twin_ids
    unassessed_item = next(i for i in summary["equipment_health"]["equipment"] if i["twin_id"] == unassessed["id"])
    assert unassessed_item["band"] is None
    assert summary["equipment_health"]["by_band"]["unassessed"] >= 1


def test_fleet_summary_low_stock_and_ai_recommendations(client, tenant):
    headers = tenant.auth_headers(client)
    item = client.post(
        "/api/v1/inventory/items",
        json={"code": f"dash-npk-{tenant.tenant_slug}", "name": "NPK", "category": "fertilizer", "uom": "kg", "min_qty": 50},
        headers=headers,
    ).json()
    warehouse = client.post(
        "/api/v1/inventory/warehouses", json={"code": f"dash-wh-{tenant.tenant_slug}", "name": "Store"}, headers=headers
    ).json()
    client.post(
        f"/api/v1/inventory/warehouses/{warehouse['id']}/receive",
        json={"item_id": item["id"], "lot_code": "LOT-LOW", "quantity": 10},
        headers=headers,
    )

    action_res = client.post(
        "/api/v1/ai/agent-actions",
        json={
            "agent_code": "dashboard_test_agent", "action_type": "notify_operator", "requested_level": "L1",
            "entity_type": "farm", "entity_id": "00000000-0000-0000-0000-000000000000",
            "rationale": "Worth a look.", "input_context": {},
        },
        headers=headers,
    ).json()

    summary_res = client.get("/api/v1/dashboard/fleet-summary", headers=headers)
    assert summary_res.status_code == 200, summary_res.text
    summary = summary_res.json()

    assert summary["inventory"]["low_stock_count"] == 1
    assert summary["inventory"]["items"][0]["code"] == item["code"]
    assert action_res["id"] in [a["agent_action_id"] for a in summary["ai_recommendations"]]


def test_farm_summary_aggregates_real_data(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="DASHFARM1")

    client.post(
        "/api/v1/weather/readings",
        json={"farm_id": farm["id"], "metric": "temperature_c", "value": 31.5, "source": "station", "observed_at": "2026-01-01T06:00:00Z"},
        headers=headers,
    )

    disease = client.post(
        "/api/v1/crop-health/diseases",
        json={"code": f"blight-{tenant.tenant_slug}", "name_en": "Blight", "name_th": "โรคใบไหม้", "pathogen_type": "fungal"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/crop-health/farms/{farm['id']}/incidents", json={"disease_id": disease["id"]}, headers=headers
    )

    plan = client.post(
        f"/api/v1/irrigation/farms/{farm['id']}/plans", json={"reason": "dry topsoil"}, headers=headers
    ).json()
    client.post(f"/api/v1/irrigation/plans/{plan['id']}/submit", headers=headers)

    client.post(
        f"/api/v1/harvest/farms/{farm['id']}/yield-forecasts",
        json={"tree_count": 5, "avg_fruit_count_per_tree": 15, "avg_fruit_weight_kg": 2.5},
        headers=headers,
    )
    client.post(f"/api/v1/harvest/farms/{farm['id']}/harvest-lots", json={"quantity_kg": 12.0}, headers=headers)

    client.post(
        "/api/v1/accounting/ledger-entries",
        json={"entry_type": "actual", "direction": "revenue", "amount": 1000.0, "dimensions": {"farm_id": farm["id"]}},
        headers=headers,
    )
    client.post(
        "/api/v1/accounting/ledger-entries",
        json={"entry_type": "actual", "direction": "expense", "amount": 300.0, "dimensions": {"farm_id": farm["id"]}},
        headers=headers,
    )

    client.post(
        "/api/v1/ai/agent-actions",
        json={
            "agent_code": "dashboard_test_agent", "action_type": "notify_operator", "requested_level": "L1",
            "entity_type": "farm", "entity_id": farm["id"], "farm_id": farm["id"],
            "rationale": "Farm-scoped recommendation.", "input_context": {},
        },
        headers=headers,
    )

    summary_res = client.get(f"/api/v1/dashboard/farms/{farm['id']}/summary", headers=headers)
    assert summary_res.status_code == 200, summary_res.text
    summary = summary_res.json()

    assert summary["farm_id"] == farm["id"]
    assert summary["weather"]["temperature_c"] == 31.5
    assert summary["weather"]["soil_moisture_pct"] is None
    assert summary["disease_risk"]["open_incident_count"] == 1
    assert summary["irrigation_status"]["pending_approval_count"] == 1
    assert summary["yield_forecast"]["estimated_yield_kg_low"] > 0
    assert summary["harvest_status"]["lots_last_30_days"] == 1
    assert summary["harvest_status"]["total_kg_last_30_days"] == 12.0
    assert summary["financial_kpis"]["revenue"] == 1000.0
    assert summary["financial_kpis"]["profit"] == 700.0
    assert len(summary["ai_recommendations"]) == 1


def test_farm_summary_work_orders_widget(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="DASHFARM2")
    twin_type = _create_asset_twin_type(client, headers, code=f"wo-pump-{tenant.tenant_slug}")
    asset = _register_asset(client, headers, twin_type["id"], display_code="WO-PUMP-1", farm_id=farm["id"])

    request_res = client.post(
        f"/api/v1/assets/{asset['id']}/maintenance-requests",
        json={"strategy": "corrective", "description": "Leaking seal"},
        headers=headers,
    ).json()
    client.post(f"/api/v1/maintenance-requests/{request_res['id']}/submit", headers=headers)
    client.post(f"/api/v1/maintenance-requests/{request_res['id']}/approve", json={}, headers=headers)
    client.post(f"/api/v1/maintenance-requests/{request_res['id']}/convert", headers=headers)

    summary_res = client.get(f"/api/v1/dashboard/farms/{farm['id']}/summary", headers=headers)
    assert summary_res.status_code == 200, summary_res.text
    assert summary_res.json()["work_orders"]["open_count"] == 1


def test_farm_summary_with_no_data_returns_honest_empty_shape(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="DASHFARM3")

    summary_res = client.get(f"/api/v1/dashboard/farms/{farm['id']}/summary", headers=headers)
    assert summary_res.status_code == 200, summary_res.text
    summary = summary_res.json()

    assert summary["weather"] == {"temperature_c": None, "humidity_pct": None, "rainfall_mm": None, "soil_moisture_pct": None}
    assert summary["disease_risk"]["open_incident_count"] == 0
    assert summary["yield_forecast"] is None
    assert summary["financial_kpis"]["revenue"] == 0.0
    assert summary["ai_recommendations"] == []


def test_dashboard_farm_scoped_abac(client, tenant):
    admin_headers = tenant.auth_headers(client)
    farm_a = client.post("/api/v1/farm/farms", json={"code": "DASHA", "name": "Dash Farm A"}, headers=admin_headers).json()
    farm_b = client.post("/api/v1/farm/farms", json={"code": "DASHB", "name": "Dash Farm B"}, headers=admin_headers).json()

    email = f"dashmgr-{unique_slug('u')}@example.com"
    password = "pw-for-testing-123"
    user = client.post(
        "/api/v1/users", json={"email": email, "password": password, "full_name": "Dash Manager"}, headers=admin_headers
    ).json()
    roles = {r["code"]: r["id"] for r in client.get("/api/v1/roles", headers=admin_headers).json()}
    client.post(
        "/api/v1/role-assignments",
        json={"user_id": user["id"], "role_id": roles["farm_manager"], "scope_type": "farm", "scope_id": farm_a["id"]},
        headers=admin_headers,
    )

    login_res = client.post("/api/v1/auth/login", json={"tenant_slug": tenant.tenant_slug, "email": email, "password": password})
    manager_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    ok_res = client.get(f"/api/v1/dashboard/farms/{farm_a['id']}/summary", headers=manager_headers)
    assert ok_res.status_code == 200

    denied_res = client.get(f"/api/v1/dashboard/farms/{farm_b['id']}/summary", headers=manager_headers)
    assert denied_res.status_code == 403
