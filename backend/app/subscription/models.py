"""Subscription & Plans (master-prompt integration §37, Phase 21) - the
SaaS-entitlement layer: which `Plan` a tenant is on, and what that plan
limits. No payment processing lives here or anywhere in this codebase -
`price_per_month` is informational/pricing-page content only; an actual
charge is explicitly out of scope for this assistant to build or execute.

`Plan` is a global catalog, same shape as `foundation.models.Permission`
(seeded once via `ensure_plan_catalog`, not per-tenant). `Subscription` is
one row per tenant - like `crm.models.Customer`, it is deliberately NOT
`TenantScopedMixin`/RLS-protected: it's the vendor's own billing record
*about* a tenant, and platform staff need to list/manage it across every
tenant, which RLS would prevent.

Every tenant gets a `Subscription` automatically at provisioning time
(`foundation.seed.provision_tenant` -> `seed_default_subscription`), on
the "free" plan with a 14-day trial - the same "structural, not
optional" seeding pattern already used for RBAC roles and mandatory
approval workflows, so there's no tenant without one to report usage
against.

Enforcement (actually blocking a tenant from exceeding `farm_limit`, say)
is deliberately NOT wired into `farm.py`/`users.py`/`iot.py`'s create
endpoints this pass - see docs/05-RTM.md's Phase 21 checklist for why.
`GET /api/v1/subscriptions/me` reports real current usage against real
limits; nothing currently blocks on it.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..foundation.models import gen_uuid

PLAN_CODES = ("free", "farm", "pro", "enterprise")
SUBSCRIPTION_STATUSES = ("trialing", "active", "past_due", "cancelled")


def _uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)


class Plan(Base):
    __tablename__ = "subscription_plans"

    id: Mapped[str] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    price_per_month: Mapped[float] = mapped_column(Float, default=0.0)
    farm_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    user_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sensor_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    features: Mapped[list] = mapped_column(JSONB, default=list)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = _uuid_pk()
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), unique=True, index=True)
    plan_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("subscription_plans.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="trialing")
    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
