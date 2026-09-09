from app.crophealth.risk import compute_disease_risk

from .conftest import unique_slug
from .test_farm import _build_hierarchy


def test_risk_engine_low_with_no_signals():
    result = compute_disease_risk()
    assert result.risk_score == 0
    assert result.band == "low"
    assert result.evidence


def test_risk_engine_critical_with_strong_signals():
    result = compute_disease_risk(
        humidity_pct=90,
        rainfall_mm_7d=30,
        leaf_wetness_hours=8,
        recent_confirmed_incident_count=2,
        recent_vision_detection_confidence=0.9,
    )
    assert result.band == "critical"
    assert result.risk_score >= 75
    assert result.confidence > 0.5
    assert len(result.evidence) > 3


def _create_farm(client, headers, code="CHFARM"):
    res = client.post("/api/v1/farm/farms", json={"code": code, "name": "Crop Health Farm"}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _create_disease(client, headers, code="anthracnose"):
    res = client.post(
        "/api/v1/crop-health/diseases",
        json={"code": code, "name_en": "Anthracnose", "name_th": "แอนแทรคโนส", "pathogen_type": "fungal"},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_disease_master_crud(client, tenant):
    headers = tenant.auth_headers(client)
    disease = _create_disease(client, headers, code=f"anthracnose-{tenant.tenant_slug}")

    list_res = client.get("/api/v1/crop-health/diseases", headers=headers)
    assert disease["id"] in [d["id"] for d in list_res.json()]


def test_incident_lifecycle_transitions(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="CHFARM1")
    disease = _create_disease(client, headers, code=f"blight-{tenant.tenant_slug}")

    incident_res = client.post(
        f"/api/v1/crop-health/farms/{farm['id']}/incidents",
        json={"disease_id": disease["id"], "notes": "yellowing leaves observed"},
        headers=headers,
    )
    assert incident_res.status_code == 201, incident_res.text
    incident = incident_res.json()
    assert incident["status"] == "detected"

    invalid_res = client.patch(
        f"/api/v1/crop-health/incidents/{incident['id']}/status", json={"status": "treatment_planned"}, headers=headers
    )
    assert invalid_res.status_code == 409

    valid_res = client.patch(
        f"/api/v1/crop-health/incidents/{incident['id']}/status", json={"status": "suspected"}, headers=headers
    )
    assert valid_res.status_code == 200
    assert valid_res.json()["status"] == "suspected"


def test_treatment_plan_full_lifecycle_syncs_incident_status(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="CHFARM2")
    disease = _create_disease(client, headers, code=f"rot-{tenant.tenant_slug}")

    incident = client.post(
        f"/api/v1/crop-health/farms/{farm['id']}/incidents", json={"disease_id": disease["id"]}, headers=headers
    ).json()
    for status in ("suspected", "inspection_required", "confirmed"):
        client.patch(f"/api/v1/crop-health/incidents/{incident['id']}/status", json={"status": status}, headers=headers)

    plan_res = client.post(
        "/api/v1/crop-health/treatment-plans",
        json={"incident_id": incident["id"], "method": "copper fungicide spray", "reason": "confirmed fungal infection"},
        headers=headers,
    )
    assert plan_res.status_code == 201, plan_res.text
    plan = plan_res.json()

    submit_res = client.post(f"/api/v1/crop-health/treatment-plans/{plan['id']}/submit", headers=headers)
    assert submit_res.status_code == 200, submit_res.text
    assert submit_res.json()["status"] == "pending_approval"

    approve_res = client.post(f"/api/v1/crop-health/treatment-plans/{plan['id']}/approve", json={}, headers=headers)
    assert approve_res.status_code == 200, approve_res.text
    assert approve_res.json()["status"] == "approved"

    incident_after_approve = client.get(f"/api/v1/crop-health/incidents/{incident['id']}", headers=headers).json()
    assert incident_after_approve["status"] == "treatment_planned"

    execute_res = client.post(
        f"/api/v1/crop-health/treatment-plans/{plan['id']}/execute",
        json={"actual_method": {"product": "copper oxychloride", "dose_l": 2.5}},
        headers=headers,
    )
    assert execute_res.status_code == 201, execute_res.text
    assert execute_res.json()["plan_id"] == plan["id"]

    plan_after_execute = client.get(f"/api/v1/crop-health/treatment-plans/{plan['id']}", headers=headers).json()
    assert plan_after_execute["status"] == "completed"

    incident_after_execute = client.get(f"/api/v1/crop-health/incidents/{incident['id']}", headers=headers).json()
    assert incident_after_execute["status"] == "treatment_applied"


def test_treatment_plan_reject_path_blocks_execution(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="CHFARM3")
    disease = _create_disease(client, headers, code=f"wilt-{tenant.tenant_slug}")
    incident = client.post(
        f"/api/v1/crop-health/farms/{farm['id']}/incidents", json={"disease_id": disease["id"]}, headers=headers
    ).json()
    plan = client.post(
        "/api/v1/crop-health/treatment-plans", json={"incident_id": incident["id"]}, headers=headers
    ).json()
    client.post(f"/api/v1/crop-health/treatment-plans/{plan['id']}/submit", headers=headers)

    reject_res = client.post(
        f"/api/v1/crop-health/treatment-plans/{plan['id']}/reject", json={"reason": "needs more evidence"}, headers=headers
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["status"] == "rejected"

    execute_res = client.post(f"/api/v1/crop-health/treatment-plans/{plan['id']}/execute", json={}, headers=headers)
    assert execute_res.status_code == 409


def test_seeded_treatment_workflow_exists(client, tenant):
    headers = tenant.auth_headers(client)
    definitions = client.get("/api/v1/workflows/definitions", headers=headers).json()
    assert "treatment_plan" in {d["entity_type"] for d in definitions}


def test_incident_requires_confirmed_detection(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="CHFARM4")
    disease = _create_disease(client, headers, code=f"scab-{tenant.tenant_slug}")

    twin_type = client.post(
        "/api/v1/twins/types", json={"code": f"cctv-ch-{tenant.tenant_slug}", "name": "CCTV", "category": "camera"}, headers=headers
    ).json()
    camera = client.post(
        "/api/v1/vision/cameras",
        json={"farm_id": farm["id"], "twin_type_id": twin_type["id"], "display_code": "CAM-CH", "protocol": "rtsp"},
        headers=headers,
    ).json()
    model = client.post(
        "/api/v1/vision/models",
        json={"code": f"disease-ch-{tenant.tenant_slug}", "name": "Disease Detector", "use_case": "disease_symptom"},
        headers=headers,
    ).json()
    detection = client.post(
        f"/api/v1/vision/cameras/{camera['id']}/detections",
        json={"model_id": model["id"], "detected_class": "leaf_scab", "confidence": 0.8},
        headers=headers,
    ).json()

    blocked_res = client.post(
        f"/api/v1/crop-health/farms/{farm['id']}/incidents",
        json={"disease_id": disease["id"], "source_detection_id": detection["id"]},
        headers=headers,
    )
    assert blocked_res.status_code == 422

    client.post(f"/api/v1/vision/detections/{detection['id']}/confirm", json={}, headers=headers)

    allowed_res = client.post(
        f"/api/v1/crop-health/farms/{farm['id']}/incidents",
        json={"disease_id": disease["id"], "source_detection_id": detection["id"]},
        headers=headers,
    )
    assert allowed_res.status_code == 201, allowed_res.text
    assert allowed_res.json()["source_detection_id"] == detection["id"]


def test_disease_risk_endpoint_combines_weather(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="CHFARM5")
    client.post(
        "/api/v1/weather/readings",
        json={"farm_id": farm["id"], "metric": "humidity_pct", "value": 92, "source": "station"},
        headers=headers,
    )

    risk_res = client.post(
        f"/api/v1/crop-health/farms/{farm['id']}/risk", json={"leaf_wetness_hours": 7}, headers=headers
    )
    assert risk_res.status_code == 200, risk_res.text
    body = risk_res.json()
    assert body["risk_score"] > 0
    assert any("humidity" in e.lower() for e in body["evidence"])


def test_incident_farm_scoped_abac(client, tenant):
    admin_headers = tenant.auth_headers(client)
    farm_a = client.post("/api/v1/farm/farms", json={"code": "CHA", "name": "CH Farm A"}, headers=admin_headers).json()
    farm_b = client.post("/api/v1/farm/farms", json={"code": "CHB", "name": "CH Farm B"}, headers=admin_headers).json()
    disease = _create_disease(client, admin_headers, code=f"canker-{tenant.tenant_slug}")

    incident_a = client.post(
        f"/api/v1/crop-health/farms/{farm_a['id']}/incidents", json={"disease_id": disease["id"]}, headers=admin_headers
    ).json()
    incident_b = client.post(
        f"/api/v1/crop-health/farms/{farm_b['id']}/incidents", json={"disease_id": disease["id"]}, headers=admin_headers
    ).json()

    email = f"chmgr-{unique_slug('u')}@example.com"
    password = "pw-for-testing-123"
    user = client.post(
        "/api/v1/users", json={"email": email, "password": password, "full_name": "CropHealth Manager"}, headers=admin_headers
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

    ok_res = client.get(f"/api/v1/crop-health/incidents/{incident_a['id']}", headers=manager_headers)
    assert ok_res.status_code == 200

    denied_res = client.get(f"/api/v1/crop-health/incidents/{incident_b['id']}", headers=manager_headers)
    assert denied_res.status_code == 403
