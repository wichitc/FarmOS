from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..config import settings
from ..farm import models as farm_models
from ..foundation import models as fm
from ..iot import models as iot_models
from . import models as sub_models

PLAN_CATALOG: list[tuple[str, str, float, Optional[int], Optional[int], Optional[int], list[str]]] = [
    # code, name, price_per_month, farm_limit, user_limit, sensor_limit, features
    ("free", "Free", 0.0, 1, 3, 5, ["farm_management", "basic_dashboard"]),
    ("farm", "Farm", 990.0, 3, 10, 25, ["farm_management", "dashboard", "irrigation", "reporting"]),
    ("pro", "Pro", 2990.0, 10, 30, 100, ["farm_management", "dashboard", "irrigation", "reporting", "ai_copilot", "ai_agents"]),
    ("enterprise", "Enterprise", 0.0, None, None, None, ["farm_management", "dashboard", "irrigation", "reporting", "ai_copilot", "ai_agents", "api_access", "priority_support"]),
]

TRIAL_DAYS = 14


def ensure_plan_catalog(db: Session) -> dict[str, sub_models.Plan]:
    """Idempotent, global - same shape as `foundation.seed.ensure_permission_catalog`."""
    existing = {p.code: p for p in db.query(sub_models.Plan).all()}
    for code, name, price, farm_limit, user_limit, sensor_limit, features in PLAN_CATALOG:
        if code not in existing:
            plan = sub_models.Plan(
                code=code, name=name, price_per_month=price,
                farm_limit=farm_limit, user_limit=user_limit, sensor_limit=sensor_limit, features=features,
            )
            db.add(plan)
            existing[code] = plan
    db.flush()
    return existing


def seed_default_subscription(db: Session, tenant_id: str) -> sub_models.Subscription:
    plans = ensure_plan_catalog(db)
    subscription = sub_models.Subscription(
        tenant_id=tenant_id,
        plan_id=plans["free"].id,
        status="trialing",
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=TRIAL_DAYS),
    )
    db.add(subscription)
    db.flush()
    return subscription


class PlanLimitExceeded(Exception):
    """Raised by `enforce_limit` when creating one more `resource` row
    would exceed the tenant's plan limit - callers translate this into a
    402 (master-prompt integration, Phase 29: the enforcement half of
    Phase 21's usage-vs-limits reporting, previously advisory-only)."""

    def __init__(self, resource: str, used: int, limit: int):
        self.resource = resource
        self.used = used
        self.limit = limit
        super().__init__(f"Plan limit reached for {resource}: {used}/{limit}")


@dataclass
class UsageLine:
    resource: str
    used: int
    limit: Optional[int]
    over_limit: bool


@dataclass
class SubscriptionUsage:
    subscription: sub_models.Subscription
    plan: sub_models.Plan
    usage: list[UsageLine]


def get_usage(db: Session, tenant_id: str) -> Optional[SubscriptionUsage]:
    subscription = db.query(sub_models.Subscription).filter(sub_models.Subscription.tenant_id == tenant_id).first()
    if subscription is None:
        return None
    plan = db.get(sub_models.Plan, subscription.plan_id)

    farm_count = db.query(farm_models.Farm).filter(farm_models.Farm.tenant_id == tenant_id).count()
    user_count = db.query(fm.User).filter(fm.User.tenant_id == tenant_id).count()
    sensor_count = db.query(iot_models.IotDevice).filter(iot_models.IotDevice.tenant_id == tenant_id).count()

    lines = [
        UsageLine("farms", farm_count, plan.farm_limit, plan.farm_limit is not None and farm_count > plan.farm_limit),
        UsageLine("users", user_count, plan.user_limit, plan.user_limit is not None and user_count > plan.user_limit),
        UsageLine("sensors", sensor_count, plan.sensor_limit, plan.sensor_limit is not None and sensor_count > plan.sensor_limit),
    ]
    return SubscriptionUsage(subscription=subscription, plan=plan, usage=lines)


def enforce_limit(db: Session, tenant_id: str, resource: str) -> None:
    """Raises `PlanLimitExceeded` if the tenant is already at its plan's
    limit for `resource` ("farms"/"users"/"sensors") - called by a create
    endpoint *before* inserting the new row, so the (n+1)th row is what
    gets blocked, not silently allowed past the limit. A missing
    subscription (shouldn't happen - seeded at provisioning, Phase 21)
    fails open rather than blocking creation on an unrelated data gap.
    """
    if not settings.subscription_enforcement_enabled:
        return
    usage = get_usage(db, tenant_id)
    if usage is None:
        return
    line = next((l for l in usage.usage if l.resource == resource), None)
    if line is None or line.limit is None:
        return
    if line.used >= line.limit:
        raise PlanLimitExceeded(resource, line.used, line.limit)


def check_trial_expirations(db: Session) -> list[sub_models.Subscription]:
    """Master-prompt integration, Phase 34: `trial_ends_at` passing has
    had no automatic consequence since Phase 21 - flagged explicitly as
    a deferral at the time. Moves an expired trial to `"past_due"`
    (already in `SUBSCRIPTION_STATUSES`, not a new status invented for
    this) rather than `"cancelled"` - the tenant didn't cancel anything,
    their trial simply ran out with no payment behind it, which is what
    `past_due` already means. Naturally idempotent: once `status` moves
    off `"trialing"` a subscription is never selected by this query
    again, no separate marker column needed (unlike `SupportTicket.
    sla_breached_at`, which has to persist a permanent "was breached"
    fact even after the ticket resolves - a subscription's status *is*
    that fact here).

    No behavioral enforcement is wired to `"past_due"` yet - this only
    makes the status honest; see the RTM deferral note.
    """
    now = datetime.now(timezone.utc)
    expired = (
        db.query(sub_models.Subscription)
        .filter(
            sub_models.Subscription.status == "trialing",
            sub_models.Subscription.trial_ends_at.isnot(None),
            sub_models.Subscription.trial_ends_at < now,
        )
        .all()
    )
    for subscription in expired:
        subscription.status = "past_due"
    db.commit()
    return expired
