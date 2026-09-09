from tests.conftest import provision_test_tenant


def test_crop_created_in_tenant_a_is_invisible_to_tenant_b(client, tenant, raw_db):
    tenant_b = provision_test_tenant(raw_db, "beta")

    a_headers = {"Authorization": f"Bearer {tenant.admin_token(client)}"}
    create_res = client.post(
        "/api/v1/master-data/crops",
        json={"code": "mangosteen", "name_en": "Mangosteen", "name_th": "มังคุด"},
        headers=a_headers,
    )
    assert create_res.status_code == 201
    crop_id = create_res.json()["id"]

    b_headers = {"Authorization": f"Bearer {tenant_b.admin_token(client)}"}
    b_crops = client.get("/api/v1/master-data/crops", headers=b_headers).json()
    assert crop_id not in [c["id"] for c in b_crops]

    b_audit = client.get(
        "/api/v1/audit", params={"entity_type": "crop", "entity_id": crop_id}, headers=b_headers
    ).json()
    assert b_audit == []


def test_users_are_isolated_per_tenant(client, tenant, raw_db):
    tenant_b = provision_test_tenant(raw_db, "beta")

    a_headers = {"Authorization": f"Bearer {tenant.admin_token(client)}"}
    a_users = {u["email"] for u in client.get("/api/v1/users", headers=a_headers).json()}
    assert tenant_b.admin_email not in a_users

    b_headers = {"Authorization": f"Bearer {tenant_b.admin_token(client)}"}
    b_users = {u["email"] for u in client.get("/api/v1/users", headers=b_headers).json()}
    assert tenant.admin_email not in b_users
