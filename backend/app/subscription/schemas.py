from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PlanOut(BaseModel):
    id: str
    code: str
    name: str
    price_per_month: float
    farm_limit: Optional[int] = None
    user_limit: Optional[int] = None
    sensor_limit: Optional[int] = None
    features: list[str]

    model_config = ConfigDict(from_attributes=True)


class SubscriptionOut(BaseModel):
    id: str
    tenant_id: str
    plan_id: str
    status: str
    trial_ends_at: Optional[datetime] = None
    current_period_start: datetime
    current_period_end: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UsageLineOut(BaseModel):
    resource: str
    used: int
    limit: Optional[int] = None
    over_limit: bool


class SubscriptionUsageOut(BaseModel):
    subscription: SubscriptionOut
    plan: PlanOut
    usage: list[UsageLineOut]


class ChangePlanRequest(BaseModel):
    plan_code: str


class CancelSubscriptionRequest(BaseModel):
    reason: Optional[str] = None
