from .conftest import unique_slug


def _create_farm(client, headers, code="AIFARM"):
    res = client.post("/api/v1/farm/farms", json={"code": code, "name": "AI Farm"}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _create_asset_twin_type(client, headers, code="pump-type"):
    res = client.post("/api/v1/twins/types", json={"code": code, "name": "Pump", "category": "asset"}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _register_asset(client, headers, twin_type_id, display_code="PUMP-1", **extra):
    payload = {"twin_type_id": twin_type_id, "display_code": display_code, **extra}
    res = client.post("/api/v1/assets", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _propose(client, headers, **overrides):
    payload = {
        "agent_code": "test_agent",
        "action_type": "notify_operator",
        "requested_level": "L1",
        "entity_type": "farm",
        "entity_id": "00000000-0000-0000-0000-000000000000",
        "rationale": "Observed a condition worth flagging.",
        "input_context": {"observed": True},
    }
    payload.update(overrides)
    res = client.post("/api/v1/ai/agent-actions", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def test_model_registry_seeded_on_provisioning(client, tenant):
    headers = tenant.auth_headers(client)
    models = client.get("/api/v1/ai/models", headers=headers).json()
    codes = {m["code"] for m in models}
    assert "health_score_rule_engine" in codes
    assert "yield_estimation_rule_engine" in codes

    health_model = next(m for m in models if m["code"] == "health_score_rule_engine")
    versions = client.get(f"/api/v1/ai/models/{health_model['id']}/versions", headers=headers).json()
    assert len(versions) == 1
    assert versions[0]["status"] == "active"
    assert versions[0]["implementation_ref"] == "app.health.compute_health_score"


def test_health_assessment_records_prediction(client, tenant):
    headers = tenant.auth_headers(client)
    twin_type = _create_asset_twin_type(client, headers, code=f"pump-{tenant.tenant_slug}")
    asset = _register_asset(client, headers, twin_type["id"], initial_state={"temperature_c": 95, "vibration_mm_s": 1.0, "status": "running"})

    assess_res = client.post(f"/api/v1/assets/{asset['id']}/assessments", headers=headers)
    assert assess_res.status_code == 201, assess_res.text

    predictions = client.get(
        "/api/v1/ai/predictions", params={"entity_type": "digital_twin", "entity_id": asset["id"]}, headers=headers
    ).json()
    assert len(predictions) == 1
    assert predictions[0]["output"]["band"] in ("healthy", "warning", "critical")

    feedback_res = client.post(
        f"/api/v1/ai/predictions/{predictions[0]['id']}/feedback",
        json={"status": "accepted"},
        headers=headers,
    )
    assert feedback_res.status_code == 201, feedback_res.text


def test_yield_forecast_records_prediction(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="AIFARM1")
    forecast_res = client.post(
        f"/api/v1/harvest/farms/{farm['id']}/yield-forecasts",
        json={"tree_count": 5, "avg_fruit_count_per_tree": 15, "avg_fruit_weight_kg": 2.5},
        headers=headers,
    )
    assert forecast_res.status_code == 201, forecast_res.text
    forecast = forecast_res.json()

    predictions = client.get(
        "/api/v1/ai/predictions", params={"entity_type": "yield_forecast", "entity_id": forecast["id"]}, headers=headers
    ).json()
    assert len(predictions) == 1
    assert predictions[0]["confidence"] == forecast["confidence"]


def test_l1_action_executes_immediately_without_confirmation(client, tenant):
    headers = tenant.auth_headers(client)
    action = _propose(client, headers, requested_level="L1")
    assert action["level"] == "L1"
    assert action["status"] == "proposed"

    exec_res = client.post(f"/api/v1/ai/agent-actions/{action['id']}/execute", json={}, headers=headers)
    assert exec_res.status_code == 200, exec_res.text
    assert exec_res.json()["status"] == "executed"


def test_l2_action_requires_explicit_confirmation(client, tenant):
    headers = tenant.auth_headers(client)
    action = _propose(client, headers, action_type="adjust_camera_angle", requested_level="L2")
    assert action["level"] == "L2"

    denied = client.post(f"/api/v1/ai/agent-actions/{action['id']}/execute", json={"confirmed": False}, headers=headers)
    assert denied.status_code == 409

    approved = client.post(
        f"/api/v1/ai/agent-actions/{action['id']}/execute", json={"confirmed": True, "result": {"ok": True}}, headers=headers
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "executed"
    assert approved.json()["result"] == {"ok": True}


def test_sensitive_action_type_is_capped_at_l2_without_policy_grant(client, tenant):
    """FR-AGENT-002: pump activation must never execute above L2 without an
    explicit auditable policy grant - requesting L4 with no grant on file
    is silently downgraded to L2 by the gateway, not rejected outright."""
    headers = tenant.auth_headers(client)
    action = _propose(client, headers, action_type="pump_activation", requested_level="L4")
    assert action["level"] == "L2"
    assert action["policy_grant_id"] is None

    exec_res = client.post(
        f"/api/v1/ai/agent-actions/{action['id']}/execute", json={"confirmed": True}, headers=headers
    )
    assert exec_res.status_code == 200, exec_res.text


def test_sensitive_action_with_active_policy_grant_reaches_l4(client, tenant):
    headers = tenant.auth_headers(client)
    grant_res = client.post(
        "/api/v1/ai/agent-policy-grants", json={"action_type": "pump_activation", "notes": "Pilot autonomy trial"}, headers=headers
    )
    assert grant_res.status_code == 201, grant_res.text
    grant = grant_res.json()

    action = _propose(client, headers, action_type="pump_activation", requested_level="L4")
    assert action["level"] == "L4"
    assert action["policy_grant_id"] == grant["id"]

    exec_res = client.post(f"/api/v1/ai/agent-actions/{action['id']}/execute", json={}, headers=headers)
    assert exec_res.status_code == 200, exec_res.text
    assert exec_res.json()["status"] == "executed"

    revoke_res = client.post(f"/api/v1/ai/agent-policy-grants/{grant['id']}/revoke", headers=headers)
    assert revoke_res.status_code == 200
    assert revoke_res.json()["is_active"] is False


def test_l3_action_requires_workflow_approval_before_executing(client, tenant):
    headers = tenant.auth_headers(client)
    action = _propose(client, headers, action_type="generate_report", requested_level="L3")
    assert action["level"] == "L3"

    early_exec = client.post(f"/api/v1/ai/agent-actions/{action['id']}/execute", json={}, headers=headers)
    assert early_exec.status_code == 409

    submit_res = client.post(f"/api/v1/ai/agent-actions/{action['id']}/submit", headers=headers)
    assert submit_res.status_code == 200, submit_res.text
    assert submit_res.json()["status"] == "pending_approval"

    approve_res = client.post(f"/api/v1/ai/agent-actions/{action['id']}/approve", json={}, headers=headers)
    assert approve_res.status_code == 200, approve_res.text
    assert approve_res.json()["status"] == "approved"

    exec_res = client.post(f"/api/v1/ai/agent-actions/{action['id']}/execute", json={}, headers=headers)
    assert exec_res.status_code == 200, exec_res.text
    assert exec_res.json()["status"] == "executed"


def test_l3_action_rejected_stops_execution(client, tenant):
    headers = tenant.auth_headers(client)
    action = _propose(client, headers, action_type="generate_report_2", requested_level="L3")
    client.post(f"/api/v1/ai/agent-actions/{action['id']}/submit", headers=headers)

    reject_res = client.post(f"/api/v1/ai/agent-actions/{action['id']}/reject", json={"reason": "not needed"}, headers=headers)
    assert reject_res.status_code == 200
    assert reject_res.json()["status"] == "rejected"

    exec_res = client.post(f"/api/v1/ai/agent-actions/{action['id']}/execute", json={}, headers=headers)
    assert exec_res.status_code == 409


def test_agent_action_farm_scoped_abac(client, tenant):
    admin_headers = tenant.auth_headers(client)
    farm_a = client.post("/api/v1/farm/farms", json={"code": "AIA", "name": "AI Farm A"}, headers=admin_headers).json()
    farm_b = client.post("/api/v1/farm/farms", json={"code": "AIB", "name": "AI Farm B"}, headers=admin_headers).json()

    action_a = _propose(client, admin_headers, farm_id=farm_a["id"])
    action_b = _propose(client, admin_headers, farm_id=farm_b["id"])

    email = f"aimgr-{unique_slug('u')}@example.com"
    password = "pw-for-testing-123"
    user = client.post(
        "/api/v1/users", json={"email": email, "password": password, "full_name": "AI Manager"}, headers=admin_headers
    ).json()
    roles = {r["code"]: r["id"] for r in client.get("/api/v1/roles", headers=admin_headers).json()}
    client.post(
        "/api/v1/role-assignments",
        json={"user_id": user["id"], "role_id": roles["farm_manager"], "scope_type": "farm", "scope_id": farm_a["id"]},
        headers=admin_headers,
    )

    login_res = client.post("/api/v1/auth/login", json={"tenant_slug": tenant.tenant_slug, "email": email, "password": password})
    manager_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    ok_res = client.get(f"/api/v1/ai/agent-actions/{action_a['id']}", headers=manager_headers)
    assert ok_res.status_code == 200

    denied_res = client.get(f"/api/v1/ai/agent-actions/{action_b['id']}", headers=manager_headers)
    assert denied_res.status_code == 403


def test_copilot_answers_with_citations_grounded_in_real_data(client, tenant):
    headers = tenant.auth_headers(client)

    no_alerts = client.post("/api/v1/ai/copilot/ask", json={"question": "Any open alerts?"}, headers=headers)
    assert no_alerts.status_code == 200, no_alerts.text
    assert "no open alerts" in no_alerts.json()["answer"].lower()
    assert no_alerts.json()["citations"] == []

    unsupported = client.post("/api/v1/ai/copilot/ask", json={"question": "What is the meaning of life?"}, headers=headers)
    assert unsupported.status_code == 200
    assert "can currently only answer" in unsupported.json()["answer"].lower()

    conv_id = no_alerts.json()["conversation_id"]
    follow_up = client.post(
        "/api/v1/ai/copilot/ask", json={"question": "Any low stock items?", "conversation_id": conv_id}, headers=headers
    )
    assert follow_up.status_code == 200, follow_up.text
    assert follow_up.json()["conversation_id"] == conv_id
