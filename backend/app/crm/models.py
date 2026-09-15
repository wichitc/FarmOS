"""Vendor CRM (master-prompt integration: "AI Agriculture" business
platform §9-10) - the DurianOS *vendor's* own pipeline for acquiring and
supporting farm-operator customers, not a farm's own customer/sales data
(that already exists as `app.sales`, Phase 14, scoped to one farm's
produce buyers).

Deliberately **not** `TenantScopedMixin`/RLS-protected, for the same
reason `foundation.models.Tenant` isn't: a prospect submitting the
landing-page contact form is not a tenant yet, so there is no `tenant_id`
to scope by. Safety here comes from `core.deps.require_platform_super_admin`
gating every endpoint except the one public lead-capture form (the same
split `routers/v1/tenants.py` already established for tenant
provisioning) - not from row-level security.

Pipeline (master prompt §10): Lead -> Qualified -> Demo -> Opportunity ->
Proposal -> Customer -> Subscription -> Active Farm. `Customer.tenant_id`
is the bridge: null until the customer actually provisions/is provisioned
a real operational `Tenant`, at which point `POST
/api/v1/crm/customers/{id}/link-tenant` sets it - CRM identity and
operational-platform identity are related but distinct records, not
collapsed into one.

Marketing/Campaign and Support/Ticket/Knowledge-Base (master prompt §9,
§11) are explicitly not built this pass - see docs/05-RTM.md's
completion checklist for this phase.
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..foundation.models import gen_uuid

LEAD_STATUSES = ("new", "contacted", "qualified", "demo_scheduled", "proposal", "converted", "lost")
OPPORTUNITY_STAGES = ("pipeline", "demo", "proposal", "negotiation", "won", "lost")
CUSTOMER_STATUSES = ("trial", "active", "churned")


def _uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)


class PlatformEntityMixin:
    """Same audit-field shape as `foundation.models.TenantScopedMixin`,
    minus `tenant_id` - these rows live above the tenant boundary."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)


class Lead(PlatformEntityMixin, Base):
    __tablename__ = "crm_leads"

    id: Mapped[str] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255))
    company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    farm_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    farm_area_rai: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    interest: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="landing_page")
    status: Mapped[str] = mapped_column(String(20), default="new")
    score: Mapped[Optional[int]] = mapped_column(nullable=True)
    assigned_to: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)


class Customer(PlatformEntityMixin, Base):
    __tablename__ = "crm_customers"

    id: Mapped[str] = _uuid_pk()
    lead_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("crm_leads.id"), nullable=True)
    tenant_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=True, unique=True)
    name: Mapped[str] = mapped_column(String(255))
    company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str] = mapped_column(String(255))
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="trial")


class Opportunity(PlatformEntityMixin, Base):
    __tablename__ = "crm_opportunities"

    id: Mapped[str] = _uuid_pk()
    lead_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("crm_leads.id"), nullable=True)
    customer_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("crm_customers.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    stage: Mapped[str] = mapped_column(String(20), default="pipeline")
    expected_revenue: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    probability_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    expected_close_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
