from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...core.deps import get_current_user, require_platform_super_admin, set_tenant_context
from ...database import get_db
from ...foundation import models as fm
from ...foundation.audit import record_audit
from ...subscription import models as sub_models
from ...subscription import schemas as sub_schemas
from ...subscription import service as sub_service

router = APIRouter(prefix="/api/v1/subscriptions", tags=["subscription"])


def _get_or_404(db: Session, model, obj_id: str, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


def _usage_out(usage: sub_service.SubscriptionUsage) -> sub_schemas.SubscriptionUsageOut:
    return sub_schemas.SubscriptionUsageOut(
        subscription=sub_schemas.SubscriptionOut.model_validate(usage.subscription),
        plan=sub_schemas.PlanOut.model_validate(usage.plan),
        usage=[sub_schemas.UsageLineOut(**vars(line)) for line in usage.usage],
    )


@router.get("/plans", response_model=list[sub_schemas.PlanOut])
def list_plans(db: Session = Depends(get_db)):
    """Public - pricing-page content (master prompt §37). Ensures the
    catalog exists rather than assuming some tenant has already been
    provisioned (the only other place that seeds it): a pricing page must
    work before a single tenant does."""
    sub_service.ensure_plan_catalog(db)
    db.commit()
    return db.query(sub_models.Plan).order_by(sub_models.Plan.price_per_month.asc()).all()


@router.get("/me", response_model=sub_schemas.SubscriptionUsageOut)
def get_my_subscription(
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(get_current_user),
):
    usage = sub_service.get_usage(db, current_user.tenant_id)
    if usage is None:
        raise HTTPException(status_code=404, detail="No subscription found for this tenant")
    return _usage_out(usage)


@router.get("/{tenant_id}", response_model=sub_schemas.SubscriptionUsageOut)
def get_tenant_subscription(
    tenant_id: str,
    db: Session = Depends(get_db),
    _admin: fm.User = Depends(require_platform_super_admin),
):
    _get_or_404(db, fm.Tenant, tenant_id, "Tenant")
    # Farm/User/IotDevice counts are RLS-protected by the *target* tenant,
    # not the admin's own - re-point this transaction's context the same
    # way `foundation.seed.provision_tenant` does when writing into a
    # tenant other than the caller's own.
    set_tenant_context(db, tenant_id)
    usage = sub_service.get_usage(db, tenant_id)
    if usage is None:
        raise HTTPException(status_code=404, detail="No subscription found for this tenant")
    return _usage_out(usage)


@router.post("/{tenant_id}/change-plan", response_model=sub_schemas.SubscriptionOut)
def change_plan(
    tenant_id: str,
    payload: sub_schemas.ChangePlanRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_platform_super_admin),
):
    _get_or_404(db, fm.Tenant, tenant_id, "Tenant")
    plan = db.query(sub_models.Plan).filter(sub_models.Plan.code == payload.plan_code).first()
    if plan is None:
        raise HTTPException(status_code=422, detail=f"Unknown plan '{payload.plan_code}'")
    subscription = db.query(sub_models.Subscription).filter(sub_models.Subscription.tenant_id == tenant_id).first()
    if subscription is None:
        raise HTTPException(status_code=404, detail="No subscription found for this tenant")
    if subscription.status == "cancelled":
        raise HTTPException(status_code=409, detail="Cannot change the plan of a cancelled subscription")

    old_plan_id = subscription.plan_id
    subscription.plan_id = plan.id
    if subscription.status == "trialing":
        subscription.status = "active"
    subscription.updated_at = datetime.now(timezone.utc)

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="subscription.change_plan", entity_type="subscription", entity_id=subscription.id,
        old_values={"plan_id": old_plan_id}, new_values={"plan_id": plan.id, "target_tenant_id": tenant_id},
    )
    db.commit()
    return subscription


@router.post("/{tenant_id}/cancel", response_model=sub_schemas.SubscriptionOut)
def cancel_subscription(
    tenant_id: str,
    payload: sub_schemas.CancelSubscriptionRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_platform_super_admin),
):
    _get_or_404(db, fm.Tenant, tenant_id, "Tenant")
    subscription = db.query(sub_models.Subscription).filter(sub_models.Subscription.tenant_id == tenant_id).first()
    if subscription is None:
        raise HTTPException(status_code=404, detail="No subscription found for this tenant")
    if subscription.status == "cancelled":
        raise HTTPException(status_code=409, detail="Subscription is already cancelled")

    subscription.status = "cancelled"
    subscription.cancelled_at = datetime.now(timezone.utc)
    subscription.updated_at = datetime.now(timezone.utc)

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="subscription.cancel", entity_type="subscription", entity_id=subscription.id,
        new_values={"target_tenant_id": tenant_id}, reason=payload.reason,
    )
    db.commit()
    return subscription
