def test_login_success_and_me(client, tenant):
    token = tenant.admin_token(client)
    res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.json()
    assert body["email"] == tenant.admin_email
    assert body["tenant_id"] == tenant.tenant_id


def test_login_wrong_password(client, tenant):
    res = client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": tenant.tenant_slug, "email": tenant.admin_email, "password": "nope"},
    )
    assert res.status_code == 401


def test_login_wrong_tenant_slug(client, tenant):
    res = client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": "does-not-exist", "email": tenant.admin_email, "password": tenant.admin_password},
    )
    assert res.status_code == 401


def test_me_requires_token(client):
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 401


def test_refresh_flow(client, tenant):
    login_res = client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": tenant.tenant_slug, "email": tenant.admin_email, "password": tenant.admin_password},
    )
    refresh_token = login_res.json()["refresh_token"]

    refresh_res = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_res.status_code == 200
    new_access = refresh_res.json()["access_token"]

    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me_res.status_code == 200


def test_access_token_rejected_by_refresh_endpoint(client, tenant):
    access_token = tenant.admin_token(client)
    res = client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
    assert res.status_code == 401
