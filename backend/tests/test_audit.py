def test_crop_create_is_audited(client, tenant):
    headers = {"Authorization": f"Bearer {tenant.admin_token(client)}"}
    create_res = client.post(
        "/api/v1/master-data/crops",
        json={"code": "rambutan", "name_en": "Rambutan", "name_th": "เงาะ"},
        headers=headers,
    )
    assert create_res.status_code == 201
    crop_id = create_res.json()["id"]

    audit_res = client.get(
        "/api/v1/audit",
        params={"entity_type": "crop", "entity_id": crop_id},
        headers=headers,
    )
    assert audit_res.status_code == 200
    entries = audit_res.json()
    assert len(entries) == 1
    assert entries[0]["action"] == "crop.create"
    assert entries[0]["new_values"]["code"] == "rambutan"
    assert entries[0]["actor_user_id"] == tenant.admin_user_id


def test_audit_view_requires_permission(client, tenant):
    headers = {"Authorization": f"Bearer {tenant.admin_token(client)}"}
    user_res = client.post(
        "/api/v1/users",
        json={"email": f"norole-{tenant.tenant_slug}@example.com", "password": "pw-for-testing-123", "full_name": "No Role"},
        headers=headers,
    )
    login_res = client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": tenant.tenant_slug,
            "email": user_res.json()["email"],
            "password": "pw-for-testing-123",
        },
    )
    token = login_res.json()["access_token"]

    res = client.get("/api/v1/audit", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
