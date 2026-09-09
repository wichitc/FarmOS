from .test_farm import _build_hierarchy, _create_crop
from .conftest import unique_slug


def _create_twin_type(client, headers, code="pump", category="asset"):
    res = client.post(
        "/api/v1/twins/types",
        json={"code": code, "name": code.title(), "category": category},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_twin_type_and_digital_twin_crud(client, tenant):
    headers = tenant.auth_headers(client)
    twin_type = _create_twin_type(client, headers)

    create_res = client.post(
        "/api/v1/twins",
        json={"twin_type_id": twin_type["id"], "display_code": "PUMP-001", "current_state": {"status": "running"}},
        headers=headers,
    )
    assert create_res.status_code == 201, create_res.text
    twin = create_res.json()
    assert twin["farm_id"] is None

    inspector_res = client.get(f"/api/v1/twins/{twin['id']}", headers=headers)
    assert inspector_res.status_code == 200, inspector_res.text
    inspector = inspector_res.json()
    assert inspector["display_code"] == "PUMP-001"
    assert inspector["twin_type"]["code"] == "pump"
    assert inspector["current_state"]["status"] == "running"
    assert inspector["properties"] == {}
    assert inspector["recent_events"] == []

    patch_res = client.patch(f"/api/v1/twins/{twin['id']}", json={"status": "maintenance"}, headers=headers)
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "maintenance"

    delete_res = client.delete(f"/api/v1/twins/{twin['id']}", headers=headers)
    assert delete_res.status_code == 204

    list_res = client.get("/api/v1/twins", headers=headers)
    assert twin["id"] not in [t["id"] for t in list_res.json()]


def test_twin_relationship_both_directions(client, tenant):
    headers = tenant.auth_headers(client)
    twin_type = _create_twin_type(client, headers, code="valve")

    pump = client.post(
        "/api/v1/twins", json={"twin_type_id": twin_type["id"], "display_code": "PUMP-A"}, headers=headers
    ).json()
    valve = client.post(
        "/api/v1/twins", json={"twin_type_id": twin_type["id"], "display_code": "VALVE-A"}, headers=headers
    ).json()

    rel_res = client.post(
        f"/api/v1/twins/{pump['id']}/relationships",
        json={"to_twin_id": valve["id"], "relation_type": "SUPPLIED_BY"},
        headers=headers,
    )
    assert rel_res.status_code == 201, rel_res.text

    from_side = client.get(f"/api/v1/twins/{pump['id']}/relationships", headers=headers)
    to_side = client.get(f"/api/v1/twins/{valve['id']}/relationships", headers=headers)
    assert len(from_side.json()) == 1
    assert len(to_side.json()) == 1
    assert from_side.json()[0]["relation_type"] == "SUPPLIED_BY"


def test_twin_property_upsert(client, tenant):
    headers = tenant.auth_headers(client)
    twin_type = _create_twin_type(client, headers)
    twin = client.post(
        "/api/v1/twins", json={"twin_type_id": twin_type["id"], "display_code": "PUMP-B"}, headers=headers
    ).json()

    set_res = client.put(
        f"/api/v1/twins/{twin['id']}/properties", json={"key": "manufacturer", "value": "Grundfos"}, headers=headers
    )
    assert set_res.status_code == 200, set_res.text

    overwrite_res = client.put(
        f"/api/v1/twins/{twin['id']}/properties", json={"key": "manufacturer", "value": "Wilo"}, headers=headers
    )
    assert overwrite_res.status_code == 200

    list_res = client.get(f"/api/v1/twins/{twin['id']}/properties", headers=headers)
    props = list_res.json()
    assert len(props) == 1
    assert props[0]["value"] == "Wilo"


def test_twin_event_append_only(client, tenant):
    headers = tenant.auth_headers(client)
    twin_type = _create_twin_type(client, headers)
    twin = client.post(
        "/api/v1/twins", json={"twin_type_id": twin_type["id"], "display_code": "PUMP-C"}, headers=headers
    ).json()

    event_res = client.post(
        f"/api/v1/twins/{twin['id']}/events",
        json={"event_type": "alarm_raised", "payload": {"code": "OVERHEAT"}},
        headers=headers,
    )
    assert event_res.status_code == 201, event_res.text

    list_res = client.get(f"/api/v1/twins/{twin['id']}/events", headers=headers)
    assert len(list_res.json()) == 1
    assert list_res.json()[0]["event_type"] == "alarm_raised"


def test_twin_telemetry_latest_first(client, tenant):
    headers = tenant.auth_headers(client)
    twin_type = _create_twin_type(client, headers, code="sensor", category="sensor")
    twin = client.post(
        "/api/v1/twins", json={"twin_type_id": twin_type["id"], "display_code": "SENSOR-1"}, headers=headers
    ).json()

    client.post(f"/api/v1/twins/{twin['id']}/telemetry", json={"metric": "temp_c", "value_numeric": 25.5}, headers=headers)
    client.post(f"/api/v1/twins/{twin['id']}/telemetry", json={"metric": "temp_c", "value_numeric": 26.0}, headers=headers)

    list_res = client.get(f"/api/v1/twins/{twin['id']}/telemetry", headers=headers)
    assert list_res.status_code == 200
    readings = list_res.json()
    assert len(readings) == 2
    assert readings[0]["value_numeric"] == 26.0

    inspector_res = client.get(f"/api/v1/twins/{twin['id']}", headers=headers)
    assert inspector_res.json()["latest_telemetry"]["temp_c"]["value_numeric"] == 26.0


def test_tree_creation_auto_links_digital_twin(client, tenant):
    headers = tenant.auth_headers(client)
    crop = _create_crop(client, headers, code=f"durian-twin-{tenant.tenant_slug}")
    farm, _zone, _plot, _block, row = _build_hierarchy(client, headers, farm_code="TWINFARM")

    tree_res = client.post(
        f"/api/v1/farm/rows/{row['id']}/trees", json={"crop_id": crop["id"]}, headers=headers
    )
    assert tree_res.status_code == 201, tree_res.text
    tree = tree_res.json()
    assert tree["digital_twin_id"], "tree should be auto-linked to a digital twin"

    inspector_res = client.get(f"/api/v1/twins/{tree['digital_twin_id']}", headers=headers)
    assert inspector_res.status_code == 200, inspector_res.text
    inspector = inspector_res.json()
    assert inspector["display_code"] == tree["code"]
    assert inspector["farm_id"] == farm["id"]
    assert inspector["twin_type"]["code"] == "tree"
    assert inspector["current_state"]["growth_stage"] == "seedling"


def test_twin_farm_scoped_abac(client, tenant):
    admin_headers = tenant.auth_headers(client)
    farm_a = client.post("/api/v1/farm/farms", json={"code": "TWA", "name": "Twin Farm A"}, headers=admin_headers).json()
    farm_b = client.post("/api/v1/farm/farms", json={"code": "TWB", "name": "Twin Farm B"}, headers=admin_headers).json()
    twin_type = _create_twin_type(client, admin_headers, code="camera", category="camera")

    twin_a = client.post(
        "/api/v1/twins",
        json={"twin_type_id": twin_type["id"], "display_code": "CAM-A", "farm_id": farm_a["id"]},
        headers=admin_headers,
    ).json()
    twin_b = client.post(
        "/api/v1/twins",
        json={"twin_type_id": twin_type["id"], "display_code": "CAM-B", "farm_id": farm_b["id"]},
        headers=admin_headers,
    ).json()

    email = f"twinmgr-{unique_slug('u')}@example.com"
    password = "pw-for-testing-123"
    user = client.post(
        "/api/v1/users", json={"email": email, "password": password, "full_name": "Twin Manager"}, headers=admin_headers
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

    ok_res = client.get(f"/api/v1/twins/{twin_a['id']}", headers=manager_headers)
    assert ok_res.status_code == 200

    denied_res = client.get(f"/api/v1/twins/{twin_b['id']}", headers=manager_headers)
    assert denied_res.status_code == 403
