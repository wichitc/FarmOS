from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr


class LeadCapture(BaseModel):
    """Public, unauthenticated - the landing-page contact form (master
    prompt §36). `campaign_code` is optional attribution (a UTM-style
    tracking parameter, e.g. from a campaign landing page) - an unknown
    code is ignored rather than rejecting an otherwise-valid lead."""

    name: str
    company: Optional[str] = None
    email: EmailStr
    phone: Optional[str] = None
    farm_type: Optional[str] = None
    farm_area_rai: Optional[float] = None
    interest: Optional[str] = None
    message: Optional[str] = None
    campaign_code: Optional[str] = None


class LeadOut(BaseModel):
    id: str
    name: str
    company: Optional[str] = None
    email: str
    phone: Optional[str] = None
    farm_type: Optional[str] = None
    farm_area_rai: Optional[float] = None
    interest: Optional[str] = None
    message: Optional[str] = None
    source: str
    status: str
    score: Optional[int] = None
    assigned_to: Optional[str] = None
    campaign_id: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeadStatusUpdate(BaseModel):
    status: str
    score: Optional[int] = None
    assigned_to: Optional[str] = None


class CustomerOut(BaseModel):
    id: str
    lead_id: Optional[str] = None
    tenant_id: Optional[str] = None
    name: str
    company: Optional[str] = None
    contact_email: str
    contact_phone: Optional[str] = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerUpdate(BaseModel):
    status: Optional[str] = None
    contact_phone: Optional[str] = None


class LinkTenantRequest(BaseModel):
    tenant_id: str


class OpportunityCreate(BaseModel):
    lead_id: Optional[str] = None
    customer_id: Optional[str] = None
    name: str
    stage: str = "pipeline"
    expected_revenue: Optional[float] = None
    probability_pct: Optional[float] = None
    expected_close_date: Optional[date] = None
    notes: Optional[str] = None


class OpportunityUpdate(BaseModel):
    stage: Optional[str] = None
    expected_revenue: Optional[float] = None
    probability_pct: Optional[float] = None
    expected_close_date: Optional[date] = None
    notes: Optional[str] = None


class OpportunityOut(BaseModel):
    id: str
    lead_id: Optional[str] = None
    customer_id: Optional[str] = None
    name: str
    stage: str
    expected_revenue: Optional[float] = None
    probability_pct: Optional[float] = None
    expected_close_date: Optional[date] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TicketCreate(BaseModel):
    subject: str
    category: str = "other"
    priority: str = "medium"
    message: str


class TicketOut(BaseModel):
    id: str
    tenant_id: Optional[str] = None
    customer_id: Optional[str] = None
    requester_name: str
    requester_email: str
    subject: str
    category: str
    priority: str
    status: str
    sla_due_at: Optional[datetime] = None
    assigned_to: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TicketUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_to: Optional[str] = None


class TicketMessageCreate(BaseModel):
    body: str
    is_internal_note: bool = False


class TicketMessageOut(BaseModel):
    id: str
    ticket_id: str
    author_type: str
    author_user_id: Optional[str] = None
    author_name: str
    body: str
    is_internal_note: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CampaignCreate(BaseModel):
    code: str
    name: str
    channel: str = "other"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    budget: Optional[float] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    notes: Optional[str] = None


class CampaignUpdate(BaseModel):
    status: Optional[str] = None
    end_date: Optional[date] = None
    budget: Optional[float] = None
    notes: Optional[str] = None


class CampaignOut(BaseModel):
    id: str
    code: str
    name: str
    channel: str
    status: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    budget: Optional[float] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CouponCreate(BaseModel):
    code: str
    description: Optional[str] = None
    discount_type: str = "percent"
    discount_value: float
    applies_to_plan_code: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    max_redemptions: Optional[int] = None


class CouponOut(BaseModel):
    id: str
    code: str
    description: Optional[str] = None
    discount_type: str
    discount_value: float
    applies_to_plan_code: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    max_redemptions: Optional[int] = None
    redemption_count: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CouponRedeemResponse(BaseModel):
    coupon: CouponOut
    discount_type: str
    discount_value: float
