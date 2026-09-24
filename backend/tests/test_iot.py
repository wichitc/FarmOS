from datetime import datetime, timedelta, timezone

from app.ai import models as ai_models
from app.core.deps import set_tenant_context
from app.iot import models as iot_models
from app.iot.ingestion import check_offline_devices, process_reading
from app.iot.scheduling import fire_scheduled_commands
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


def test_rotate_secret_invalidates_old_secret_and_issues_a_new_one(client, tenant, raw_db):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="IOTFARM8")
    twin_type = _create_twin_type(client, headers, code="sensor8")
    device_resp = _register_device(client, headers, farm["id"], twin_type["id"], device_key="dev-rotate")

    rotate_res = client.post(f"/api/v1/iot/devices/{device_resp['id']}/rotate-secret", headers=headers)
    assert rotate_res.status_code == 200, rotate_res.text
    rotated = rotate_res.json()
    assert rotated["secret"]
    assert rotated["secret"] != device_resp["secret"]

    set_tenant_context(raw_db, tenant.tenant_id)
    device = raw_db.get(iot_models.IotDevice, device_resp["id"])

    old_secret_result = process_reading(raw_db, device=device, metric="temp_c", value=1.0, secret=device_resp["secret"])
    assert old_secret_result.accepted is False
    assert old_secret_result.reason == "invalid_secret"

    new_secret_result = process_reading(raw_db, device=device, metric="temp_c", value=2.0, secret=rotated["secret"])
    assert new_secret_result.accepted is True


def test_deactivated_device_is_rejected_even_with_the_correct_secret(client, tenant, raw_db):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="IOTFARM9")
    twin_type = _create_twin_type(client, headers, code="sensor9")
    device_resp = _register_device(client, headers, farm["id"], twin_type["id"], device_key="dev-deactivate")

    deactivate_res = client.post(
        f"/api/v1/iot/devices/{device_resp['id']}/deactivate", json={"reason": "device retired"}, headers=headers
    )
    assert deactivate_res.status_code == 200, deactivate_res.text
    assert deactivate_res.json()["is_active"] is False

    double_deactivate_res = client.post(f"/api/v1/iot/devices/{device_resp['id']}/deactivate", json={}, headers=headers)
    assert double_deactivate_res.status_code == 409

    set_tenant_context(raw_db, tenant.tenant_id)
    device = raw_db.get(iot_models.IotDevice, device_resp["id"])
    result = process_reading(raw_db, device=device, metric="temp_c", value=1.0, secret=device_resp["secret"])
    assert result.accepted is False
    assert result.reason == "device_inactive"
    assert device.last_seen_at is None

    reactivate_res = client.post(f"/api/v1/iot/devices/{device_resp['id']}/reactivate", headers=headers)
    assert reactivate_res.status_code == 200, reactivate_res.text
    assert reactivate_res.json()["is_active"] is True

    # The reactivate call above ran on a different DB session (the test
    # client's request), so `raw_db`'s identity map still holds the
    # is_active=False object `.get()` returned earlier - expire it to
    # force a fresh read, the same staleness this phase's `set_tenant_context`
    # docstring already warns about for post-commit reads.
    raw_db.expire_all()
    set_tenant_context(raw_db, tenant.tenant_id)
    device = raw_db.get(iot_models.IotDevice, device_resp["id"])
    resumed_result = process_reading(raw_db, device=device, metric="temp_c", value=3.0, secret=device_resp["secret"])
    assert resumed_result.accepted is True

    double_reactivate_res = client.post(f"/api/v1/iot/devices/{device_resp['id']}/reactivate", headers=headers)
    assert double_reactivate_res.status_code == 409


def test_actuator_stop_command_always_executes_immediately(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="IOTFARM10")
    twin_type = _create_twin_type(client, headers, code="pump10")
    device = _register_device(client, headers, farm["id"], twin_type["id"], device_key="dev-actuator-off")

    res = client.post(f"/api/v1/iot/devices/{device['id']}/commands", json={"command": "off"}, headers=headers)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["command"] == "off"
    assert body["status"] == "executed"

    twin_res = client.get(f"/api/v1/twins/{device['digital_twin_id']}", headers=headers)
    assert twin_res.json()["current_state"]["actuator_status"] == "off"


def test_actuator_start_command_requires_confirmation(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="IOTFARM11")
    twin_type = _create_twin_type(client, headers, code="pump11")
    device = _register_device(client, headers, farm["id"], twin_type["id"], device_key="dev-actuator-on")

    denied_res = client.post(f"/api/v1/iot/devices/{device['id']}/commands", json={"command": "on"}, headers=headers)
    assert denied_res.status_code == 409

    ok_res = client.post(
        f"/api/v1/iot/devices/{device['id']}/commands", json={"command": "on", "confirmed": True}, headers=headers
    )
    assert ok_res.status_code == 201, ok_res.text
    assert ok_res.json()["status"] == "executed"

    twin_res = client.get(f"/api/v1/twins/{device['digital_twin_id']}", headers=headers)
    assert twin_res.json()["current_state"]["actuator_status"] == "on"


def test_actuator_command_validation_and_deactivated_device(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="IOTFARM12")
    twin_type = _create_twin_type(client, headers, code="pump12")
    device = _register_device(client, headers, farm["id"], twin_type["id"], device_key="dev-actuator-bad")

    bad_command_res = client.post(f"/api/v1/iot/devices/{device['id']}/commands", json={"command": "explode"}, headers=headers)
    assert bad_command_res.status_code == 422

    client.post(f"/api/v1/iot/devices/{device['id']}/deactivate", json={}, headers=headers)
    deactivated_res = client.post(f"/api/v1/iot/devices/{device['id']}/commands", json={"command": "off"}, headers=headers)
    assert deactivated_res.status_code == 409


def test_actuator_auto_command_requires_confirmation(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="IOTFARM13")
    twin_type = _create_twin_type(client, headers, code="pump13")
    device = _register_device(client, headers, farm["id"], twin_type["id"], device_key="dev-actuator-auto")

    denied_res = client.post(f"/api/v1/iot/devices/{device['id']}/commands", json={"command": "auto"}, headers=headers)
    assert denied_res.status_code == 409
    ok_res = client.post(
        f"/api/v1/iot/devices/{device['id']}/commands", json={"command": "auto", "confirmed": True}, headers=headers
    )
    assert ok_res.status_code == 201, ok_res.text
    assert ok_res.json()["status"] == "executed"


def test_schedule_command_requires_scheduled_for_and_confirmation_but_does_not_execute_yet(client, tenant):
    """Master-prompt integration, Phase 35: a 'schedule' command still
    requires the same-request confirmation every other actuator-start
    command does, but - unlike 'on'/'auto' - it stays 'proposed' rather
    than executing immediately; `fire_scheduled_commands` is what
    actually executes it once scheduled_for arrives."""
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="IOTFARM14")
    twin_type = _create_twin_type(client, headers, code="pump14")
    device = _register_device(client, headers, farm["id"], twin_type["id"], device_key="dev-actuator-schedule")

    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    missing_scheduled_for_res = client.post(
        f"/api/v1/iot/devices/{device['id']}/commands", json={"command": "schedule", "confirmed": True}, headers=headers
    )
    assert missing_scheduled_for_res.status_code == 422

    denied_res = client.post(
        f"/api/v1/iot/devices/{device['id']}/commands", json={"command": "schedule", "scheduled_for": future}, headers=headers
    )
    assert denied_res.status_code == 409

    ok_res = client.post(
        f"/api/v1/iot/devices/{device['id']}/commands",
        json={"command": "schedule", "scheduled_for": future, "confirmed": True},
        headers=headers,
    )
    assert ok_res.status_code == 201, ok_res.text
    body = ok_res.json()
    assert body["status"] == "proposed"
    assert body["executed_at"] is None

    twin_res = client.get(f"/api/v1/twins/{device['digital_twin_id']}", headers=headers)
    assert "actuator_status" not in twin_res.json()["current_state"]


def test_fire_scheduled_commands_executes_due_actions_and_updates_twin(client, tenant, raw_db):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="IOTFARM15")
    twin_type = _create_twin_type(client, headers, code="pump15")
    device = _register_device(client, headers, farm["id"], twin_type["id"], device_key="dev-actuator-fire")

    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    due_res = client.post(
        f"/api/v1/iot/devices/{device['id']}/commands",
        json={"command": "schedule", "scheduled_for": past, "confirmed": True},
        headers=headers,
    )
    assert due_res.status_code == 201, due_res.text
    due_action_id = due_res.json()["id"]

    not_due_res = client.post(
        f"/api/v1/iot/devices/{device['id']}/commands",
        json={"command": "schedule", "scheduled_for": future, "confirmed": True},
        headers=headers,
    )
    assert not_due_res.status_code == 201, not_due_res.text
    not_due_action_id = not_due_res.json()["id"]

    set_tenant_context(raw_db, tenant.tenant_id)
    fired = fire_scheduled_commands(raw_db, tenant.tenant_id)
    fired_ids = [a.id for a in fired]
    assert due_action_id in fired_ids
    assert not_due_action_id not in fired_ids

    # `fire_scheduled_commands` commits internally, which resets
    # `set_tenant_context`'s transaction-scoped setting - re-set it
    # before further RLS-protected reads on this session.
    set_tenant_context(raw_db, tenant.tenant_id)
    due_action = raw_db.get(ai_models.AgentAction, due_action_id)
    assert due_action.status == "executed"
    not_due_action = raw_db.get(ai_models.AgentAction, not_due_action_id)
    assert not_due_action.status == "proposed"

    twin_res = client.get(f"/api/v1/twins/{device['digital_twin_id']}", headers=headers)
    assert twin_res.json()["current_state"]["actuator_status"] == "schedule"

    # Idempotent: a second sweep doesn't re-fire the already-executed action.
    set_tenant_context(raw_db, tenant.tenant_id)
    second_sweep = fire_scheduled_commands(raw_db, tenant.tenant_id)
    assert due_action_id not in [a.id for a in second_sweep]


def test_cancel_pending_scheduled_command(client, tenant, raw_db):
    """Master-prompt integration, Phase 38 (Phase 35's own deferral: no
    cancel for a pending schedule command)."""
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="IOTFARM16")
    twin_type = _create_twin_type(client, headers, code="pump16")
    device = _register_device(client, headers, farm["id"], twin_type["id"], device_key="dev-actuator-cancel")

    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    cmd_res = client.post(
        f"/api/v1/iot/devices/{device['id']}/commands",
        json={"command": "schedule", "scheduled_for": future, "confirmed": True},
        headers=headers,
    )
    assert cmd_res.status_code == 201, cmd_res.text
    action_id = cmd_res.json()["id"]

    cancel_res = client.post(
        f"/api/v1/iot/devices/{device['id']}/commands/{action_id}/cancel",
        json={"reason": "Plan changed"},
        headers=headers,
    )
    assert cancel_res.status_code == 200, cancel_res.text
    assert cancel_res.json()["status"] == "cancelled"
    assert cancel_res.json()["result"]["cancelled_reason"] == "Plan changed"

    # A cancelled action is never fired by the watcher, even if its
    # scheduled_for time has already passed.
    set_tenant_context(raw_db, tenant.tenant_id)
    action = raw_db.get(ai_models.AgentAction, action_id)
    action.input_context = {**action.input_context, "scheduled_for": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}
    raw_db.commit()
    set_tenant_context(raw_db, tenant.tenant_id)
    fired = fire_scheduled_commands(raw_db, tenant.tenant_id)
    assert action_id not in [a.id for a in fired]

    # Cancelling an already-cancelled (non-"proposed") action is rejected.
    double_cancel_res = client.post(
        f"/api/v1/iot/devices/{device['id']}/commands/{action_id}/cancel", json={}, headers=headers
    )
    assert double_cancel_res.status_code == 409

    # Cancelling an already-executed immediate command is also rejected.
    on_res = client.post(
        f"/api/v1/iot/devices/{device['id']}/commands", json={"command": "on", "confirmed": True}, headers=headers
    )
    assert on_res.status_code == 201, on_res.text
    on_action_id = on_res.json()["id"]
    cancel_executed_res = client.post(
        f"/api/v1/iot/devices/{device['id']}/commands/{on_action_id}/cancel", json={}, headers=headers
    )
    assert cancel_executed_res.status_code == 409
