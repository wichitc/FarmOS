from .conftest import unique_slug


def _create_farm(client, headers, code="ACCFARM"):
    res = client.post("/api/v1/farm/farms", json={"code": code, "name": "Accounting Farm"}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _post_entry(client, headers, direction, amount, dimensions, entry_type="actual"):
    res = client.post(
        "/api/v1/accounting/ledger-entries",
        json={"entry_type": entry_type, "direction": direction, "amount": amount, "dimensions": dimensions},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_cost_center_crud(client, tenant):
    headers = tenant.auth_headers(client)
    res = client.post("/api/v1/accounting/cost-centers", json={"code": f"cc-{tenant.tenant_slug}", "name": "Field Ops"}, headers=headers)
    assert res.status_code == 201, res.text
    cc = res.json()

    list_res = client.get("/api/v1/accounting/cost-centers", headers=headers)
    assert cc["id"] in [c["id"] for c in list_res.json()]


def test_post_and_list_ledger_entries(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="ACCFARM1")

    _post_entry(client, headers, "revenue", 1000.0, {"farm_id": farm["id"]})
    _post_entry(client, headers, "expense", 400.0, {"farm_id": farm["id"]})

    list_res = client.get("/api/v1/accounting/ledger-entries", params={"farm_id": farm["id"]}, headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) == 2


def test_profitability_computation(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="ACCFARM2")
    _post_entry(client, headers, "revenue", 1000.0, {"farm_id": farm["id"], "plot_id": "plot-x"})
    _post_entry(client, headers, "expense", 400.0, {"farm_id": farm["id"], "plot_id": "plot-x"})

    profit_res = client.post(
        "/api/v1/accounting/profitability",
        json={"dimensions": {"farm_id": farm["id"], "plot_id": "plot-x"}, "overhead_allocation_pct": 10},
        headers=headers,
    )
    assert profit_res.status_code == 200, profit_res.text
    result = profit_res.json()
    assert result["revenue"] == 1000.0
    assert result["direct_costs"] == 400.0
    assert result["allocated_overhead"] == 100.0
    assert result["profit"] == 500.0
    assert result["margin_pct"] == 50.0


def test_budget_variance(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="ACCFARM3")

    budget_res = client.post(
        "/api/v1/accounting/budgets",
        json={
            "direction": "expense", "amount": 1000.0, "dimensions": {"farm_id": farm["id"]},
            "period_start": "2026-01-01", "period_end": "2026-12-31",
        },
        headers=headers,
    )
    assert budget_res.status_code == 201, budget_res.text
    budget = budget_res.json()

    _post_entry(client, headers, "expense", 1200.0, {"farm_id": farm["id"]})

    variance_res = client.get(f"/api/v1/accounting/budgets/{budget['id']}/variance", headers=headers)
    assert variance_res.status_code == 200, variance_res.text
    variance = variance_res.json()
    assert variance["budgeted_amount"] == 1000.0
    assert variance["actual_amount"] == 1200.0
    assert variance["variance"] == 200.0


def test_profitability_heatmap_groups_by_plot(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="ACCFARM4")
    _post_entry(client, headers, "revenue", 500.0, {"farm_id": farm["id"], "plot_id": "plot-a"})
    _post_entry(client, headers, "revenue", 300.0, {"farm_id": farm["id"], "plot_id": "plot-b"})

    heatmap_res = client.get(
        "/api/v1/accounting/profitability/heatmap", params={"farm_id": farm["id"], "group_by": "plot_id"}, headers=headers
    )
    assert heatmap_res.status_code == 200, heatmap_res.text
    rows = {r["group_id"]: r for r in heatmap_res.json()}
    assert rows["plot-a"]["revenue"] == 500.0
    assert rows["plot-b"]["revenue"] == 300.0


def test_ledger_farm_scoped_abac(client, tenant):
    admin_headers = tenant.auth_headers(client)
    farm_a = client.post("/api/v1/farm/farms", json={"code": "ACCA", "name": "Acc Farm A"}, headers=admin_headers).json()
    farm_b = client.post("/api/v1/farm/farms", json={"code": "ACCB", "name": "Acc Farm B"}, headers=admin_headers).json()

    _post_entry(client, admin_headers, "revenue", 100.0, {"farm_id": farm_a["id"]})
    _post_entry(client, admin_headers, "revenue", 100.0, {"farm_id": farm_b["id"]})

    email = f"finmgr-{unique_slug('u')}@example.com"
    password = "pw-for-testing-123"
    user = client.post(
        "/api/v1/users", json={"email": email, "password": password, "full_name": "Finance Manager"}, headers=admin_headers
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

    ok_res = client.get("/api/v1/accounting/ledger-entries", params={"farm_id": farm_a["id"]}, headers=manager_headers)
    assert ok_res.status_code == 200

    denied_res = client.get("/api/v1/accounting/ledger-entries", params={"farm_id": farm_b["id"]}, headers=manager_headers)
    assert denied_res.status_code == 403
