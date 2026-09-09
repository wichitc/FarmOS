from app.foundation.workflow_engine import _applicable_steps


class _FakeDefinition:
    def __init__(self, steps):
        self.steps = steps


def test_applicable_steps_filters_by_amount_condition():
    definition = _FakeDefinition(
        steps=[
            {"step": 1, "approver_role_code": "warehouse_officer"},
            {"step": 2, "approver_role_code": "finance", "condition": {"amount_gte": 100000}},
        ]
    )
    assert [s["step"] for s in _applicable_steps(definition, {"amount": 500})] == [1]
    assert [s["step"] for s in _applicable_steps(definition, {"amount": 250000})] == [1, 2]


def _headers(client, tenant, email, password):
    res = client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": tenant.tenant_slug, "email": email, "password": password},
    )
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_submit_and_approve_end_to_end(client, tenant):
    admin_headers = {"Authorization": f"Bearer {tenant.admin_token(client)}"}
    roles = {r["code"]: r["id"] for r in client.get("/api/v1/roles", headers=admin_headers).json()}

    submitter_email = f"submitter-{tenant.tenant_slug}@example.com"
    submitter_password = "pw-for-testing-123"
    submitter = client.post(
        "/api/v1/users",
        json={"email": submitter_email, "password": submitter_password, "full_name": "Submitter"},
        headers=admin_headers,
    ).json()
    client.post(
        "/api/v1/role-assignments",
        json={"user_id": submitter["id"], "role_id": roles["warehouse_officer"], "scope_type": "tenant"},
        headers=admin_headers,
    )

    approver_email = f"approver-{tenant.tenant_slug}@example.com"
    approver_password = "pw-for-testing-123"
    approver = client.post(
        "/api/v1/users",
        json={"email": approver_email, "password": approver_password, "full_name": "Approver"},
        headers=admin_headers,
    ).json()
    client.post(
        "/api/v1/role-assignments",
        json={"user_id": approver["id"], "role_id": roles["farm_manager"], "scope_type": "tenant"},
        headers=admin_headers,
    )

    definition_res = client.post(
        "/api/v1/workflows/definitions",
        json={
            "entity_type": "purchase_request",
            "name": "PR Approval",
            "steps": [{"step": 1, "approver_role_code": "farm_manager"}],
        },
        headers=admin_headers,
    )
    assert definition_res.status_code == 201
    definition_id = definition_res.json()["id"]

    submitter_headers = _headers(client, tenant, submitter_email, submitter_password)
    submit_res = client.post(
        "/api/v1/workflows/instances",
        json={
            "workflow_definition_id": definition_id,
            "entity_type": "purchase_request",
            "entity_id": "PR-1001",
            "context": {"amount": 5000},
        },
        headers=submitter_headers,
    )
    assert submit_res.status_code == 201
    instance = submit_res.json()
    assert instance["status"] == "submitted"

    wrong_approve = client.post(
        f"/api/v1/workflows/instances/{instance['id']}/approve",
        json={},
        headers=submitter_headers,
    )
    assert wrong_approve.status_code == 403

    approver_headers = _headers(client, tenant, approver_email, approver_password)
    approve_res = client.post(
        f"/api/v1/workflows/instances/{instance['id']}/approve",
        json={"reason": "looks good"},
        headers=approver_headers,
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "approved"

    notifications = client.get("/api/v1/notifications", headers=submitter_headers).json()
    assert any(n["related_entity_id"] == instance["id"] for n in notifications)

    audit_res = client.get(
        "/api/v1/audit",
        params={"entity_type": "workflow_instance", "entity_id": instance["id"]},
        headers=admin_headers,
    ).json()
    actions = [a["action"] for a in audit_res]
    assert "workflow.submit" in actions
    assert "workflow.approve" in actions
