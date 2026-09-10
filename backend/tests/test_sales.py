from .conftest import unique_slug


def _create_farm(client, headers, code="SALESFARM"):
    res = client.post("/api/v1/farm/farms", json={"code": code, "name": "Sales Farm"}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _create_customer(client, headers, code="cust-1"):
    res = client.post("/api/v1/sales/customers", json={"code": code, "name": "Fresh Fruit Co"}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def test_customer_crud(client, tenant):
    headers = tenant.auth_headers(client)
    customer = _create_customer(client, headers, code=f"cust-{tenant.tenant_slug}")
    list_res = client.get("/api/v1/sales/customers", headers=headers)
    assert customer["id"] in [c["id"] for c in list_res.json()]


def test_order_status_transition_guards(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="SALESFARM1")
    customer = _create_customer(client, headers, code=f"cust1-{tenant.tenant_slug}")

    order = client.post(
        "/api/v1/sales/orders",
        json={"customer_id": customer["id"], "farm_id": farm["id"], "quantity_kg": 100, "unit_price": 50},
        headers=headers,
    ).json()

    # Can't deliver before confirming.
    deliver_too_early = client.post(f"/api/v1/sales/orders/{order['id']}/deliver", headers=headers)
    assert deliver_too_early.status_code == 409

    confirm_res = client.post(f"/api/v1/sales/orders/{order['id']}/confirm", headers=headers)
    assert confirm_res.status_code == 200
    assert confirm_res.json()["status"] == "confirmed"

    # Can't invoice before delivering.
    invoice_too_early = client.post(f"/api/v1/sales/orders/{order['id']}/invoices", json={}, headers=headers)
    assert invoice_too_early.status_code == 409

    deliver_res = client.post(f"/api/v1/sales/orders/{order['id']}/deliver", headers=headers)
    assert deliver_res.status_code == 200
    assert deliver_res.json()["status"] == "delivered"


def test_full_order_to_payment_posts_revenue_to_ledger(client, tenant):
    headers = tenant.auth_headers(client)
    farm = _create_farm(client, headers, code="SALESFARM2")
    customer = _create_customer(client, headers, code=f"cust2-{tenant.tenant_slug}")

    order = client.post(
        "/api/v1/sales/orders",
        json={"customer_id": customer["id"], "farm_id": farm["id"], "quantity_kg": 200, "unit_price": 60},
        headers=headers,
    ).json()
    client.post(f"/api/v1/sales/orders/{order['id']}/confirm", headers=headers)
    client.post(f"/api/v1/sales/orders/{order['id']}/deliver", headers=headers)

    invoice_res = client.post(f"/api/v1/sales/orders/{order['id']}/invoices", json={}, headers=headers)
    assert invoice_res.status_code == 201, invoice_res.text
    invoice = invoice_res.json()
    assert invoice["amount"] == 200 * 60

    order_after_invoice = client.get(f"/api/v1/sales/orders/{order['id']}", headers=headers).json()
    assert order_after_invoice["status"] == "invoiced"

    # Partial payment: not fully paid, no ledger posting yet.
    partial_res = client.post(
        f"/api/v1/sales/invoices/{invoice['id']}/payments", json={"amount": 5000, "method": "bank_transfer"}, headers=headers
    )
    assert partial_res.status_code == 201, partial_res.text
    partial_invoice = client.get(f"/api/v1/sales/invoices/{invoice['id']}", headers=headers).json()
    assert partial_invoice["is_paid"] is False

    ledger_before = client.get(
        "/api/v1/accounting/ledger-entries", params={"farm_id": farm["id"], "direction": "revenue"}, headers=headers
    ).json()
    assert len(ledger_before) == 0

    # Final payment completes it.
    final_res = client.post(
        f"/api/v1/sales/invoices/{invoice['id']}/payments", json={"amount": 7000, "method": "bank_transfer"}, headers=headers
    )
    assert final_res.status_code == 201, final_res.text
    final_invoice = client.get(f"/api/v1/sales/invoices/{invoice['id']}", headers=headers).json()
    assert final_invoice["is_paid"] is True

    ledger_after = client.get(
        "/api/v1/accounting/ledger-entries", params={"farm_id": farm["id"], "direction": "revenue"}, headers=headers
    ).json()
    assert len(ledger_after) == 1
    assert ledger_after[0]["amount"] == invoice["amount"]
    assert ledger_after[0]["source_type"] == "sales_invoice"
    assert ledger_after[0]["source_id"] == invoice["id"]

    # Already-paid invoice rejects further payment.
    over_pay_res = client.post(
        f"/api/v1/sales/invoices/{invoice['id']}/payments", json={"amount": 1}, headers=headers
    )
    assert over_pay_res.status_code == 409


def test_sales_order_farm_scoped_abac(client, tenant):
    admin_headers = tenant.auth_headers(client)
    farm_a = client.post("/api/v1/farm/farms", json={"code": "SLSA", "name": "Sales Farm A"}, headers=admin_headers).json()
    farm_b = client.post("/api/v1/farm/farms", json={"code": "SLSB", "name": "Sales Farm B"}, headers=admin_headers).json()
    customer = _create_customer(client, admin_headers, code=f"custabac-{tenant.tenant_slug}")

    order_a = client.post(
        "/api/v1/sales/orders",
        json={"customer_id": customer["id"], "farm_id": farm_a["id"], "quantity_kg": 10, "unit_price": 1},
        headers=admin_headers,
    ).json()
    order_b = client.post(
        "/api/v1/sales/orders",
        json={"customer_id": customer["id"], "farm_id": farm_b["id"], "quantity_kg": 10, "unit_price": 1},
        headers=admin_headers,
    ).json()

    email = f"salesmgr-{unique_slug('u')}@example.com"
    password = "pw-for-testing-123"
    user = client.post(
        "/api/v1/users", json={"email": email, "password": password, "full_name": "Sales Manager"}, headers=admin_headers
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

    ok_res = client.get(f"/api/v1/sales/orders/{order_a['id']}", headers=manager_headers)
    assert ok_res.status_code == 200

    denied_res = client.get(f"/api/v1/sales/orders/{order_b['id']}", headers=manager_headers)
    assert denied_res.status_code == 403
