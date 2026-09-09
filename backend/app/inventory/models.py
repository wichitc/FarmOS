"""Inventory & Procurement (Phase 13, FR-INV / FR-PROC) - see
docs/03-BRD.md §14.

FR-INV-001's full feature list (item master, UOM, warehouse/bin, lot/
expiry, receipt/issue/transfer/return/adjustment/cycle-count, reservation,
min/max reorder, valuation) is delivered via a five-entity core rather than
a table per movement type: `StockMovement.movement_type` is the enum
(`receipt`/`issue`/`transfer`/`return`/`adjustment`/`cycle_count`), and
`StockLot` carries the current on-hand balance + expiry + unit cost
(valuation) per lot - same "generic type column over parallel tables"
principle ADR-004 already established for twins.

FR-PROC-001's `Purchase Request -> Approval -> RFQ -> Vendor Comparison ->
PO -> Receiving -> Inspection -> Inventory -> Invoice Matching` pipeline is
collapsed to `PurchaseRequest` (approval-gated, same pattern as every
Phase 8/10/12 plan) -> `PurchaseOrder` (the Approved Action, carrying
receiving/inspection/invoice fields directly rather than three more
tables - RFQ/Vendor Comparison is a pre-PO negotiation process with no
persistent state of its own to model here). A passed receipt on a
`PurchaseOrder` creates the `StockLot`/`StockMovement` automatically,
closing the pipeline into real inventory.
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..foundation.models import TenantScopedMixin, gen_uuid

ITEM_CATEGORIES = ("fertilizer", "chemical", "spare_part", "fuel", "lubricant", "tool", "ppe", "packaging", "other")
MOVEMENT_TYPES = ("receipt", "issue", "transfer", "return", "adjustment", "cycle_count")
MOVEMENT_REFERENCE_TYPES = ("work_order", "farm_task", "plot", "asset", "crop", "season")
REQUEST_STATUSES = ("draft", "pending_approval", "approved", "rejected", "converted", "cancelled")
PO_STATUSES = ("issued", "receiving", "received", "invoiced", "cancelled")


def _uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)


class Item(TenantScopedMixin, Base):
    __tablename__ = "inventory_items"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_inventory_items_tenant_code"),)

    id: Mapped[str] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(20))
    uom: Mapped[str] = mapped_column(String(20))
    min_qty: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_qty: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Warehouse(TenantScopedMixin, Base):
    __tablename__ = "warehouses"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_warehouses_tenant_code"),)

    id: Mapped[str] = _uuid_pk()
    farm_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(255))
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class StockLot(TenantScopedMixin, Base):
    """Current on-hand balance per lot - updated transactionally alongside
    each `StockMovement`, not derived on read, so a valuation/reorder query
    doesn't have to replay the whole movement history."""

    __tablename__ = "stock_lots"

    id: Mapped[str] = _uuid_pk()
    item_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("inventory_items.id"), index=True)
    warehouse_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("warehouses.id"), index=True)
    lot_code: Mapped[str] = mapped_column(String(100))
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    unit_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StockMovement(TenantScopedMixin, Base):
    """Append-only audit trail (BR-004-style: no update/delete route
    exposed). `reference_type`/`reference_id` is FR-INV-002's generic cost-
    attribution link (Work Order, Farm Task, Plot, Asset, Crop, Season) -
    one pair of columns rather than six nullable FKs, same pattern as
    `Alert.entity_type`/`entity_id` (Phase 7). `farm_task` has no backing
    table yet (FR-WORK, Phase 17) so `reference_id` is just an opaque
    string in that case, same treatment as every other FR-WORK gap so far."""

    __tablename__ = "stock_movements"

    id: Mapped[str] = _uuid_pk()
    lot_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("stock_lots.id"), index=True)
    movement_type: Mapped[str] = mapped_column(String(20), index=True)
    quantity_delta: Mapped[float] = mapped_column(Float)
    reference_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    reference_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    from_warehouse_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("warehouses.id"), nullable=True)
    to_warehouse_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("warehouses.id"), nullable=True)
    performed_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Vendor(TenantScopedMixin, Base):
    __tablename__ = "vendors"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_vendors_tenant_code"),)

    id: Mapped[str] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(255))
    contact_info: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PurchaseRequest(TenantScopedMixin, Base):
    __tablename__ = "purchase_requests"

    id: Mapped[str] = _uuid_pk()
    item_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("inventory_items.id"), index=True)
    farm_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), nullable=True, index=True)
    quantity: Mapped[float] = mapped_column(Float)
    needed_by: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    workflow_instance_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("workflow_instances.id"), nullable=True)
    requested_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)


class PurchaseOrder(TenantScopedMixin, Base):
    """The Approved Action - only ever created by converting an `approved`
    `PurchaseRequest` (mirrors `WorkOrder` in Phase 12). Receiving/
    inspection/invoice fields live here directly rather than in three more
    tables, per this module's docstring."""

    __tablename__ = "purchase_orders"

    id: Mapped[str] = _uuid_pk()
    request_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("purchase_requests.id"), index=True)
    vendor_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("vendors.id"), index=True)
    item_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("inventory_items.id"), index=True)
    farm_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), nullable=True, index=True)
    po_number: Mapped[str] = mapped_column(String(30))
    quantity: Mapped[float] = mapped_column(Float)
    unit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="issued")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Receiving + inspection
    received_quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    inspection_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    inspection_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    warehouse_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("warehouses.id"), nullable=True)
    resulting_lot_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("stock_lots.id"), nullable=True)
    # Invoice matching
    invoice_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    invoice_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    invoice_matched: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
