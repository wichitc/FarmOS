from .test_farm import _build_hierarchy, _create_crop

SQUARE_BOUNDARY = {
    "type": "Polygon",
    "coordinates": [[
        [100.0, 13.0], [100.001, 13.0], [100.001, 13.001], [100.0, 13.001], [100.0, 13.0],
    ]],
}


def _create_farm(client, headers, code="GFARM"):
    return client.post("/api/v1/farm/farms", json={"code": code, "name": "GIS Farm"}, headers=headers).json()


def test_set_farm_boundary_computes_area_and_is_audited(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="GFARM1")

    res = client.patch(f"/api/v1/farm/farms/{farm['id']}/boundary", json=SQUARE_BOUNDARY, headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["boundary"]["type"] == "Polygon"
    # ~0.001deg square at 13N is ~111m x ~108m => roughly 1.2 ha; loose bound
    # to tolerate geodesic vs. planar approximation, not exact geometry.
    assert 1.0 < body["area_hectares"] < 1.4

    audit_res = client.get(
        "/api/v1/audit", params={"entity_type": "farm", "entity_id": farm["id"]}, headers=headers
    )
    assert audit_res.status_code == 200
    actions = [e["action"] for e in audit_res.json()]
    assert "farm.set_boundary" in actions


def test_zone_plot_block_boundary_and_row_centerline(client, tenant):
    headers = tenant.auth_headers(client)
    farm, zone, plot, block, row = _build_hierarchy(client, headers, farm_code="GFARM2")

    zone_res = client.patch(f"/api/v1/farm/zones/{zone['id']}/boundary", json=SQUARE_BOUNDARY, headers=headers)
    assert zone_res.status_code == 200, zone_res.text
    assert zone_res.json()["area_hectares"] > 0

    plot_res = client.patch(f"/api/v1/farm/plots/{plot['id']}/boundary", json=SQUARE_BOUNDARY, headers=headers)
    assert plot_res.status_code == 200, plot_res.text

    block_res = client.patch(f"/api/v1/farm/blocks/{block['id']}/boundary", json=SQUARE_BOUNDARY, headers=headers)
    assert block_res.status_code == 200, block_res.text

    centerline = {"type": "LineString", "coordinates": [[100.0, 13.0], [100.001, 13.0]]}
    row_res = client.patch(f"/api/v1/farm/rows/{row['id']}/centerline", json=centerline, headers=headers)
    assert row_res.status_code == 200, row_res.text
    assert row_res.json()["centerline"]["type"] == "LineString"


def test_map_feature_crud(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="GFARM3")

    create_res = client.post(
        f"/api/v1/gis/farms/{farm['id']}/features",
        json={
            "feature_type": "pump",
            "name": "Pump 1",
            "geometry": {"type": "Point", "coordinates": [100.0005, 13.0005]},
            "properties": {"capacity_lps": 5},
        },
        headers=headers,
    )
    assert create_res.status_code == 201, create_res.text
    feature = create_res.json()
    assert feature["geometry"]["type"] == "Point"

    list_res = client.get(f"/api/v1/gis/farms/{farm['id']}/features", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1

    patch_res = client.patch(
        f"/api/v1/gis/features/{feature['id']}", json={"name": "Pump 1 - Renamed"}, headers=headers
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Pump 1 - Renamed"

    delete_res = client.delete(f"/api/v1/gis/features/{feature['id']}", headers=headers)
    assert delete_res.status_code == 204

    list_after = client.get(f"/api/v1/gis/farms/{farm['id']}/features", headers=headers)
    assert list_after.json() == []


def test_export_and_import_geojson(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="GFARM4")
    client.patch(f"/api/v1/farm/farms/{farm['id']}/boundary", json=SQUARE_BOUNDARY, headers=headers)
    client.post(
        f"/api/v1/gis/farms/{farm['id']}/features",
        json={"feature_type": "pond", "name": "Pond A", "geometry": {"type": "Point", "coordinates": [100.0002, 13.0002]}},
        headers=headers,
    )

    export_res = client.get(f"/api/v1/gis/farms/{farm['id']}/export", headers=headers)
    assert export_res.status_code == 200
    layers = {f["properties"]["layer"] for f in export_res.json()["features"]}
    assert "farm" in layers
    assert "map_feature" in layers

    import_payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [100.0003, 13.0003]},
                "properties": {"feature_type": "sensor", "name": "Soil Sensor 1"},
            }
        ],
    }
    import_res = client.post(f"/api/v1/gis/farms/{farm['id']}/import", json=import_payload, headers=headers)
    assert import_res.status_code == 201, import_res.text
    assert len(import_res.json()) == 1

    features_res = client.get(f"/api/v1/gis/farms/{farm['id']}/features", headers=headers)
    assert len(features_res.json()) == 2


def test_measure_area_and_length(client, tenant):
    headers = tenant.auth_headers(client)

    area_res = client.post("/api/v1/gis/measure", json={"geometry": SQUARE_BOUNDARY}, headers=headers)
    assert area_res.status_code == 200, area_res.text
    area_body = area_res.json()
    assert area_body["length_m"] is None
    assert 1.0 < area_body["area_hectares"] < 1.4

    line_res = client.post(
        "/api/v1/gis/measure",
        json={"geometry": {"type": "LineString", "coordinates": [[100.0, 13.0], [100.001, 13.0]]}},
        headers=headers,
    )
    assert line_res.status_code == 200, line_res.text
    line_body = line_res.json()
    assert line_body["area_hectares"] is None
    assert 100 < line_body["length_m"] < 120


def test_trees_nearby(client, tenant):
    headers = tenant.auth_headers(client)
    crop = _create_crop(client, headers, code=f"durian-gis-{tenant.tenant_slug}")
    farm, _zone, _plot, _block, row = _build_hierarchy(client, headers, farm_code="GFARM5")

    tree = client.post(
        f"/api/v1/farm/rows/{row['id']}/trees",
        json={"crop_id": crop["id"], "lat": 13.0, "lng": 100.0},
        headers=headers,
    ).json()

    near_res = client.get(
        "/api/v1/gis/trees/nearby",
        params={"farm_id": farm["id"], "lat": 13.0, "lng": 100.0, "radius_m": 50},
        headers=headers,
    )
    assert near_res.status_code == 200, near_res.text
    results = near_res.json()
    assert len(results) == 1
    assert results[0]["id"] == tree["id"]
    assert results[0]["distance_m"] < 1

    far_res = client.get(
        "/api/v1/gis/trees/nearby",
        params={"farm_id": farm["id"], "lat": 20.0, "lng": 100.0, "radius_m": 50},
        headers=headers,
    )
    assert far_res.json() == []


def test_generate_grid_respects_plot_boundary(client, tenant):
    headers = tenant.auth_headers(client)
    crop = _create_crop(client, headers, code=f"durian-grid-{tenant.tenant_slug}")
    _farm, _zone, plot, _block, row = _build_hierarchy(client, headers, farm_code="GFARM6")

    # A tiny box that only contains the start point - the next point 3m
    # north falls well outside it.
    tiny_box = {
        "type": "Polygon",
        "coordinates": [[
            [99.999990, 12.999990], [100.000010, 12.999990],
            [100.000010, 13.000010], [99.999990, 13.000010], [99.999990, 12.999990],
        ]],
    }
    boundary_res = client.patch(f"/api/v1/farm/plots/{plot['id']}/boundary", json=tiny_box, headers=headers)
    assert boundary_res.status_code == 200, boundary_res.text

    ok_res = client.post(
        f"/api/v1/farm/rows/{row['id']}/trees/generate-grid",
        json={"crop_id": crop["id"], "count": 1, "spacing_m": 3.0, "start_lat": 13.0, "start_lng": 100.0},
        headers=headers,
    )
    assert ok_res.status_code == 201, ok_res.text

    fail_res = client.post(
        f"/api/v1/farm/rows/{row['id']}/trees/generate-grid",
        json={"crop_id": crop["id"], "count": 2, "spacing_m": 3.0, "start_lat": 13.0, "start_lng": 100.0},
        headers=headers,
    )
    assert fail_res.status_code == 422, fail_res.text
