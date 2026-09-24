from datetime import datetime, timedelta, timezone

from app.subscription import models as sub_models
from app.subscription.service import check_trial_expirations


def _subscription_for(raw_db, tenant_id: str) -> sub_models.Subscription:
    return raw_db.query(sub_models.Subscription).filter(sub_models.Subscription.tenant_id == tenant_id).one()


def test_check_trial_expirations_moves_expired_trial_to_past_due(client, tenant, raw_db):
    subscription = _subscription_for(raw_db, tenant.tenant_id)
    assert subscription.status == "trialing"
    subscription.trial_ends_at = datetime.now(timezone.utc) - timedelta(days=1)
    raw_db.commit()

    expired = check_trial_expirations(raw_db)
    assert tenant.tenant_id in [s.tenant_id for s in expired]

    raw_db.refresh(subscription)
    assert subscription.status == "past_due"


def test_check_trial_expirations_ignores_trials_not_yet_ended(client, tenant, raw_db):
    subscription = _subscription_for(raw_db, tenant.tenant_id)
    assert subscription.trial_ends_at > datetime.now(timezone.utc)  # seeded 14 days out (Phase 21 default)

    expired = check_trial_expirations(raw_db)
    assert tenant.tenant_id not in [s.tenant_id for s in expired]

    raw_db.refresh(subscription)
    assert subscription.status == "trialing"


def test_check_trial_expirations_ignores_non_trialing_subscriptions(client, tenant, raw_db):
    subscription = _subscription_for(raw_db, tenant.tenant_id)
    subscription.status = "active"
    subscription.trial_ends_at = datetime.now(timezone.utc) - timedelta(days=1)
    raw_db.commit()

    expired = check_trial_expirations(raw_db)
    assert tenant.tenant_id not in [s.tenant_id for s in expired]

    raw_db.refresh(subscription)
    assert subscription.status == "active"


def test_check_trial_expirations_is_idempotent(client, tenant, raw_db):
    subscription = _subscription_for(raw_db, tenant.tenant_id)
    subscription.trial_ends_at = datetime.now(timezone.utc) - timedelta(days=1)
    raw_db.commit()

    first = check_trial_expirations(raw_db)
    assert tenant.tenant_id in [s.tenant_id for s in first]

    second = check_trial_expirations(raw_db)
    assert tenant.tenant_id not in [s.tenant_id for s in second]
