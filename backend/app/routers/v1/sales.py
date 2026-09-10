import random
import string
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...accounting.service import post_ledger_entry
from ...core.deps import assert_farm_scope, require_permission
from ...database import get_db
from ...farm import models as farm_models
from ...foundation import models as fm
from ...foundation.audit import record_audit
from ...harvest import models as harvest_models
from ...sales import models as sales_models
from ...sales import schemas as sales_schemas

router = APIRouter(prefix="/api/v1/sales", tags=["sales"])


def _get_or_404(db: Session, model, obj_id: str, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


def _assert_optional_farm_scope(db: Session, user: fm.User, permission_code: str, farm_id: Optional[str]) -> None:
    if farm_id is not None:
        assert_farm_scope(db, user, permission_code, farm_id)


def _new_invoice_number() -> str:
    return "INV-" + "".join(random.choices(string.digits, k=8))


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

@router.post("/customers", response_model=sales_schemas.CustomerOut, status_code=201)
def create_customer(
    payload: sales_schemas.CustomerCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("sales.customer.manage")),
):
    customer = sales_models.Customer(
        tenant_id=current_user.tenant_id, code=payload.code, name=payload.name, contact_info=payload.contact_info,
        created_by=current_user.id, updated_by=current_user.id,
    )
    db.add(customer)
    db.flush()

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="customer.create", entity_type="customer", entity_id=customer.id, new_values={"code": customer.code},
    )
    db.commit()
    return customer


@router.get("/customers", response_model=list[sales_schemas.CustomerOut])
def list_customers(
    db: Session = Depends(get_db),
    _user: fm.User = Depends(require_permission("sales.customer.view")),
):
    return db.query(sales_models.Customer).order_by(sales_models.Customer.name.asc()).all()


# ---------------------------------------------------------------------------
# Sales orders (FR-SALES-001, collapsed pipeline - see models.py)
# ---------------------------------------------------------------------------

@router.post("/orders", response_model=sales_schemas.SalesOrderOut, status_code=201)
def create_order(
    payload: sales_schemas.SalesOrderCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("sales.order.manage")),
):
    _assert_optional_farm_scope(db, current_user, "sales.order.manage", payload.farm_id)
    _get_or_404(db, sales_models.Customer, payload.customer_id, "Customer")
    if payload.harvest_lot_id:
        _get_or_404(db, harvest_models.HarvestLot, payload.harvest_lot_id, "Harvest lot")
    if payload.farm_id:
        _get_or_404(db, farm_models.Farm, payload.farm_id, "Farm")

    order = sales_models.SalesOrder(
        tenant_id=current_user.tenant_id, customer_id=payload.customer_id, farm_id=payload.farm_id,
        season_id=payload.season_id, harvest_lot_id=payload.harvest_lot_id, quantity_kg=payload.quantity_kg,
        unit_price=payload.unit_price, order_date=payload.order_date or date.today(),
        created_by=current_user.id, updated_by=current_user.id,
    )
    db.add(order)
    db.flush()

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="sales_order.create", entity_type="sales_order", entity_id=order.id,
        new_values={"customer_id": order.customer_id, "quantity_kg": order.quantity_kg},
    )
    db.commit()
    return order


@router.get("/orders", response_model=list[sales_schemas.SalesOrderOut])
def list_orders(
    farm_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("sales.order.view")),
):
    if farm_id:
        assert_farm_scope(db, user, "sales.order.view", farm_id)
    query = db.query(sales_models.SalesOrder)
    if farm_id:
        query = query.filter(sales_models.SalesOrder.farm_id == farm_id)
    return query.order_by(sales_models.SalesOrder.order_date.desc()).all()


@router.get("/orders/{order_id}", response_model=sales_schemas.SalesOrderOut)
def get_order(
    order_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("sales.order.view")),
):
    order = _get_or_404(db, sales_models.SalesOrder, order_id, "Sales order")
    _assert_optional_farm_scope(db, user, "sales.order.view", order.farm_id)
    return order


def _advance_order_status(order: sales_models.SalesOrder, from_status: str, to_status: str) -> None:
    if order.status != from_status:
        raise HTTPException(status_code=409, detail=f"Cannot move an order from '{order.status}' to '{to_status}' (expected '{from_status}')")
    order.status = to_status


@router.post("/orders/{order_id}/confirm", response_model=sales_schemas.SalesOrderOut)
def confirm_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("sales.order.manage")),
):
    order = _get_or_404(db, sales_models.SalesOrder, order_id, "Sales order")
    _assert_optional_farm_scope(db, current_user, "sales.order.manage", order.farm_id)
    _advance_order_status(order, "draft", "confirmed")
    order.updated_by = current_user.id
    db.commit()
    return order


@router.post("/orders/{order_id}/deliver", response_model=sales_schemas.SalesOrderOut)
def deliver_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("sales.order.manage")),
):
    order = _get_or_404(db, sales_models.SalesOrder, order_id, "Sales order")
    _assert_optional_farm_scope(db, current_user, "sales.order.manage", order.farm_id)
    _advance_order_status(order, "confirmed", "delivered")
    order.updated_by = current_user.id
    db.commit()
    return order


# ---------------------------------------------------------------------------
# Invoices / Payments - a fully paid invoice auto-posts a revenue
# LedgerEntry (Phase 14's accounting integration point, FR-ACC-001).
# ---------------------------------------------------------------------------

@router.post("/orders/{order_id}/invoices", response_model=sales_schemas.InvoiceOut, status_code=201)
def create_invoice(
    order_id: str,
    payload: sales_schemas.InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("sales.order.manage")),
):
    order = _get_or_404(db, sales_models.SalesOrder, order_id, "Sales order")
    _assert_optional_farm_scope(db, current_user, "sales.order.manage", order.farm_id)
    if order.status != "delivered":
        raise HTTPException(status_code=409, detail="Only a delivered order can be invoiced")

    invoice = sales_models.Invoice(
        tenant_id=current_user.tenant_id, order_id=order.id, invoice_number=_new_invoice_number(),
        amount=payload.amount if payload.amount is not None else order.quantity_kg * order.unit_price,
        issued_at=datetime.now(timezone.utc), due_date=payload.due_date,
        created_by=current_user.id, updated_by=current_user.id,
    )
    db.add(invoice)
    order.status = "invoiced"
    order.updated_by = current_user.id
    db.flush()

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="sales_invoice.create", entity_type="sales_invoice", entity_id=invoice.id,
        new_values={"order_id": order.id, "amount": invoice.amount},
    )
    db.commit()
    return invoice


@router.get("/invoices/{invoice_id}", response_model=sales_schemas.InvoiceOut)
def get_invoice(
    invoice_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("sales.order.view")),
):
    invoice = _get_or_404(db, sales_models.Invoice, invoice_id, "Invoice")
    order = _get_or_404(db, sales_models.SalesOrder, invoice.order_id, "Sales order")
    _assert_optional_farm_scope(db, user, "sales.order.view", order.farm_id)
    return invoice


@router.post("/invoices/{invoice_id}/payments", response_model=sales_schemas.PaymentOut, status_code=201)
def record_payment(
    invoice_id: str,
    payload: sales_schemas.PaymentCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("sales.order.manage")),
):
    invoice = _get_or_404(db, sales_models.Invoice, invoice_id, "Invoice")
    order = _get_or_404(db, sales_models.SalesOrder, invoice.order_id, "Sales order")
    _assert_optional_farm_scope(db, current_user, "sales.order.manage", order.farm_id)
    if invoice.is_paid:
        raise HTTPException(status_code=409, detail="Invoice is already fully paid")

    payment = sales_models.Payment(
        tenant_id=current_user.tenant_id, invoice_id=invoice.id, amount=payload.amount, method=payload.method,
        paid_at=payload.paid_at or datetime.now(timezone.utc), created_by=current_user.id, updated_by=current_user.id,
    )
    db.add(payment)
    db.flush()

    total_paid = (
        db.query(func.coalesce(func.sum(sales_models.Payment.amount), 0.0))
        .filter(sales_models.Payment.invoice_id == invoice.id)
        .scalar()
    )
    if total_paid >= invoice.amount:
        invoice.is_paid = True
        invoice.updated_by = current_user.id

        dimensions = {"item": "harvest_sale"}
        if order.farm_id:
            dimensions["farm_id"] = order.farm_id
        if order.season_id:
            dimensions["season_id"] = order.season_id
        if order.harvest_lot_id:
            dimensions["harvest_lot_id"] = order.harvest_lot_id
        post_ledger_entry(
            db, tenant_id=current_user.tenant_id, entry_type="receipt", direction="revenue",
            amount=invoice.amount, dimensions=dimensions, source_type="sales_invoice", source_id=invoice.id,
            notes=f"Payment in full for {invoice.invoice_number}", posted_by=current_user.id,
        )

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="sales_payment.record", entity_type="sales_payment", entity_id=payment.id,
        new_values={"invoice_id": invoice.id, "amount": payment.amount, "invoice_fully_paid": invoice.is_paid},
    )
    db.commit()
    return payment


@router.get("/invoices/{invoice_id}/payments", response_model=list[sales_schemas.PaymentOut])
def list_payments(
    invoice_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("sales.order.view")),
):
    invoice = _get_or_404(db, sales_models.Invoice, invoice_id, "Invoice")
    order = _get_or_404(db, sales_models.SalesOrder, invoice.order_id, "Sales order")
    _assert_optional_farm_scope(db, user, "sales.order.view", order.farm_id)
    return db.query(sales_models.Payment).filter(sales_models.Payment.invoice_id == invoice_id).order_by(sales_models.Payment.paid_at.asc()).all()
