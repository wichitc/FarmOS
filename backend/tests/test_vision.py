from app.vision.inference import StubVisionInferenceEngine

from .conftest import unique_slug
from .test_farm import _build_hierarchy, _create_crop


def test_stub_inference_engine_returns_no_detections():
    engine = StubVisionInferenceEngine()
    result = engine.run_inference(camera_id="whatever", use_case="disease_symptom", frame_ref="s3://x/y.jpg")
    assert result == []


def _create_farm(client, headers, code="VISFARM"):
    res = client.post("/api/v1/farm/farms", json={"code": code, "name": "Vision Farm"}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _create_camera_twin_type(client, headers, code="cctv"):
    res = client.post("/api/v1/twins/types", json={"code": code, "name": "CCTV", "category": "camera"}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _register_camera(client, headers, farm_id, twin_type_id, display_code="CAM-1"):
    res = client.post(
        "/api/v1/vision/cameras",
        json={"farm_id": farm_id, "twin_type_id": twin_type_id, "display_code": display_code, "protocol": "rtsp"},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


def _create_vision_model(client, headers, code="disease-v0", use_case="disease_symptom"):
    res = client.post(
        "/api/v1/vision/models", json={"code": code, "name": "Disease Detector", "use_case": use_case}, headers=headers
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_camera_registration(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="VISFARM1")
    twin_type = _create_camera_twin_type(client, headers, code="cctv1")
    camera = _register_camera(client, headers, farm["id"], twin_type["id"])

    assert camera["farm_id"] == farm["id"]
    assert camera["digital_twin_id"]

    get_res = client.get(f"/api/v1/vision/cameras/{camera['id']}", headers=headers)
    assert get_res.status_code == 200


def test_vision_model_crud(client, tenant):
    headers = tenant.auth_headers(client)
    model = _create_vision_model(client, headers, code="fruit-v0", use_case="fruit_detection")

    list_res = client.get("/api/v1/vision/models", headers=headers)
    assert model["id"] in [m["id"] for m in list_res.json()]


def test_detection_confirm_and_reject_lifecycle(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="VISFARM2")
    twin_type = _create_camera_twin_type(client, headers, code="cctv2")
    camera = _register_camera(client, headers, farm["id"], twin_type["id"])
    model = _create_vision_model(client, headers, code="disease-v1")

    create_res = client.post(
        f"/api/v1/vision/cameras/{camera['id']}/detections",
        json={"model_id": model["id"], "detected_class": "leaf_blight", "confidence": 0.87, "bounding_box": {"x": 10, "y": 20, "w": 30, "h": 40}},
        headers=headers,
    )
    assert create_res.status_code == 201, create_res.text
    detection = create_res.json()
    assert detection["validation_status"] == "pending"

    confirm_res = client.post(
        f"/api/v1/vision/detections/{detection['id']}/confirm", json={"notes": "confirmed on-site"}, headers=headers
    )
    assert confirm_res.status_code == 200, confirm_res.text
    confirmed = confirm_res.json()
    assert confirmed["validation_status"] == "confirmed"
    assert confirmed["reviewed_by"] == tenant.admin_user_id
    assert confirmed["reviewed_at"]

    # Already reviewed - can't review again.
    reconfirm_res = client.post(f"/api/v1/vision/detections/{detection['id']}/confirm", json={}, headers=headers)
    assert reconfirm_res.status_code == 409

    create_res2 = client.post(
        f"/api/v1/vision/cameras/{camera['id']}/detections",
        json={"model_id": model["id"], "detected_class": "leaf_blight", "confidence": 0.4, "bounding_box": {}},
        headers=headers,
    )
    detection2 = create_res2.json()
    reject_res = client.post(
        f"/api/v1/vision/detections/{detection2['id']}/reject", json={"notes": "false positive"}, headers=headers
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["validation_status"] == "rejected"

    pending_res = client.get(
        f"/api/v1/vision/cameras/{camera['id']}/detections", params={"validation_status": "pending"}, headers=headers
    )
    assert pending_res.json() == []


def test_detection_linked_to_tree(client, tenant):
    headers = tenant.auth_headers(client)
    crop = _create_crop(client, headers, code=f"durian-vis-{tenant.tenant_slug}")
    farm, _zone, _plot, _block, row = _build_hierarchy(client, headers, farm_code="VISFARM3")
    tree = client.post(f"/api/v1/farm/rows/{row['id']}/trees", json={"crop_id": crop["id"]}, headers=headers).json()

    twin_type = _create_camera_twin_type(client, headers, code="cctv3")
    camera = _register_camera(client, headers, farm["id"], twin_type["id"])
    model = _create_vision_model(client, headers, code="disease-v2")

    detection_res = client.post(
        f"/api/v1/vision/cameras/{camera['id']}/detections",
        json={"model_id": model["id"], "tree_id": tree["id"], "detected_class": "leaf_discoloration", "confidence": 0.7},
        headers=headers,
    )
    assert detection_res.status_code == 201, detection_res.text
    assert detection_res.json()["tree_id"] == tree["id"]


def test_camera_farm_scoped_abac(client, tenant):
    admin_headers = tenant.auth_headers(client)
    farm_a = client.post("/api/v1/farm/farms", json={"code": "VISA", "name": "Vis Farm A"}, headers=admin_headers).json()
    farm_b = client.post("/api/v1/farm/farms", json={"code": "VISB", "name": "Vis Farm B"}, headers=admin_headers).json()
    twin_type = _create_camera_twin_type(client, admin_headers, code="cctv4")

    camera_a = _register_camera(client, admin_headers, farm_a["id"], twin_type["id"], display_code="CAM-A")
    camera_b = _register_camera(client, admin_headers, farm_b["id"], twin_type["id"], display_code="CAM-B")

    email = f"vismgr-{unique_slug('u')}@example.com"
    password = "pw-for-testing-123"
    user = client.post(
        "/api/v1/users", json={"email": email, "password": password, "full_name": "Vision Manager"}, headers=admin_headers
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

    ok_res = client.get(f"/api/v1/vision/cameras/{camera_a['id']}", headers=manager_headers)
    assert ok_res.status_code == 200

    denied_res = client.get(f"/api/v1/vision/cameras/{camera_b['id']}", headers=manager_headers)
    assert denied_res.status_code == 403
