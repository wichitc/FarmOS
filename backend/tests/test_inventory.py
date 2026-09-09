from .conftest import unique_slug


def _create_item(client, headers, code="npk-fert", min_qty=None):
    payload = {"code": code, "name": "NPK Fertilizer", "category": "fertilizer", "uom": "kg"}
    if min_qty is not None:
        payload["min_qty"] = min_qty
    res = client.post("/api/v1/inventory/items", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _create_warehouse(client, headers, code="WH1"):
    res = client.post("/api/v1/inventory/warehouses", json={"code": code, "name": "Main Store"}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _create_vendor(client, headers, code="vendor-1"):
    res = client.post("/api/v1/inventory/vendors", json={"code": code, "name": "AgroSupply Co"}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def test_item_and_warehouse_crud(client, tenant):
    headers = tenant.auth_headers(client)
    item = _create_item(client, headers, code=f"npk-{tenant.tenant_slug}")
    warehouse = _create_warehouse(client, headers, code=f"WH-{tenant.tenant_slug}")

    items_res = client.get("/api/v1/inventory/items", headers=headers)
    assert item["id"] in [i["id"] for i in items_res.json()]

    warehouses_res = client.get("/api/v1/inventory/warehouses", headers=headers)
    assert warehouse["id"] in [w["id"] for w in warehouses_res.json()]


def test_receive_stock_creates_lot_and_movement(client, tenant):
    headers = tenant.auth_headers(client)
    item = _create_item(client, headers, code=f"npk1-{tenant.tenant_slug}")
    warehouse = _create_warehouse(client, headers, code=f"WH1-{tenant.tenant_slug}")

    receive_res = client.post(
        f"/api/v1/inventory/warehouses/{warehouse['id']}/receive",
        json={"item_id": item["id"], "lot_code": "LOT-A", "quantity": 100, "unit_cost": 25.0},
        headers=headers,
    )
    assert receive_res.status_code == 201, receive_res.text
    lot = receive_res.json()
    assert lot["quantity"] == 100

    movements_res = client.get(f"/api/v1/inventory/lots/{lot['id']}/movements", headers=headers)
    assert len(movements_res.json()) == 1
    assert movements_res.json()[0]["movement_type"] == "receipt"


def test_stock_issue_decrements_and_blocks_over_issue(client, tenant):
    headers = tenant.auth_headers(client)
    item = _create_item(client, headers, code=f"npk2-{tenant.tenant_slug}")
    warehouse = _create_warehouse(client, headers, code=f"WH2-{tenant.tenant_slug}")
    lot = client.post(
        f"/api/v1/inventory/warehouses/{warehouse['id']}/receive",
        json={"item_id": item["id"], "lot_code": "LOT-B", "quantity": 50},
        headers=headers,
    ).json()

    issue_res = client.post(
        f"/api/v1/inventory/lots/{lot['id']}/movements",
        json={"quantity_delta": 20, "movement_type": "issue", "reference_type": "plot", "reference_id": "some-plot-id"},
        headers=headers,
    )
    assert issue_res.status_code == 201, issue_res.text
    assert issue_res.json()["quantity_delta"] == -20

    over_issue_res = client.post(
        f"/api/v1/inventory/lots/{lot['id']}/movements",
        json={"quantity_delta": 1000, "movement_type": "issue"},
        headers=headers,
    )
    assert over_issue_res.status_code == 409


def test_stock_transfer_between_warehouses(client, tenant):
    headers = tenant.auth_headers(client)
    item = _create_item(client, headers, code=f"npk3-{tenant.tenant_slug}")
    wh_a = _create_warehouse(client, headers, code=f"WHA-{tenant.tenant_slug}")
    wh_b = _create_warehouse(client, headers, code=f"WHB-{tenant.tenant_slug}")
    lot = client.post(
        f"/api/v1/inventory/warehouses/{wh_a['id']}/receive",
        json={"item_id": item["id"], "lot_code": "LOT-C", "quantity": 40},
        headers=headers,
    ).json()

    transfer_res = client.post(
        f"/api/v1/inventory/lots/{lot['id']}/movements",
        json={"quantity_delta": 15, "movement_type": "transfer", "to_warehouse_id": wh_b["id"]},
        headers=headers,
    )
    assert transfer_res.status_code == 201, transfer_res.text

    source_lots = client.get(f"/api/v1/inventory/items/{item['id']}/lots", headers=headers).json()
    by_warehouse = {lot_["warehouse_id"]: lot_["quantity"] for lot_ in source_lots}
    assert by_warehouse[wh_a["id"]] == 25
    assert by_warehouse[wh_b["id"]] == 15


def test_reorder_point_raises_alert(client, tenant):
    headers = tenant.auth_headers(client)
    item = _create_item(client, headers, code=f"npk4-{tenant.tenant_slug}", min_qty=30)
    warehouse = _create_warehouse(client, headers, code=f"WH4-{tenant.tenant_slug}")
    lot = client.post(
        f"/api/v1/inventory/warehouses/{warehouse['id']}/receive",
        json={"item_id": item["id"], "lot_code": "LOT-D", "quantity": 40},
        headers=headers,
    ).json()

    client.post(
        f"/api/v1/inventory/lots/{lot['id']}/movements",
        json={"quantity_delta": 20, "movement_type": "issue"},
        headers=headers,
    )

    alerts_res = client.get("/api/v1/iot/alerts", params={"status": "open"}, headers=headers)
    assert any(a["entity_type"] == "inventory_item" and a["entity_id"] == item["id"] for a in alerts_res.json())


def test_item_valuation(client, tenant):
    headers = tenant.auth_headers(client)
    item = _create_item(client, headers, code=f"npk5-{tenant.tenant_slug}", min_qty=10)
    warehouse = _create_warehouse(client, headers, code=f"WH5-{tenant.tenant_slug}")
    client.post(
        f"/api/v1/inventory/warehouses/{warehouse['id']}/receive",
        json={"item_id": item["id"], "lot_code": "LOT-E", "quantity": 20, "unit_cost": 10.0},
        headers=headers,
    )

    valuation_res = client.get(f"/api/v1/inventory/items/{item['id']}/valuation", headers=headers)
    assert valuation_res.status_code == 200
    valuation = valuation_res.json()
    assert valuation["total_quantity"] == 20
    assert valuation["total_value"] == 200.0
    assert valuation["below_reorder_point"] is False


def test_seeded_purchase_workflow_exists(client, tenant):
    headers = tenant.auth_headers(client)
    definitions = client.get("/api/v1/workflows/definitions", headers=headers).json()
    assert "purchase_request" in {d["entity_type"] for d in definitions}


def test_purchase_request_full_lifecycle_to_inventory(client, tenant):
    headers = tenant.auth_headers(client)
    item = _create_item(client, headers, code=f"npk6-{tenant.tenant_slug}")
    warehouse = _create_warehouse(client, headers, code=f"WH6-{tenant.tenant_slug}")
    vendor = _create_vendor(client, headers, code=f"vendor6-{tenant.tenant_slug}")

    request_res = client.post(
        "/api/v1/inventory/purchase-requests",
        json={"item_id": item["id"], "quantity": 100, "reason": "restock before dry season"},
        headers=headers,
    )
    assert request_res.status_code == 201, request_res.text
    request = request_res.json()

    client.post(f"/api/v1/inventory/purchase-requests/{request['id']}/submit", headers=headers)
    approve_res = client.post(f"/api/v1/inventory/purchase-requests/{request['id']}/approve", json={}, headers=headers)
    assert approve_res.status_code == 200, approve_res.text

    po_res = client.post(
        f"/api/v1/inventory/purchase-requests/{request['id']}/issue-po",
        json={"vendor_id": vendor["id"], "unit_price": 12.5},
        headers=headers,
    )
    assert po_res.status_code == 201, po_res.text
    po = po_res.json()
    assert po["status"] == "issued"

    receive_res = client.post(
        f"/api/v1/inventory/purchase-orders/{po['id']}/receive",
        json={"warehouse_id": warehouse["id"], "received_quantity": 100, "inspection_status": "passed"},
        headers=headers,
    )
    assert receive_res.status_code == 200, receive_res.text
    received_po = receive_res.json()
    assert received_po["status"] == "received"
    assert received_po["resulting_lot_id"]

    lots_res = client.get(f"/api/v1/inventory/items/{item['id']}/lots", headers=headers)
    assert any(lot["id"] == received_po["resulting_lot_id"] and lot["quantity"] == 100 for lot in lots_res.json())

    match_res = client.post(
        f"/api/v1/inventory/purchase-orders/{po['id']}/match-invoice",
        json={"invoice_number": "INV-001", "invoice_amount": 1250.0},
        headers=headers,
    )
    assert match_res.status_code == 200, match_res.text
    matched = match_res.json()
    assert matched["invoice_matched"] is True
    assert matched["status"] == "invoiced"


def test_purchase_request_reject_blocks_issue_po(client, tenant):
    headers = tenant.auth_headers(client)
    item = _create_item(client, headers, code=f"npk7-{tenant.tenant_slug}")
    vendor = _create_vendor(client, headers, code=f"vendor7-{tenant.tenant_slug}")

    request = client.post(
        "/api/v1/inventory/purchase-requests", json={"item_id": item["id"], "quantity": 10}, headers=headers
    ).json()
    client.post(f"/api/v1/inventory/purchase-requests/{request['id']}/submit", headers=headers)
    client.post(f"/api/v1/inventory/purchase-requests/{request['id']}/reject", json={"reason": "budget"}, headers=headers)

    po_res = client.post(
        f"/api/v1/inventory/purchase-requests/{request['id']}/issue-po",
        json={"vendor_id": vendor["id"]},
        headers=headers,
    )
    assert po_res.status_code == 409


def test_warehouse_farm_scoped_abac(client, tenant):
    admin_headers = tenant.auth_headers(client)
    farm_a = client.post("/api/v1/farm/farms", json={"code": "INVA", "name": "Inv Farm A"}, headers=admin_headers).json()
    farm_b = client.post("/api/v1/farm/farms", json={"code": "INVB", "name": "Inv Farm B"}, headers=admin_headers).json()

    wh_a = client.post(
        "/api/v1/inventory/warehouses", json={"farm_id": farm_a["id"], "code": "WHFA", "name": "Farm A Store"}, headers=admin_headers
    ).json()
    wh_b = client.post(
        "/api/v1/inventory/warehouses", json={"farm_id": farm_b["id"], "code": "WHFB", "name": "Farm B Store"}, headers=admin_headers
    ).json()

    email = f"whmgr-{unique_slug('u')}@example.com"
    password = "pw-for-testing-123"
    user = client.post(
        "/api/v1/users", json={"email": email, "password": password, "full_name": "Warehouse Manager"}, headers=admin_headers
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

    ok_res = client.get("/api/v1/inventory/warehouses", params={"farm_id": farm_a["id"]}, headers=manager_headers)
    assert ok_res.status_code == 200

    denied_res = client.get("/api/v1/inventory/warehouses", params={"farm_id": farm_b["id"]}, headers=manager_headers)
    assert denied_res.status_code == 403
