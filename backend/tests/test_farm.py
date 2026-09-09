from .conftest import unique_slug


def _create_crop(client, headers, code="durian"):
    res = client.post(
        "/api/v1/master-data/crops",
        json={"code": code, "name_en": "Durian", "name_th": "ทุเรียน"},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


def _build_hierarchy(client, headers, farm_code="F01"):
    farm = client.post("/api/v1/farm/farms", json={"code": farm_code, "name": "Farm One"}, headers=headers).json()
    zone = client.post(f"/api/v1/farm/farms/{farm['id']}/zones", json={"code": "Z1", "name": "Zone 1"}, headers=headers).json()
    plot = client.post(f"/api/v1/farm/zones/{zone['id']}/plots", json={"code": "P1", "name": "Plot 1"}, headers=headers).json()
    block = client.post(f"/api/v1/farm/plots/{plot['id']}/blocks", json={"code": "A", "name": "Block A"}, headers=headers).json()
    row = client.post(f"/api/v1/farm/blocks/{block['id']}/rows", json={"code": "R03", "name": "Row 3"}, headers=headers).json()
    return farm, zone, plot, block, row


def test_full_hierarchy_and_tree_code_generation(client, tenant):
    headers = tenant.auth_headers(client)
    crop = _create_crop(client, headers, code=f"durian-{tenant.tenant_slug}")
    farm, zone, plot, block, row = _build_hierarchy(client, headers, farm_code="FARM01")

    tree_res = client.post(
        f"/api/v1/farm/rows/{row['id']}/trees",
        json={"crop_id": crop["id"], "planting_date": "2024-01-15"},
        headers=headers,
    )
    assert tree_res.status_code == 201, tree_res.text
    tree = tree_res.json()
    assert tree["code"] == f"FARM01-{crop['code'].upper()}-A-R03-T001"
    assert tree["growth_stage"] == "seedling"


def test_bulk_grid_and_csv_import(client, tenant):
    headers = tenant.auth_headers(client)
    crop = _create_crop(client, headers, code=f"mango-{tenant.tenant_slug}")
    _farm, _zone, _plot, _block, row = _build_hierarchy(client, headers, farm_code="FARM02")

    bulk_res = client.post(
        f"/api/v1/farm/rows/{row['id']}/trees/bulk",
        json={"trees": [{"crop_id": crop["id"]}, {"crop_id": crop["id"]}]},
        headers=headers,
    )
    assert bulk_res.status_code == 201, bulk_res.text
    assert len(bulk_res.json()) == 2

    grid_res = client.post(
        f"/api/v1/farm/rows/{row['id']}/trees/generate-grid",
        json={"crop_id": crop["id"], "count": 3, "spacing_m": 3.0, "start_lat": 13.7, "start_lng": 100.5},
        headers=headers,
    )
    assert grid_res.status_code == 201, grid_res.text
    grid_trees = grid_res.json()
    assert len(grid_trees) == 3
    lats = sorted(t["lat"] for t in grid_trees)
    assert lats[0] < lats[1] < lats[2]

    csv_content = f"crop_code,planting_date\n{crop['code']},2024-02-01\n{crop['code']},2024-02-02\n"
    csv_res = client.post(
        f"/api/v1/farm/rows/{row['id']}/trees/import-csv",
        files={"file": ("trees.csv", csv_content, "text/csv")},
        headers=headers,
    )
    assert csv_res.status_code == 201, csv_res.text
    assert len(csv_res.json()) == 2

    list_res = client.get(f"/api/v1/farm/rows/{row['id']}/trees", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) == 2 + 3 + 2


def test_tree_update_soft_delete_and_events(client, tenant):
    headers = tenant.auth_headers(client)
    crop = _create_crop(client, headers, code=f"longan-{tenant.tenant_slug}")
    _farm, _zone, _plot, _block, row = _build_hierarchy(client, headers, farm_code="FARM03")
    tree = client.post(
        f"/api/v1/farm/rows/{row['id']}/trees", json={"crop_id": crop["id"]}, headers=headers
    ).json()

    patch_res = client.patch(
        f"/api/v1/farm/trees/{tree['id']}", json={"growth_stage": "flowering"}, headers=headers
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["growth_stage"] == "flowering"

    event_res = client.post(
        f"/api/v1/farm/trees/{tree['id']}/events",
        json={"event_type": "irrigation", "payload": {"liters": 20}},
        headers=headers,
    )
    assert event_res.status_code == 201, event_res.text

    events_res = client.get(f"/api/v1/farm/trees/{tree['id']}/events", headers=headers)
    assert events_res.status_code == 200
    assert len(events_res.json()) == 1
    assert events_res.json()[0]["event_type"] == "irrigation"

    delete_res = client.delete(f"/api/v1/farm/trees/{tree['id']}", headers=headers)
    assert delete_res.status_code == 204

    list_res = client.get(f"/api/v1/farm/rows/{row['id']}/trees", headers=headers)
    assert list_res.json() == []

    get_res = client.get(f"/api/v1/farm/trees/{tree['id']}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["deleted_at"] is not None


def test_season_crud(client, tenant):
    headers = tenant.auth_headers(client)
    farm = client.post("/api/v1/farm/farms", json={"code": "FARM04", "name": "Farm Four"}, headers=headers).json()

    season_res = client.post(
        f"/api/v1/farm/farms/{farm['id']}/seasons",
        json={"name": "2026 Wet Season", "start_date": "2026-05-01", "end_date": "2026-10-31"},
        headers=headers,
    )
    assert season_res.status_code == 201, season_res.text

    list_res = client.get(f"/api/v1/farm/farms/{farm['id']}/seasons", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1


def test_farm_scoped_abac(client, tenant):
    admin_headers = tenant.auth_headers(client)
    farm_a = client.post("/api/v1/farm/farms", json={"code": "FA", "name": "Farm A"}, headers=admin_headers).json()
    farm_b = client.post("/api/v1/farm/farms", json={"code": "FB", "name": "Farm B"}, headers=admin_headers).json()

    email = f"manager-{unique_slug('u')}@example.com"
    password = "pw-for-testing-123"
    user_res = client.post(
        "/api/v1/users", json={"email": email, "password": password, "full_name": "Farm Manager"}, headers=admin_headers
    )
    assert user_res.status_code == 201, user_res.text
    user = user_res.json()

    roles = {r["code"]: r["id"] for r in client.get("/api/v1/roles", headers=admin_headers).json()}
    assign_res = client.post(
        "/api/v1/role-assignments",
        json={"user_id": user["id"], "role_id": roles["farm_manager"], "scope_type": "farm", "scope_id": farm_a["id"]},
        headers=admin_headers,
    )
    assert assign_res.status_code == 201, assign_res.text

    login_res = client.post(
        "/api/v1/auth/login", json={"tenant_slug": tenant.tenant_slug, "email": email, "password": password}
    )
    assert login_res.status_code == 200
    manager_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    ok_res = client.get(f"/api/v1/farm/farms/{farm_a['id']}", headers=manager_headers)
    assert ok_res.status_code == 200

    denied_res = client.get(f"/api/v1/farm/farms/{farm_b['id']}", headers=manager_headers)
    assert denied_res.status_code == 403

    denied_zone_res = client.post(
        f"/api/v1/farm/farms/{farm_b['id']}/zones", json={"code": "Z1", "name": "Zone 1"}, headers=manager_headers
    )
    assert denied_zone_res.status_code == 403

    allowed_zone_res = client.post(
        f"/api/v1/farm/farms/{farm_a['id']}/zones", json={"code": "Z1", "name": "Zone 1"}, headers=manager_headers
    )
    assert allowed_zone_res.status_code == 201, allowed_zone_res.text
