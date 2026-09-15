from .conftest import unique_slug
from .test_farm import _build_hierarchy


def _create_farm(client, headers, code="RPTFARM"):
    res = client.post("/api/v1/farm/farms", json={"code": code, "name": "Reporting Farm"}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def test_farm_health_report_reflects_real_data(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="RPTFARM1")

    disease = client.post(
        "/api/v1/crop-health/diseases",
        json={"code": f"blight-{tenant.tenant_slug}", "name_en": "Blight", "name_th": "โรคใบไหม้", "pathogen_type": "fungal"},
        headers=headers,
    ).json()
    client.post(f"/api/v1/crop-health/farms/{farm['id']}/incidents", json={"disease_id": disease["id"]}, headers=headers)

    twin_type = client.post(
        "/api/v1/twins/types", json={"code": f"rpt-pump-{tenant.tenant_slug}", "name": "Pump", "category": "asset"}, headers=headers
    ).json()
    asset = client.post(
        "/api/v1/assets",
        json={"twin_type_id": twin_type["id"], "display_code": "RPT-PUMP-1", "farm_id": farm["id"], "initial_state": {"temperature_c": 20, "vibration_mm_s": 0.1, "status": "running"}},
        headers=headers,
    ).json()
    client.post(f"/api/v1/assets/{asset['id']}/assessments", headers=headers)

    res = client.get(f"/api/v1/reports/farms/{farm['id']}/health", headers=headers)
    assert res.status_code == 200, res.text
    row = res.json()
    assert row["farm_id"] == farm["id"]
    assert row["open_disease_incidents"] == 1
    assert row["equipment_count"] == 1


def test_irrigation_fertigation_usage_report(client, tenant):
    headers = tenant.auth_headers(client)
    farm, _zone, plot, _block, _row = _build_hierarchy(client, headers, farm_code="RPTFARM2")

    plan = client.post(
        f"/api/v1/irrigation/farms/{farm['id']}/plans", json={"plot_id": plot["id"], "reason": "dry topsoil"}, headers=headers
    ).json()
    client.post(f"/api/v1/irrigation/plans/{plan['id']}/submit", headers=headers)
    client.post(f"/api/v1/irrigation/plans/{plan['id']}/approve", json={}, headers=headers)
    client.post(f"/api/v1/irrigation/plans/{plan['id']}/execute", json={"actual_volume_liters": 500.0}, headers=headers)

    res = client.get(f"/api/v1/reports/farms/{farm['id']}/irrigation-fertigation-usage", headers=headers)
    assert res.status_code == 200, res.text
    rows = res.json()
    assert len(rows) == 1
    assert rows[0]["plot_id"] == plot["id"]
    assert rows[0]["irrigation_events"] == 1
    assert rows[0]["total_irrigation_liters"] == 500.0


def test_work_completion_report(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="RPTFARM3")

    task = client.post(
        f"/api/v1/work/farms/{farm['id']}/tasks", json={"work_type": "pruning", "title": "Prune row 1"}, headers=headers
    ).json()
    client.post(f"/api/v1/work/tasks/{task['id']}/plan", json={}, headers=headers)
    client.post(f"/api/v1/work/tasks/{task['id']}/assign", json={"assigned_to": tenant.admin_user_id}, headers=headers)
    client.post(f"/api/v1/work/tasks/{task['id']}/accept", json={}, headers=headers)
    client.post(f"/api/v1/work/tasks/{task['id']}/start", headers=headers)
    client.post(f"/api/v1/work/tasks/{task['id']}/complete", json={"evidence": {}}, headers=headers)
    client.post(f"/api/v1/work/tasks/{task['id']}/review", json={"decision": "close"}, headers=headers)

    res = client.get(f"/api/v1/reports/farms/{farm['id']}/work-completion", headers=headers)
    assert res.status_code == 200, res.text
    rows = res.json()
    assert len(rows) == 1
    assert rows[0]["work_type"] == "pruning"
    assert rows[0]["requested"] == 1
    assert rows[0]["closed"] == 1
    assert rows[0]["completion_rate_pct"] == 100.0


def test_disease_trend_report(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="RPTFARM4")
    disease = client.post(
        "/api/v1/crop-health/diseases",
        json={"code": f"anthracnose-{tenant.tenant_slug}", "name_en": "Anthracnose", "name_th": "แอนแทรคโนส", "pathogen_type": "fungal"},
        headers=headers,
    ).json()
    client.post(f"/api/v1/crop-health/farms/{farm['id']}/incidents", json={"disease_id": disease["id"]}, headers=headers)

    res = client.get(f"/api/v1/reports/farms/{farm['id']}/disease-trend", headers=headers)
    assert res.status_code == 200, res.text
    rows = res.json()
    assert len(rows) == 1
    assert rows[0]["new_incidents"] == 1


def test_yield_harvest_report(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="RPTFARM5")
    client.post(
        f"/api/v1/harvest/farms/{farm['id']}/yield-forecasts",
        json={"tree_count": 5, "avg_fruit_count_per_tree": 15, "avg_fruit_weight_kg": 2.5},
        headers=headers,
    )
    client.post(f"/api/v1/harvest/farms/{farm['id']}/harvest-lots", json={"quantity_kg": 10.0}, headers=headers)

    res = client.get(f"/api/v1/reports/farms/{farm['id']}/yield-harvest", headers=headers)
    assert res.status_code == 200, res.text
    rows = res.json()
    assert len(rows) == 1
    assert rows[0]["forecast_count"] == 1
    assert rows[0]["actual_harvest_kg"] == 10.0


def test_maintenance_report(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="RPTFARM6")
    twin_type = client.post(
        "/api/v1/twins/types", json={"code": f"rpt-pump2-{tenant.tenant_slug}", "name": "Pump", "category": "asset"}, headers=headers
    ).json()
    asset = client.post(
        "/api/v1/assets", json={"twin_type_id": twin_type["id"], "display_code": "RPT-PUMP-2", "farm_id": farm["id"]}, headers=headers
    ).json()
    request = client.post(
        f"/api/v1/assets/{asset['id']}/maintenance-requests",
        json={"strategy": "corrective", "description": "Leaking seal"},
        headers=headers,
    ).json()
    client.post(f"/api/v1/maintenance-requests/{request['id']}/submit", headers=headers)
    client.post(f"/api/v1/maintenance-requests/{request['id']}/approve", json={}, headers=headers)
    work_order = client.post(f"/api/v1/maintenance-requests/{request['id']}/convert", headers=headers).json()
    client.patch(f"/api/v1/work-orders/{work_order['id']}", json={"status": "completed", "labor_hours": 2.5}, headers=headers)

    res = client.get(f"/api/v1/reports/farms/{farm['id']}/maintenance", headers=headers)
    assert res.status_code == 200, res.text
    rows = res.json()
    assert len(rows) == 1
    assert rows[0]["strategy"] == "corrective"
    assert rows[0]["work_orders_completed"] == 1
    assert rows[0]["average_labor_hours"] == 2.5
    assert rows[0]["pm_compliance_pct"] == 0.0


def test_inventory_report_is_farm_scoped_via_warehouse(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="RPTFARM7")
    item = client.post(
        "/api/v1/inventory/items",
        json={"code": f"rpt-npk-{tenant.tenant_slug}", "name": "NPK", "category": "fertilizer", "uom": "kg"},
        headers=headers,
    ).json()
    warehouse = client.post(
        "/api/v1/inventory/warehouses",
        json={"farm_id": farm["id"], "code": f"rpt-wh-{tenant.tenant_slug}", "name": "Farm Store"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/inventory/warehouses/{warehouse['id']}/receive",
        json={"item_id": item["id"], "lot_code": "LOT-RPT", "quantity": 100},
        headers=headers,
    )

    res = client.get(f"/api/v1/reports/farms/{farm['id']}/inventory", headers=headers)
    assert res.status_code == 200, res.text
    rows = res.json()
    assert len(rows) == 1
    assert rows[0]["item_code"] == item["code"]
    assert rows[0]["on_hand_qty"] == 100.0
    assert rows[0]["received_qty"] == 100.0


def test_financial_report_actual_and_budget(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="RPTFARM8")
    client.post(
        "/api/v1/accounting/ledger-entries",
        json={"entry_type": "actual", "direction": "revenue", "amount": 1000.0, "dimensions": {"farm_id": farm["id"]}},
        headers=headers,
    )
    client.post(
        "/api/v1/accounting/budgets",
        json={"direction": "revenue", "amount": 1200.0, "dimensions": {"farm_id": farm["id"]}, "period_start": "2020-01-01", "period_end": "2030-01-01"},
        headers=headers,
    )

    res = client.get(f"/api/v1/reports/farms/{farm['id']}/financial", headers=headers)
    assert res.status_code == 200, res.text
    rows = {r["direction"]: r for r in res.json()}
    assert rows["revenue"]["actual_amount"] == 1000.0
    assert rows["revenue"]["budgeted_amount"] == 1200.0
    assert rows["revenue"]["variance"] == -200.0
    assert rows["expense"]["actual_amount"] == 0.0
    assert rows["expense"]["budgeted_amount"] is None


def test_report_export_formats(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="RPTFARM9")

    csv_res = client.get(f"/api/v1/reports/farms/{farm['id']}/health", params={"format": "csv"}, headers=headers)
    assert csv_res.status_code == 200, csv_res.text
    assert csv_res.headers["content-type"].startswith("text/csv")
    assert "farm_id" in csv_res.text

    pdf_res = client.get(f"/api/v1/reports/farms/{farm['id']}/health", params={"format": "pdf"}, headers=headers)
    assert pdf_res.status_code == 200, pdf_res.text
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF")

    bad_res = client.get(f"/api/v1/reports/farms/{farm['id']}/health", params={"format": "xml"}, headers=headers)
    assert bad_res.status_code == 422


def test_date_range_filter_excludes_out_of_range_rows(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="RPTFARM10")
    client.post(f"/api/v1/harvest/farms/{farm['id']}/harvest-lots", json={"quantity_kg": 5.0}, headers=headers)

    future_res = client.get(
        f"/api/v1/reports/farms/{farm['id']}/yield-harvest",
        params={"date_from": "2099-01-01", "date_to": "2099-12-31"},
        headers=headers,
    )
    assert future_res.status_code == 200
    assert future_res.json() == []

    all_time_res = client.get(f"/api/v1/reports/farms/{farm['id']}/yield-harvest", headers=headers)
    assert len(all_time_res.json()) == 1


def test_reporting_farm_scoped_abac(client, tenant):
    admin_headers = tenant.auth_headers(client)
    farm_a = client.post("/api/v1/farm/farms", json={"code": "RPTA", "name": "Report Farm A"}, headers=admin_headers).json()
    farm_b = client.post("/api/v1/farm/farms", json={"code": "RPTB", "name": "Report Farm B"}, headers=admin_headers).json()

    email = f"rptmgr-{unique_slug('u')}@example.com"
    password = "pw-for-testing-123"
    user = client.post(
        "/api/v1/users", json={"email": email, "password": password, "full_name": "Report Manager"}, headers=admin_headers
    ).json()
    roles = {r["code"]: r["id"] for r in client.get("/api/v1/roles", headers=admin_headers).json()}
    client.post(
        "/api/v1/role-assignments",
        json={"user_id": user["id"], "role_id": roles["farm_manager"], "scope_type": "farm", "scope_id": farm_a["id"]},
        headers=admin_headers,
    )

    login_res = client.post("/api/v1/auth/login", json={"tenant_slug": tenant.tenant_slug, "email": email, "password": password})
    manager_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    ok_res = client.get(f"/api/v1/reports/farms/{farm_a['id']}/health", headers=manager_headers)
    assert ok_res.status_code == 200

    denied_res = client.get(f"/api/v1/reports/farms/{farm_b['id']}/health", headers=manager_headers)
    assert denied_res.status_code == 403
