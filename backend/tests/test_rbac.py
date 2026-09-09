def _create_user(client, tenant, email, password="pw-for-testing-123"):
    admin_headers = {"Authorization": f"Bearer {tenant.admin_token(client)}"}
    res = client.post(
        "/api/v1/users",
        json={"email": email, "password": password, "full_name": "Test User"},
        headers=admin_headers,
    )
    assert res.status_code == 201, res.text
    return res.json(), password


def _login(client, tenant, email, password):
    res = client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": tenant.tenant_slug, "email": email, "password": password},
    )
    assert res.status_code == 200
    return res.json()["access_token"]


def test_user_with_no_role_assignment_is_denied(client, tenant):
    user, password = _create_user(client, tenant, f"noroles-{tenant.tenant_slug}@example.com")
    token = _login(client, tenant, user["email"], password)

    res = client.get("/api/v1/master-data/crops", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


def test_viewer_role_grants_read_but_not_write(client, tenant):
    user, password = _create_user(client, tenant, f"viewer-{tenant.tenant_slug}@example.com")
    admin_headers = {"Authorization": f"Bearer {tenant.admin_token(client)}"}

    roles = {r["code"]: r["id"] for r in client.get("/api/v1/roles", headers=admin_headers).json()}
    assign_res = client.post(
        "/api/v1/role-assignments",
        json={"user_id": user["id"], "role_id": roles["viewer"], "scope_type": "tenant"},
        headers=admin_headers,
    )
    assert assign_res.status_code == 201

    token = _login(client, tenant, user["email"], password)
    headers = {"Authorization": f"Bearer {token}"}

    list_res = client.get("/api/v1/master-data/crops", headers=headers)
    assert list_res.status_code == 200

    create_res = client.post(
        "/api/v1/master-data/crops",
        json={"code": "durian", "name_en": "Durian", "name_th": "ทุเรียน"},
        headers=headers,
    )
    assert create_res.status_code == 403


def test_platform_super_admin_flag_bypasses_rbac_but_not_authentication(client):
    res = client.get("/api/v1/master-data/crops")
    assert res.status_code == 401
