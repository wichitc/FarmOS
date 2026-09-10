"""Sales & Customer (Phase 14-adjacent, FR-SALES) - see docs/03-BRD.md §16.

FR-SALES-001's `Customer, Contract, Quotation, Sales Order, Delivery,
Invoice, Payment` list is collapsed to `Customer` -> `SalesOrder`
(`status` covers confirmed/delivered the way `SalesOrder.status` does
elsewhere in this codebase's collapsed pipelines) -> `Invoice` -> `Payment`
- Contract/Quotation/Delivery have no persistent state distinct from what
`SalesOrder.status` already carries, same reasoning Phase 13 used to skip
separate RFQ/Vendor-Comparison tables. This is the lowest-priority
requirement built so far (`C`, not `S`/`M`), so the collapse is even more
justified here than in earlier phases.

A `SalesOrder` is single-line (one `harvest_lot_id` + quantity + price),
matching the proportions of `PurchaseRequest` (Phase 13) and
`IrrigationPlan` (Phase 8) rather than a full multi-line order.
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..foundation.models import TenantScopedMixin, gen_uuid

ORDER_STATUSES = ("draft", "confirmed", "delivered", "invoiced", "cancelled")


def _uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)


class Customer(TenantScopedMixin, Base):
    __tablename__ = "customers"

    id: Mapped[str] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(255))
    contact_info: Mapped[dict] = mapped_column(JSONB, default=dict)


class SalesOrder(TenantScopedMixin, Base):
    __tablename__ = "sales_orders"

    id: Mapped[str] = _uuid_pk()
    customer_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("customers.id"), index=True)
    farm_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), nullable=True, index=True)
    season_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("seasons.id"), nullable=True)
    harvest_lot_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("harvest_lots.id"), nullable=True)
    quantity_kg: Mapped[float] = mapped_column(Float)
    unit_price: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    order_date: Mapped[date] = mapped_column(Date)


class Invoice(TenantScopedMixin, Base):
    __tablename__ = "sales_invoices"

    id: Mapped[str] = _uuid_pk()
    order_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("sales_orders.id"), index=True)
    invoice_number: Mapped[str] = mapped_column(String(30))
    amount: Mapped[float] = mapped_column(Float)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)


class Payment(TenantScopedMixin, Base):
    __tablename__ = "sales_payments"

    id: Mapped[str] = _uuid_pk()
    invoice_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("sales_invoices.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    method: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
