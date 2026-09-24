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

`SupportTicket`/`TicketMessage` (master prompt §11, picked up in the
Phase 20 follow-on) are the odd ones out in this module: unlike
Lead/Customer/Opportunity, a ticket's *creation* and *reply* are things an
ordinary tenant user does about their own tenant, not something only
platform staff touch. They still aren't `TenantScopedMixin`/RLS-protected
(support staff must see tickets *across* tenants, which RLS would
prevent), so `tenant_id` here is a plain nullable FK and
`routers/v1/crm.py` enforces "your own tenant's tickets, or all of them
if you're platform staff" in code instead - a documented, deliberate
exception to this platform's usual RLS-first tenant-isolation pattern,
justified by who actually needs cross-tenant visibility here.

`Campaign`/`Coupon` (master prompt §9, picked up in the Phase 22
follow-on) complete this module's three-way split from the original
prompt: Lead/Customer/Opportunity (Phase 19) is the pipeline,
SupportTicket/TicketMessage (Phase 20) is post-sale support, and these
two are pre-sale marketing/promotion data. `Lead.campaign_id` is the
attribution link ("which campaign brought this lead in"), populated
optionally at capture time - `routers/v1/crm.py::capture_lead` accepts an
optional `campaign_code` and resolves it, silently ignoring an unknown
code rather than rejecting an otherwise-valid lead over a tracking
parameter. `Coupon` is pure discount *data* (validity window, redemption
count, applicable plan) - redeeming one validates and increments a
counter, but changes no price anywhere, since no billing engine exists
in this platform to apply a discount to (see Phase 21's explicit
no-payment-processing stance).

Knowledge-Base (master prompt §11) remains explicitly not built - see
docs/05-RTM.md's completion checklist.
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..foundation.models import gen_uuid

LEAD_STATUSES = ("new", "contacted", "qualified", "demo_scheduled", "proposal", "converted", "lost")
OPPORTUNITY_STAGES = ("pipeline", "demo", "proposal", "negotiation", "won", "lost")
CUSTOMER_STATUSES = ("trial", "active", "churned")
TICKET_STATUSES = ("open", "in_progress", "waiting_on_customer", "resolved", "closed")
TICKET_PRIORITIES = ("low", "medium", "high", "urgent")
TICKET_CATEGORIES = ("billing", "technical", "feature_request", "bug", "other")
# FR-SUPPORT (indicative defaults, not a contractual SLA - same "shape
# now" treatment as health.py's threshold table): hours-to-first-response
# by priority.
TICKET_SLA_HOURS = {"urgent": 4, "high": 24, "medium": 72, "low": 168}
CAMPAIGN_CHANNELS = ("email", "social", "search", "referral", "event", "other")
CAMPAIGN_STATUSES = ("draft", "active", "paused", "completed")
COUPON_DISCOUNT_TYPES = ("percent", "fixed")


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
    campaign_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("crm_campaigns.id"), nullable=True)


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


class SupportTicket(PlatformEntityMixin, Base):
    __tablename__ = "crm_support_tickets"

    id: Mapped[str] = _uuid_pk()
    tenant_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=True, index=True)
    customer_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("crm_customers.id"), nullable=True)
    requester_name: Mapped[str] = mapped_column(String(255))
    requester_email: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(30), default="other")
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="open")
    sla_due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_to: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Master-prompt integration, Phase 33: set once by `check_sla_breaches`
    # the first time a still-open ticket is found past `sla_due_at` - the
    # watcher's idempotency marker (never reset, even if the ticket
    # later resolves) so a breach isn't re-flagged/re-processed on every
    # sweep, and staff can still see that it *was* breached after the fact.
    sla_breached_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class TicketMessage(Base):
    """Append-only conversation thread - no update/delete route, same
    shape as `TwinEvent`/`AuditEntry`."""

    __tablename__ = "crm_ticket_messages"

    id: Mapped[str] = _uuid_pk()
    ticket_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("crm_support_tickets.id", ondelete="CASCADE"), index=True)
    author_type: Mapped[str] = mapped_column(String(20))  # "customer" | "agent" | "system"
    author_user_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    author_name: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    is_internal_note: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # File attachment (master-prompt integration, Phase 39, SEC-005) -
    # at most one per message, nullable. `attachment_object_key` is the
    # MinIO object key, never exposed to callers directly - downloads go
    # through a short-lived presigned URL (`GET .../attachment`), not a
    # raw key.
    attachment_object_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    attachment_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    attachment_content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    attachment_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class Campaign(PlatformEntityMixin, Base):
    __tablename__ = "crm_campaigns"

    id: Mapped[str] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    channel: Mapped[str] = mapped_column(String(20), default="other")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    budget: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    utm_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    utm_medium: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Coupon(PlatformEntityMixin, Base):
    """Pure discount data - see this module's docstring for why redeeming
    one changes no price anywhere."""

    __tablename__ = "crm_coupons"

    id: Mapped[str] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(50), unique=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    discount_type: Mapped[str] = mapped_column(String(10), default="percent")
    discount_value: Mapped[float] = mapped_column(Float)
    applies_to_plan_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    max_redemptions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    redemption_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
