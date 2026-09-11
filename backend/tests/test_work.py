from .conftest import unique_slug


def _create_farm(client, headers, code="WORKFARM"):
    res = client.post("/api/v1/farm/farms", json={"code": code, "name": "Work Farm"}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _create_field_worker(client, admin_headers, tenant, farm_id, email_prefix="worker"):
    email = f"{email_prefix}-{unique_slug('u')}@example.com"
    password = "pw-for-testing-123"
    user = client.post(
        "/api/v1/users", json={"email": email, "password": password, "full_name": "Field Worker"}, headers=admin_headers
    ).json()
    roles = {r["code"]: r["id"] for r in client.get("/api/v1/roles", headers=admin_headers).json()}
    client.post(
        "/api/v1/role-assignments",
        json={"user_id": user["id"], "role_id": roles["field_worker"], "scope_type": "farm", "scope_id": farm_id},
        headers=admin_headers,
    )
    login_res = client.post("/api/v1/auth/login", json={"tenant_slug": tenant.tenant_slug, "email": email, "password": password})
    assert login_res.status_code == 200, login_res.text
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}
    return user, headers


def test_work_task_full_lifecycle(client, tenant):
    admin_headers = tenant.auth_headers(client)
    farm = _create_farm(client, admin_headers, code="WORKFARM1")
    worker, worker_headers = _create_field_worker(client, admin_headers, tenant, farm["id"])

    create_res = client.post(
        f"/api/v1/work/farms/{farm['id']}/tasks",
        json={"work_type": "pruning", "title": "Prune row 3", "description": "Overgrown canopy"},
        headers=admin_headers,
    )
    assert create_res.status_code == 201, create_res.text
    task = create_res.json()
    assert task["status"] == "requested"

    plan_res = client.post(f"/api/v1/work/tasks/{task['id']}/plan", json={}, headers=admin_headers)
    assert plan_res.status_code == 200, plan_res.text
    assert plan_res.json()["status"] == "planned"

    assign_res = client.post(
        f"/api/v1/work/tasks/{task['id']}/assign", json={"assigned_to": worker["id"]}, headers=admin_headers
    )
    assert assign_res.status_code == 200, assign_res.text
    assert assign_res.json()["status"] == "assigned"

    # Only the assignee (or a manager) can accept.
    accept_res = client.post(f"/api/v1/work/tasks/{task['id']}/accept", json={}, headers=worker_headers)
    assert accept_res.status_code == 200, accept_res.text
    assert accept_res.json()["status"] == "accepted"

    start_res = client.post(f"/api/v1/work/tasks/{task['id']}/start", headers=worker_headers)
    assert start_res.status_code == 200, start_res.text
    assert start_res.json()["status"] == "in_progress"

    complete_res = client.post(
        f"/api/v1/work/tasks/{task['id']}/complete",
        json={"evidence": {"photos": ["s3://evidence/1.jpg"], "labor_hours": 2.5}},
        headers=worker_headers,
    )
    assert complete_res.status_code == 200, complete_res.text
    completed = complete_res.json()
    assert completed["status"] == "completed"
    assert completed["evidence"]["labor_hours"] == 2.5

    review_res = client.post(
        f"/api/v1/work/tasks/{task['id']}/review", json={"decision": "close", "notes": "Looks good"}, headers=admin_headers
    )
    assert review_res.status_code == 200, review_res.text
    assert review_res.json()["status"] == "closed"


def test_review_send_back_reopens_for_rework(client, tenant):
    admin_headers = tenant.auth_headers(client)
    farm = _create_farm(client, admin_headers, code="WORKFARM2")
    worker, worker_headers = _create_field_worker(client, admin_headers, tenant, farm["id"])

    task = client.post(
        f"/api/v1/work/farms/{farm['id']}/tasks", json={"work_type": "spraying", "title": "Spray block A"}, headers=admin_headers
    ).json()
    client.post(f"/api/v1/work/tasks/{task['id']}/plan", json={}, headers=admin_headers)
    client.post(f"/api/v1/work/tasks/{task['id']}/assign", json={"assigned_to": worker["id"]}, headers=admin_headers)
    client.post(f"/api/v1/work/tasks/{task['id']}/accept", json={}, headers=worker_headers)
    client.post(f"/api/v1/work/tasks/{task['id']}/start", headers=worker_headers)
    client.post(f"/api/v1/work/tasks/{task['id']}/complete", json={"evidence": {}}, headers=worker_headers)

    send_back_res = client.post(
        f"/api/v1/work/tasks/{task['id']}/review", json={"decision": "send_back", "notes": "Missed a section"}, headers=admin_headers
    )
    assert send_back_res.status_code == 200, send_back_res.text
    assert send_back_res.json()["status"] == "in_progress"

    complete_again_res = client.post(
        f"/api/v1/work/tasks/{task['id']}/complete", json={"evidence": {"photos": ["done.jpg"]}}, headers=worker_headers
    )
    assert complete_again_res.status_code == 200, complete_again_res.text
    assert complete_again_res.json()["status"] == "completed"


def test_reject_assignment_is_terminal(client, tenant):
    admin_headers = tenant.auth_headers(client)
    farm = _create_farm(client, admin_headers, code="WORKFARM3")
    worker, worker_headers = _create_field_worker(client, admin_headers, tenant, farm["id"])

    task = client.post(
        f"/api/v1/work/farms/{farm['id']}/tasks", json={"work_type": "mowing", "title": "Mow zone 1"}, headers=admin_headers
    ).json()
    client.post(f"/api/v1/work/tasks/{task['id']}/plan", json={}, headers=admin_headers)
    client.post(f"/api/v1/work/tasks/{task['id']}/assign", json={"assigned_to": worker["id"]}, headers=admin_headers)

    reject_res = client.post(
        f"/api/v1/work/tasks/{task['id']}/reject", json={"reason": "Not available"}, headers=worker_headers
    )
    assert reject_res.status_code == 200, reject_res.text
    assert reject_res.json()["status"] == "rejected"

    start_res = client.post(f"/api/v1/work/tasks/{task['id']}/start", headers=worker_headers)
    assert start_res.status_code == 409


def test_only_assignee_or_manager_can_accept(client, tenant):
    admin_headers = tenant.auth_headers(client)
    farm = _create_farm(client, admin_headers, code="WORKFARM4")
    assignee, _assignee_headers = _create_field_worker(client, admin_headers, tenant, farm["id"], email_prefix="assignee")
    other_worker, other_headers = _create_field_worker(client, admin_headers, tenant, farm["id"], email_prefix="other")

    task = client.post(
        f"/api/v1/work/farms/{farm['id']}/tasks", json={"work_type": "cleaning", "title": "Clean packhouse"}, headers=admin_headers
    ).json()
    client.post(f"/api/v1/work/tasks/{task['id']}/plan", json={}, headers=admin_headers)
    client.post(f"/api/v1/work/tasks/{task['id']}/assign", json={"assigned_to": assignee["id"]}, headers=admin_headers)

    denied_res = client.post(f"/api/v1/work/tasks/{task['id']}/accept", json={}, headers=other_headers)
    assert denied_res.status_code == 403

    # A manager (holds work.task.manage) may act on the worker's behalf.
    manager_accept_res = client.post(f"/api/v1/work/tasks/{task['id']}/accept", json={}, headers=admin_headers)
    assert manager_accept_res.status_code == 200, manager_accept_res.text


def test_cannot_assign_before_planned(client, tenant):
    admin_headers = tenant.auth_headers(client)
    farm = _create_farm(client, admin_headers, code="WORKFARM5")
    worker, _ = _create_field_worker(client, admin_headers, tenant, farm["id"])

    task = client.post(
        f"/api/v1/work/farms/{farm['id']}/tasks", json={"work_type": "harvesting", "title": "Pick ripe fruit"}, headers=admin_headers
    ).json()

    assign_res = client.post(
        f"/api/v1/work/tasks/{task['id']}/assign", json={"assigned_to": worker["id"]}, headers=admin_headers
    )
    assert assign_res.status_code == 409


def test_cancel_task(client, tenant):
    admin_headers = tenant.auth_headers(client)
    farm = _create_farm(client, admin_headers, code="WORKFARM6")

    task = client.post(
        f"/api/v1/work/farms/{farm['id']}/tasks", json={"work_type": "disease_inspection", "title": "Inspect block B"}, headers=admin_headers
    ).json()
    cancel_res = client.post(f"/api/v1/work/tasks/{task['id']}/cancel", json={"reason": "No longer needed"}, headers=admin_headers)
    assert cancel_res.status_code == 200, cancel_res.text
    assert cancel_res.json()["status"] == "cancelled"

    plan_after_cancel_res = client.post(f"/api/v1/work/tasks/{task['id']}/plan", json={}, headers=admin_headers)
    assert plan_after_cancel_res.status_code == 409


def test_work_task_farm_scoped_abac(client, tenant):
    admin_headers = tenant.auth_headers(client)
    farm_a = client.post("/api/v1/farm/farms", json={"code": "WKA", "name": "Work Farm A"}, headers=admin_headers).json()
    farm_b = client.post("/api/v1/farm/farms", json={"code": "WKB", "name": "Work Farm B"}, headers=admin_headers).json()

    task_a = client.post(
        f"/api/v1/work/farms/{farm_a['id']}/tasks", json={"work_type": "irrigation", "title": "Irrigate A"}, headers=admin_headers
    ).json()
    task_b = client.post(
        f"/api/v1/work/farms/{farm_b['id']}/tasks", json={"work_type": "irrigation", "title": "Irrigate B"}, headers=admin_headers
    ).json()

    email = f"workmgr-{unique_slug('u')}@example.com"
    password = "pw-for-testing-123"
    user = client.post(
        "/api/v1/users", json={"email": email, "password": password, "full_name": "Work Manager"}, headers=admin_headers
    ).json()
    roles = {r["code"]: r["id"] for r in client.get("/api/v1/roles", headers=admin_headers).json()}
    client.post(
        "/api/v1/role-assignments",
        json={"user_id": user["id"], "role_id": roles["farm_manager"], "scope_type": "farm", "scope_id": farm_a["id"]},
        headers=admin_headers,
    )

    login_res = client.post("/api/v1/auth/login", json={"tenant_slug": tenant.tenant_slug, "email": email, "password": password})
    manager_headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    ok_res = client.get(f"/api/v1/work/tasks/{task_a['id']}", headers=manager_headers)
    assert ok_res.status_code == 200

    denied_res = client.get(f"/api/v1/work/tasks/{task_b['id']}", headers=manager_headers)
    assert denied_res.status_code == 403
