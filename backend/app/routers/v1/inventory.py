import random
import string
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.deps import assert_farm_scope, require_permission
from ...database import get_db
from ...farm import models as farm_models
from ...foundation import models as fm
from ...foundation import workflow_engine
from ...foundation.audit import record_audit
from ...inventory import models as inv_models
from ...inventory import schemas as inv_schemas
from ...iot import models as iot_models

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])


def _get_or_404(db: Session, model, obj_id: str, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


def _assert_optional_farm_scope(db: Session, user: fm.User, permission_code: str, farm_id: Optional[str]) -> None:
    """Same rationale as `routers.v1.asset._assert_optional_farm_scope` -
    a Warehouse/PurchaseRequest/PurchaseOrder's `farm_id` is nullable
    (a central warehouse, a company-wide purchase), so only narrow with
    `assert_farm_scope` when there's an actual farm to narrow to."""
    if farm_id is not None:
        assert_farm_scope(db, user, permission_code, farm_id)


def _correlation_id(request: Request) -> str:
    return request.headers.get("x-correlation-id", "")


def _new_po_number() -> str:
    return "PO-" + "".join(random.choices(string.digits, k=8))


# ---------------------------------------------------------------------------
# Master data: items, warehouses, vendors
# ---------------------------------------------------------------------------

@router.post("/items", response_model=inv_schemas.ItemOut, status_code=201)
def create_item(
    payload: inv_schemas.ItemCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("inventory.item.manage")),
):
    if payload.category not in inv_models.ITEM_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Unknown category '{payload.category}'")

    item = inv_models.Item(
        tenant_id=current_user.tenant_id,
        code=payload.code,
        name=payload.name,
        category=payload.category,
        uom=payload.uom,
        min_qty=payload.min_qty,
        max_qty=payload.max_qty,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(item)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An item with this code already exists") from exc

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="inventory_item.create", entity_type="inventory_item", entity_id=item.id,
        new_values={"code": item.code, "category": item.category},
    )
    db.commit()
    return item


@router.get("/items", response_model=list[inv_schemas.ItemOut])
def list_items(
    db: Session = Depends(get_db),
    _user: fm.User = Depends(require_permission("inventory.item.view")),
):
    return db.query(inv_models.Item).order_by(inv_models.Item.name.asc()).all()


@router.post("/warehouses", response_model=inv_schemas.WarehouseOut, status_code=201)
def create_warehouse(
    payload: inv_schemas.WarehouseCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("inventory.warehouse.manage")),
):
    if payload.farm_id:
        farm = _get_or_404(db, farm_models.Farm, payload.farm_id, "Farm")
        assert_farm_scope(db, current_user, "inventory.warehouse.manage", farm.id)

    warehouse = inv_models.Warehouse(
        tenant_id=current_user.tenant_id,
        farm_id=payload.farm_id,
        code=payload.code,
        name=payload.name,
        location=payload.location,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(warehouse)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A warehouse with this code already exists") from exc

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="warehouse.create", entity_type="warehouse", entity_id=warehouse.id,
        new_values={"code": warehouse.code, "farm_id": payload.farm_id},
    )
    db.commit()
    return warehouse


@router.get("/warehouses", response_model=list[inv_schemas.WarehouseOut])
def list_warehouses(
    farm_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("inventory.warehouse.view")),
):
    if farm_id:
        assert_farm_scope(db, user, "inventory.warehouse.view", farm_id)
    query = db.query(inv_models.Warehouse)
    if farm_id:
        query = query.filter(inv_models.Warehouse.farm_id == farm_id)
    return query.order_by(inv_models.Warehouse.name.asc()).all()


@router.post("/vendors", response_model=inv_schemas.VendorOut, status_code=201)
def create_vendor(
    payload: inv_schemas.VendorCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("inventory.vendor.manage")),
):
    vendor = inv_models.Vendor(
        tenant_id=current_user.tenant_id,
        code=payload.code,
        name=payload.name,
        contact_info=payload.contact_info,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(vendor)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A vendor with this code already exists") from exc

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="vendor.create", entity_type="vendor", entity_id=vendor.id, new_values={"code": vendor.code},
    )
    db.commit()
    return vendor


@router.get("/vendors", response_model=list[inv_schemas.VendorOut])
def list_vendors(
    db: Session = Depends(get_db),
    _user: fm.User = Depends(require_permission("inventory.vendor.view")),
):
    return db.query(inv_models.Vendor).order_by(inv_models.Vendor.name.asc()).all()


# ---------------------------------------------------------------------------
# Stock (FR-INV-001)
# ---------------------------------------------------------------------------

def _check_reorder_point(db: Session, tenant_id: str, item: inv_models.Item) -> None:
    """FR-INV-001's min/max reorder point, wired to Phase 7's existing
    Alert infrastructure rather than a separate low-stock mechanism."""
    if item.min_qty is None:
        return
    total = db.query(func.sum(inv_models.StockLot.quantity)).filter(inv_models.StockLot.item_id == item.id).scalar() or 0.0
    if total >= item.min_qty:
        return
    already_open = (
        db.query(iot_models.Alert)
        .filter(
            iot_models.Alert.tenant_id == tenant_id,
            iot_models.Alert.entity_type == "inventory_item",
            iot_models.Alert.entity_id == item.id,
            iot_models.Alert.status == "open",
        )
        .first()
    )
    if already_open:
        return
    db.add(
        iot_models.Alert(
            tenant_id=tenant_id,
            entity_type="inventory_item",
            entity_id=item.id,
            severity="medium",
            status="open",
            message=f"'{item.name}' on-hand ({total:g} {item.uom}) is below the reorder point ({item.min_qty:g} {item.uom})",
            raised_at=datetime.now(timezone.utc),
        )
    )


@router.post("/warehouses/{warehouse_id}/receive", response_model=inv_schemas.StockLotOut, status_code=201)
def receive_stock(
    warehouse_id: str,
    payload: inv_schemas.StockReceiptRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("inventory.stock.manage")),
):
    warehouse = _get_or_404(db, inv_models.Warehouse, warehouse_id, "Warehouse")
    _assert_optional_farm_scope(db, current_user, "inventory.stock.manage", warehouse.farm_id)
    item = _get_or_404(db, inv_models.Item, payload.item_id, "Item")

    lot = inv_models.StockLot(
        tenant_id=current_user.tenant_id,
        item_id=item.id,
        warehouse_id=warehouse.id,
        lot_code=payload.lot_code,
        quantity=payload.quantity,
        unit_cost=payload.unit_cost,
        expiry_date=payload.expiry_date,
        received_at=datetime.now(timezone.utc),
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(lot)
    db.flush()

    db.add(
        inv_models.StockMovement(
            tenant_id=current_user.tenant_id,
            lot_id=lot.id,
            movement_type="receipt",
            quantity_delta=payload.quantity,
            to_warehouse_id=warehouse.id,
            performed_by=current_user.id,
            performed_at=lot.received_at,
            notes=payload.notes,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
    )
    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="stock.receive", entity_type="stock_lot", entity_id=lot.id,
        new_values={"item_id": item.id, "warehouse_id": warehouse.id, "quantity": payload.quantity},
    )
    db.commit()
    return lot


@router.post("/lots/{lot_id}/movements", response_model=inv_schemas.StockMovementOut, status_code=201)
def record_movement(
    lot_id: str,
    payload: inv_schemas.StockMovementRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("inventory.stock.manage")),
):
    lot = _get_or_404(db, inv_models.StockLot, lot_id, "Stock lot")
    warehouse = _get_or_404(db, inv_models.Warehouse, lot.warehouse_id, "Warehouse")
    _assert_optional_farm_scope(db, current_user, "inventory.stock.manage", warehouse.farm_id)
    if payload.movement_type not in inv_models.MOVEMENT_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown movement_type '{payload.movement_type}'")
    if payload.reference_type and payload.reference_type not in inv_models.MOVEMENT_REFERENCE_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown reference_type '{payload.reference_type}'")

    now = datetime.now(timezone.utc)
    from_warehouse_id = None

    if payload.movement_type == "transfer":
        if not payload.to_warehouse_id:
            raise HTTPException(status_code=422, detail="to_warehouse_id is required for a transfer")
        if payload.quantity_delta <= 0:
            raise HTTPException(status_code=422, detail="quantity_delta must be positive for a transfer")
        to_warehouse = _get_or_404(db, inv_models.Warehouse, payload.to_warehouse_id, "Destination warehouse")
        _assert_optional_farm_scope(db, current_user, "inventory.stock.manage", to_warehouse.farm_id)
        if lot.quantity < payload.quantity_delta:
            raise HTTPException(status_code=409, detail="Insufficient quantity in source lot for this transfer")

        from_warehouse_id = warehouse.id
        lot.quantity -= payload.quantity_delta
        lot.updated_by = current_user.id

        dest_lot = (
            db.query(inv_models.StockLot)
            .filter(
                inv_models.StockLot.item_id == lot.item_id,
                inv_models.StockLot.warehouse_id == to_warehouse.id,
                inv_models.StockLot.lot_code == lot.lot_code,
            )
            .one_or_none()
        )
        if dest_lot is None:
            dest_lot = inv_models.StockLot(
                tenant_id=current_user.tenant_id, item_id=lot.item_id, warehouse_id=to_warehouse.id,
                lot_code=lot.lot_code, quantity=0.0, unit_cost=lot.unit_cost, expiry_date=lot.expiry_date,
                received_at=now, created_by=current_user.id, updated_by=current_user.id,
            )
            db.add(dest_lot)
            db.flush()
        dest_lot.quantity += payload.quantity_delta
        dest_lot.updated_by = current_user.id
    else:
        if payload.movement_type == "issue" and payload.quantity_delta > 0:
            payload.quantity_delta = -abs(payload.quantity_delta)
        new_quantity = lot.quantity + payload.quantity_delta
        if new_quantity < 0:
            raise HTTPException(status_code=409, detail="This movement would take the lot quantity below zero")
        lot.quantity = new_quantity
        lot.updated_by = current_user.id

    movement = inv_models.StockMovement(
        tenant_id=current_user.tenant_id,
        lot_id=lot.id,
        movement_type=payload.movement_type,
        quantity_delta=payload.quantity_delta,
        reference_type=payload.reference_type,
        reference_id=payload.reference_id,
        from_warehouse_id=from_warehouse_id,
        to_warehouse_id=payload.to_warehouse_id if payload.movement_type == "transfer" else None,
        performed_by=current_user.id,
        performed_at=now,
        notes=payload.notes,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(movement)
    db.flush()

    item = db.get(inv_models.Item, lot.item_id)
    if payload.movement_type in ("issue", "transfer", "adjustment"):
        _check_reorder_point(db, current_user.tenant_id, item)

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="stock.movement", entity_type="stock_movement", entity_id=movement.id,
        new_values={"lot_id": lot.id, "movement_type": movement.movement_type, "quantity_delta": movement.quantity_delta},
    )
    db.commit()
    return movement


@router.get("/items/{item_id}/lots", response_model=list[inv_schemas.StockLotOut])
def list_item_lots(
    item_id: str,
    db: Session = Depends(get_db),
    _user: fm.User = Depends(require_permission("inventory.stock.view")),
):
    _get_or_404(db, inv_models.Item, item_id, "Item")
    return db.query(inv_models.StockLot).filter(inv_models.StockLot.item_id == item_id).order_by(inv_models.StockLot.received_at.asc()).all()


@router.get("/lots/{lot_id}/movements", response_model=list[inv_schemas.StockMovementOut])
def list_lot_movements(
    lot_id: str,
    db: Session = Depends(get_db),
    _user: fm.User = Depends(require_permission("inventory.stock.view")),
):
    _get_or_404(db, inv_models.StockLot, lot_id, "Stock lot")
    return (
        db.query(inv_models.StockMovement)
        .filter(inv_models.StockMovement.lot_id == lot_id)
        .order_by(inv_models.StockMovement.performed_at.desc())
        .all()
    )


@router.get("/items/{item_id}/valuation", response_model=inv_schemas.ItemValuationOut)
def item_valuation(
    item_id: str,
    db: Session = Depends(get_db),
    _user: fm.User = Depends(require_permission("inventory.stock.view")),
):
    item = _get_or_404(db, inv_models.Item, item_id, "Item")
    lots = db.query(inv_models.StockLot).filter(inv_models.StockLot.item_id == item_id).all()
    total_quantity = sum(lot.quantity for lot in lots)
    total_value = sum(lot.quantity * (lot.unit_cost or 0.0) for lot in lots)
    below_reorder = item.min_qty is not None and total_quantity < item.min_qty
    return inv_schemas.ItemValuationOut(
        item_id=item.id, total_quantity=total_quantity, total_value=total_value, below_reorder_point=below_reorder
    )


# ---------------------------------------------------------------------------
# Procurement (FR-PROC-001)
# ---------------------------------------------------------------------------

def _active_definition(db: Session, tenant_id: str, entity_type: str) -> fm.WorkflowDefinition:
    definition = (
        db.query(fm.WorkflowDefinition)
        .filter(
            fm.WorkflowDefinition.tenant_id == tenant_id,
            fm.WorkflowDefinition.entity_type == entity_type,
            fm.WorkflowDefinition.is_active.is_(True),
        )
        .first()
    )
    if definition is None:
        raise HTTPException(status_code=409, detail=f"No active approval workflow configured for '{entity_type}' - contact your tenant admin")
    return definition


@router.post("/purchase-requests", response_model=inv_schemas.PurchaseRequestOut, status_code=201)
def create_purchase_request(
    payload: inv_schemas.PurchaseRequestCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("procurement.request.manage")),
):
    _assert_optional_farm_scope(db, current_user, "procurement.request.manage", payload.farm_id)
    item = _get_or_404(db, inv_models.Item, payload.item_id, "Item")
    if payload.farm_id:
        _get_or_404(db, farm_models.Farm, payload.farm_id, "Farm")

    request = inv_models.PurchaseRequest(
        tenant_id=current_user.tenant_id,
        item_id=item.id,
        farm_id=payload.farm_id,
        quantity=payload.quantity,
        needed_by=payload.needed_by,
        reason=payload.reason,
        requested_by=current_user.id,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(request)
    db.flush()

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="purchase_request.create", entity_type="purchase_request", entity_id=request.id,
        new_values={"item_id": item.id, "quantity": request.quantity},
    )
    db.commit()
    return request


@router.get("/purchase-requests", response_model=list[inv_schemas.PurchaseRequestOut])
def list_purchase_requests(
    farm_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("procurement.request.view")),
):
    if farm_id:
        assert_farm_scope(db, user, "procurement.request.view", farm_id)
    query = db.query(inv_models.PurchaseRequest)
    if farm_id:
        query = query.filter(inv_models.PurchaseRequest.farm_id == farm_id)
    return query.order_by(inv_models.PurchaseRequest.created_at.desc()).all()


@router.get("/purchase-requests/{request_id}", response_model=inv_schemas.PurchaseRequestOut)
def get_purchase_request(
    request_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("procurement.request.view")),
):
    request = _get_or_404(db, inv_models.PurchaseRequest, request_id, "Purchase request")
    _assert_optional_farm_scope(db, user, "procurement.request.view", request.farm_id)
    return request


@router.post("/purchase-requests/{request_id}/submit", response_model=inv_schemas.PurchaseRequestOut)
def submit_purchase_request(
    request_id: str,
    request_ctx: Request,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("procurement.request.manage")),
):
    purchase_request = _get_or_404(db, inv_models.PurchaseRequest, request_id, "Purchase request")
    _assert_optional_farm_scope(db, current_user, "procurement.request.manage", purchase_request.farm_id)
    if purchase_request.status != "draft":
        raise HTTPException(status_code=409, detail=f"Cannot submit a request in status '{purchase_request.status}'")

    definition = _active_definition(db, current_user.tenant_id, "purchase_request")
    instance = workflow_engine.submit(
        db, tenant_id=current_user.tenant_id, actor=current_user, definition=definition,
        entity_type="purchase_request", entity_id=purchase_request.id,
        context={"item_id": purchase_request.item_id, "farm_id": purchase_request.farm_id},
        correlation_id=_correlation_id(request_ctx),
    )
    purchase_request.workflow_instance_id = instance.id
    purchase_request.status = "pending_approval"
    purchase_request.updated_by = current_user.id
    db.commit()
    return purchase_request


def _decide_purchase_request(action: str):
    """See `routers.v1.irrigation._decide_irrigation`'s docstring - same
    layered farm-scope gate on top of the workflow engine's own
    (farm-unaware) role/permission check."""

    def handler(
        request_id: str,
        payload: inv_schemas.ApprovalDecisionRequest,
        request_ctx: Request,
        db: Session = Depends(get_db),
        current_user: fm.User = Depends(require_permission("procurement.request.manage")),
    ):
        purchase_request = _get_or_404(db, inv_models.PurchaseRequest, request_id, "Purchase request")
        _assert_optional_farm_scope(db, current_user, "procurement.request.manage", purchase_request.farm_id)
        if not purchase_request.workflow_instance_id:
            raise HTTPException(status_code=409, detail="Request has not been submitted for approval")

        instance = _get_or_404(db, fm.WorkflowInstance, purchase_request.workflow_instance_id, "Workflow instance")
        definition = db.get(fm.WorkflowDefinition, instance.workflow_definition_id)
        workflow_engine.decide(
            db, tenant_id=current_user.tenant_id, actor=current_user, instance=instance, definition=definition,
            action=action, reason=payload.reason, correlation_id=_correlation_id(request_ctx),
        )
        if instance.status == "approved":
            purchase_request.status = "approved"
        elif instance.status in ("rejected", "cancelled"):
            purchase_request.status = "rejected"
        elif instance.status == "draft":
            purchase_request.status = "draft"
        purchase_request.updated_by = current_user.id
        db.commit()
        return purchase_request

    return handler


router.add_api_route(
    "/purchase-requests/{request_id}/approve", _decide_purchase_request("approve"), methods=["POST"],
    response_model=inv_schemas.PurchaseRequestOut,
)
router.add_api_route(
    "/purchase-requests/{request_id}/reject", _decide_purchase_request("reject"), methods=["POST"],
    response_model=inv_schemas.PurchaseRequestOut,
)


@router.post("/purchase-requests/{request_id}/issue-po", response_model=inv_schemas.PurchaseOrderOut, status_code=201)
def issue_purchase_order(
    request_id: str,
    payload: inv_schemas.PurchaseOrderCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("procurement.order.manage")),
):
    """Only an approved PurchaseRequest can become a PurchaseOrder - the
    Approved Action, same pattern as Phase 12's WorkOrder."""
    purchase_request = _get_or_404(db, inv_models.PurchaseRequest, request_id, "Purchase request")
    _assert_optional_farm_scope(db, current_user, "procurement.order.manage", purchase_request.farm_id)
    if purchase_request.status != "approved":
        raise HTTPException(status_code=409, detail="Only an approved request can be issued as a purchase order")
    vendor = _get_or_404(db, inv_models.Vendor, payload.vendor_id, "Vendor")

    po = inv_models.PurchaseOrder(
        tenant_id=current_user.tenant_id,
        request_id=purchase_request.id,
        vendor_id=vendor.id,
        item_id=purchase_request.item_id,
        farm_id=purchase_request.farm_id,
        po_number=_new_po_number(),
        quantity=purchase_request.quantity,
        unit_price=payload.unit_price,
        issued_at=datetime.now(timezone.utc),
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(po)
    purchase_request.status = "converted"
    purchase_request.updated_by = current_user.id
    db.flush()

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="purchase_request.issue_po", entity_type="purchase_order", entity_id=po.id,
        new_values={"request_id": purchase_request.id, "vendor_id": vendor.id, "po_number": po.po_number},
    )
    db.commit()
    return po


@router.get("/purchase-orders", response_model=list[inv_schemas.PurchaseOrderOut])
def list_purchase_orders(
    farm_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("procurement.order.view")),
):
    if farm_id:
        assert_farm_scope(db, user, "procurement.order.view", farm_id)
    query = db.query(inv_models.PurchaseOrder)
    if farm_id:
        query = query.filter(inv_models.PurchaseOrder.farm_id == farm_id)
    if status:
        query = query.filter(inv_models.PurchaseOrder.status == status)
    return query.order_by(inv_models.PurchaseOrder.issued_at.desc()).all()


@router.get("/purchase-orders/{po_id}", response_model=inv_schemas.PurchaseOrderOut)
def get_purchase_order(
    po_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("procurement.order.view")),
):
    po = _get_or_404(db, inv_models.PurchaseOrder, po_id, "Purchase order")
    _assert_optional_farm_scope(db, user, "procurement.order.view", po.farm_id)
    return po


@router.post("/purchase-orders/{po_id}/receive", response_model=inv_schemas.PurchaseOrderOut)
def receive_purchase_order(
    po_id: str,
    payload: inv_schemas.PurchaseOrderReceiveRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("procurement.order.manage")),
):
    """Receiving + Inspection + Inventory in one step (FR-PROC-001): a
    passed inspection creates the StockLot/StockMovement directly, closing
    the procurement pipeline into real, on-hand inventory."""
    po = _get_or_404(db, inv_models.PurchaseOrder, po_id, "Purchase order")
    _assert_optional_farm_scope(db, current_user, "procurement.order.manage", po.farm_id)
    if po.status not in ("issued", "receiving"):
        raise HTTPException(status_code=409, detail=f"Cannot receive a purchase order in status '{po.status}'")
    warehouse = _get_or_404(db, inv_models.Warehouse, payload.warehouse_id, "Warehouse")
    _assert_optional_farm_scope(db, current_user, "procurement.order.manage", warehouse.farm_id)

    now = datetime.now(timezone.utc)
    po.received_quantity = payload.received_quantity
    po.received_at = now
    po.inspection_status = payload.inspection_status
    po.inspection_notes = payload.inspection_notes
    po.warehouse_id = warehouse.id
    po.updated_by = current_user.id

    if payload.inspection_status == "passed":
        lot = inv_models.StockLot(
            tenant_id=current_user.tenant_id, item_id=po.item_id, warehouse_id=warehouse.id,
            lot_code=payload.lot_code or po.po_number, quantity=payload.received_quantity,
            unit_cost=po.unit_price, expiry_date=payload.expiry_date, received_at=now,
            created_by=current_user.id, updated_by=current_user.id,
        )
        db.add(lot)
        db.flush()
        db.add(
            inv_models.StockMovement(
                tenant_id=current_user.tenant_id, lot_id=lot.id, movement_type="receipt",
                quantity_delta=payload.received_quantity, reference_type="asset", reference_id=None,
                to_warehouse_id=warehouse.id, performed_by=current_user.id, performed_at=now,
                notes=f"Received against {po.po_number}", created_by=current_user.id, updated_by=current_user.id,
            )
        )
        po.resulting_lot_id = lot.id
        po.status = "received"
    else:
        po.status = "receiving"

    db.flush()
    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="purchase_order.receive", entity_type="purchase_order", entity_id=po.id,
        new_values={"received_quantity": payload.received_quantity, "inspection_status": payload.inspection_status},
    )
    db.commit()
    return po


@router.post("/purchase-orders/{po_id}/match-invoice", response_model=inv_schemas.PurchaseOrderOut)
def match_invoice(
    po_id: str,
    payload: inv_schemas.PurchaseOrderInvoiceRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("procurement.order.manage")),
):
    po = _get_or_404(db, inv_models.PurchaseOrder, po_id, "Purchase order")
    _assert_optional_farm_scope(db, current_user, "procurement.order.manage", po.farm_id)
    if po.status != "received":
        raise HTTPException(status_code=409, detail="Only a received purchase order can be invoice-matched")

    expected = (po.unit_price or 0.0) * (po.received_quantity or po.quantity)
    tolerance = expected * (payload.tolerance_pct / 100)
    matched = expected > 0 and abs(payload.invoice_amount - expected) <= tolerance

    po.invoice_number = payload.invoice_number
    po.invoice_amount = payload.invoice_amount
    po.invoice_matched = matched
    po.status = "invoiced"
    po.updated_by = current_user.id
    db.flush()

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="purchase_order.match_invoice", entity_type="purchase_order", entity_id=po.id,
        new_values={"invoice_number": payload.invoice_number, "invoice_amount": payload.invoice_amount, "matched": matched},
    )
    db.commit()
    return po
