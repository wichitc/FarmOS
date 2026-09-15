from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr


class LeadCapture(BaseModel):
    """Public, unauthenticated - the landing-page contact form (master
    prompt §36)."""

    name: str
    company: Optional[str] = None
    email: EmailStr
    phone: Optional[str] = None
    farm_type: Optional[str] = None
    farm_area_rai: Optional[float] = None
    interest: Optional[str] = None
    message: Optional[str] = None


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
