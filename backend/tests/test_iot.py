from datetime import datetime, timedelta, timezone

from app.core.deps import set_tenant_context
from app.iot import models as iot_models
from app.iot.ingestion import check_offline_devices, process_reading
from app.twins import models as twin_models

from .conftest import unique_slug


def _create_farm(client, headers, code="IOTFARM"):
    res = client.post("/api/v1/farm/farms", json={"code": code, "name": "IoT Farm"}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _create_twin_type(client, headers, code="sensor", category="sensor"):
    res = client.post("/api/v1/twins/types", json={"code": code, "name": code.title(), "category": category}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _register_device(client, headers, farm_id, twin_type_id, device_key="dev-1"):
    res = client.post(
        "/api/v1/iot/devices",
        json={
            "farm_id": farm_id,
            "twin_type_id": twin_type_id,
            "display_code": device_key.upper(),
            "device_key": device_key,
            "protocol": "mqtt",
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_device_registration_one_time_secret(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers)
    twin_type = _create_twin_type(client, headers)
    device = _register_device(client, headers, farm["id"], twin_type["id"])

    assert device["secret"]
    assert device["device_key"] == "dev-1"

    get_res = client.get(f"/api/v1/iot/devices/{device['id']}", headers=headers)
    assert get_res.status_code == 200
    assert "secret" not in get_res.json()


def test_process_reading_happy_path(client, tenant, raw_db):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="IOTFARM2")
    twin_type = _create_twin_type(client, headers, code="sensor2")
    device_resp = _register_device(client, headers, farm["id"], twin_type["id"], device_key="dev-happy")

    set_tenant_context(raw_db, tenant.tenant_id)
    device = raw_db.get(iot_models.IotDevice, device_resp["id"])

    result = process_reading(raw_db, device=device, metric="temp_c", value=27.5, secret=device_resp["secret"])
    assert result.accepted
    assert result.reason is None

    set_tenant_context(raw_db, tenant.tenant_id)
    twin = raw_db.get(twin_models.DigitalTwin, device.digital_twin_id)
    assert twin.current_state["temp_c"] == 27.5
    assert device.is_online is True
    assert device.last_seen_at is not None


def test_wrong_secret_is_rejected(client, tenant, raw_db):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="IOTFARM3")
    twin_type = _create_twin_type(client, headers, code="sensor3")
    device_resp = _register_device(client, headers, farm["id"], twin_type["id"], device_key="dev-wrong")

    set_tenant_context(raw_db, tenant.tenant_id)
    device = raw_db.get(iot_models.IotDevice, device_resp["id"])

    result = process_reading(raw_db, device=device, metric="temp_c", value=1.0, secret="not-the-secret")
    assert result.accepted is False
    assert result.reason == "invalid_secret"
    assert device.last_seen_at is None


def test_duplicate_reading_is_a_noop_not_an_error(client, tenant, raw_db):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="IOTFARM4")
    twin_type = _create_twin_type(client, headers, code="sensor4")
    device_resp = _register_device(client, headers, farm["id"], twin_type["id"], device_key="dev-dup")

    set_tenant_context(raw_db, tenant.tenant_id)
    device = raw_db.get(iot_models.IotDevice, device_resp["id"])
    ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    first = process_reading(raw_db, device=device, metric="temp_c", value=25.0, secret=device_resp["secret"], recorded_at=ts)
    assert first.accepted and first.reason is None

    # `process_reading` commits internally (mirrors a per-request commit),
    # which ends the transaction `set_tenant_context`'s is_local=true setting
    # was scoped to - re-set it before the next call on this same session.
    set_tenant_context(raw_db, tenant.tenant_id)
    second = process_reading(raw_db, device=device, metric="temp_c", value=25.0, secret=device_resp["secret"], recorded_at=ts)
    assert second.accepted
    assert second.reason == "duplicate"


def test_rule_breach_raises_alert_and_ack_resolve(client, tenant, raw_db):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="IOTFARM5")
    twin_type = _create_twin_type(client, headers, code="sensor5")
    device_resp = _register_device(client, headers, farm["id"], twin_type["id"], device_key="dev-rule")

    rule_res = client.post(
        "/api/v1/iot/rules",
        json={
            "twin_type_id": twin_type["id"],
            "metric": "temp_c",
            "operator": "gt",
            "threshold_value": 40,
            "severity": "high",
            "message_template": "{metric} is {value}, above {threshold}",
        },
        headers=headers,
    )
    assert rule_res.status_code == 201, rule_res.text

    set_tenant_context(raw_db, tenant.tenant_id)
    device = raw_db.get(iot_models.IotDevice, device_resp["id"])

    result = process_reading(raw_db, device=device, metric="temp_c", value=45.0, secret=device_resp["secret"])
    assert len(result.alerts) == 1
    alert_id = result.alerts[0].id

    # A sustained breach shouldn't raise a second open alert for the same rule.
    set_tenant_context(raw_db, tenant.tenant_id)
    result2 = process_reading(raw_db, device=device, metric="temp_c", value=46.0, secret=device_resp["secret"])
    assert len(result2.alerts) == 0

    alerts_res = client.get("/api/v1/iot/alerts", params={"status": "open"}, headers=headers)
    assert alert_id in [a["id"] for a in alerts_res.json()]

    ack_res = client.post(f"/api/v1/iot/alerts/{alert_id}/acknowledge", headers=headers)
    assert ack_res.status_code == 200
    assert ack_res.json()["status"] == "acknowledged"

    resolve_res = client.post(f"/api/v1/iot/alerts/{alert_id}/resolve", headers=headers)
    assert resolve_res.status_code == 200
    assert resolve_res.json()["status"] == "resolved"


def test_check_offline_devices_is_idempotent(client, tenant, raw_db):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="IOTFARM6")
    twin_type = _create_twin_type(client, headers, code="sensor6")
    device_resp = _register_device(client, headers, farm["id"], twin_type["id"], device_key="dev-offline")

    set_tenant_context(raw_db, tenant.tenant_id)
    device = raw_db.get(iot_models.IotDevice, device_resp["id"])
    stale_ts = datetime.now(timezone.utc) - timedelta(seconds=1000)
    process_reading(raw_db, device=device, metric="temp_c", value=20.0, secret=device_resp["secret"], recorded_at=stale_ts)
    assert device.is_online is True

    # Each of these commits internally, ending the prior is_local=true
    # tenant-context transaction - re-set before every call on this session.
    set_tenant_context(raw_db, tenant.tenant_id)
    alerts = check_offline_devices(raw_db, tenant.tenant_id, timeout_seconds=300)
    assert len(alerts) == 1
    assert device.is_online is False

    set_tenant_context(raw_db, tenant.tenant_id)
    alerts_again = check_offline_devices(raw_db, tenant.tenant_id, timeout_seconds=300)
    assert alerts_again == []


def test_device_farm_scoped_abac(client, tenant):
    admin_headers = tenant.auth_headers(client)
    farm_a = client.post("/api/v1/farm/farms", json={"code": "IOTA", "name": "IoT Farm A"}, headers=admin_headers).json()
    farm_b = client.post("/api/v1/farm/farms", json={"code": "IOTB", "name": "IoT Farm B"}, headers=admin_headers).json()
    twin_type = _create_twin_type(client, admin_headers, code="sensor7")

    device_a = _register_device(client, admin_headers, farm_a["id"], twin_type["id"], device_key="dev-a")
    device_b = _register_device(client, admin_headers, farm_b["id"], twin_type["id"], device_key="dev-b")

    email = f"iotmgr-{unique_slug('u')}@example.com"
    password = "pw-for-testing-123"
    user = client.post(
        "/api/v1/users", json={"email": email, "password": password, "full_name": "IoT Manager"}, headers=admin_headers
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

    ok_res = client.get(f"/api/v1/iot/devices/{device_a['id']}", headers=manager_headers)
    assert ok_res.status_code == 200

    denied_res = client.get(f"/api/v1/iot/devices/{device_b['id']}", headers=manager_headers)
    assert denied_res.status_code == 403
