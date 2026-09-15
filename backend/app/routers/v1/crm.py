from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...core.deps import require_platform_super_admin
from ...crm import models as crm_models
from ...crm import schemas as crm_schemas
from ...database import get_db
from ...foundation import models as fm
from ...foundation.audit import record_audit

router = APIRouter(prefix="/api/v1/crm", tags=["crm"])


def _get_or_404(db: Session, model, obj_id: str, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


# ---------------------------------------------------------------------------
# Leads (master prompt §9/§36). `capture_lead` is the one public,
# unauthenticated endpoint in this router - the landing-page contact form -
# mirroring `harvest.py`'s QR-trace endpoint as this platform's other
# precedent for a deliberately unauthenticated route. No audit entry is
# recorded for it: `record_audit` requires an active tenant RLS context
# (set by `get_current_user`, which an anonymous request never goes
# through), and there is no tenant to attribute an anonymous submission to.
# ---------------------------------------------------------------------------

@router.post("/leads", response_model=crm_schemas.LeadOut, status_code=201)
def capture_lead(payload: crm_schemas.LeadCapture, db: Session = Depends(get_db)):
    lead = crm_models.Lead(
        name=payload.name,
        company=payload.company,
        email=payload.email,
        phone=payload.phone,
        farm_type=payload.farm_type,
        farm_area_rai=payload.farm_area_rai,
        interest=payload.interest,
        message=payload.message,
        source="landing_page",
        status="new",
    )
    db.add(lead)
    db.commit()
    return lead


@router.get("/leads", response_model=list[crm_schemas.LeadOut])
def list_leads(
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _admin: fm.User = Depends(require_platform_super_admin),
):
    query = db.query(crm_models.Lead)
    if status:
        query = query.filter(crm_models.Lead.status == status)
    return query.order_by(crm_models.Lead.created_at.desc()).all()


@router.get("/leads/{lead_id}", response_model=crm_schemas.LeadOut)
def get_lead(
    lead_id: str,
    db: Session = Depends(get_db),
    _admin: fm.User = Depends(require_platform_super_admin),
):
    return _get_or_404(db, crm_models.Lead, lead_id, "Lead")


@router.patch("/leads/{lead_id}", response_model=crm_schemas.LeadOut)
def update_lead_status(
    lead_id: str,
    payload: crm_schemas.LeadStatusUpdate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_platform_super_admin),
):
    lead = _get_or_404(db, crm_models.Lead, lead_id, "Lead")
    if payload.status not in crm_models.LEAD_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown status '{payload.status}'")
    if lead.status == "converted":
        raise HTTPException(status_code=409, detail="Cannot change status of an already-converted lead")

    old_status = lead.status
    lead.status = payload.status
    if payload.score is not None:
        lead.score = payload.score
    if payload.assigned_to is not None:
        lead.assigned_to = payload.assigned_to
    lead.updated_by = current_user.id

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="crm_lead.status_update", entity_type="crm_lead", entity_id=lead.id,
        old_values={"status": old_status}, new_values={"status": lead.status},
    )
    db.commit()
    return lead


@router.post("/leads/{lead_id}/convert", response_model=crm_schemas.CustomerOut, status_code=201)
def convert_lead(
    lead_id: str,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_platform_super_admin),
):
    """Lead -> Customer (master prompt §10's pipeline). Does not itself
    provision a `Tenant` - `POST /customers/{id}/link-tenant` bridges to a
    real operational tenant once one exists (provisioned separately via
    `POST /api/v1/tenants`, same as any other tenant)."""
    lead = _get_or_404(db, crm_models.Lead, lead_id, "Lead")
    if lead.status == "converted":
        raise HTTPException(status_code=409, detail="Lead is already converted")

    customer = crm_models.Customer(
        lead_id=lead.id,
        name=lead.name,
        company=lead.company,
        contact_email=lead.email,
        contact_phone=lead.phone,
        status="trial",
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(customer)
    lead.status = "converted"
    lead.updated_by = current_user.id
    db.flush()

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="crm_lead.convert", entity_type="crm_customer", entity_id=customer.id,
        new_values={"lead_id": lead.id},
    )
    db.commit()
    return customer


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

@router.get("/customers", response_model=list[crm_schemas.CustomerOut])
def list_customers(
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _admin: fm.User = Depends(require_platform_super_admin),
):
    query = db.query(crm_models.Customer)
    if status:
        query = query.filter(crm_models.Customer.status == status)
    return query.order_by(crm_models.Customer.created_at.desc()).all()


@router.get("/customers/{customer_id}", response_model=crm_schemas.CustomerOut)
def get_customer(
    customer_id: str,
    db: Session = Depends(get_db),
    _admin: fm.User = Depends(require_platform_super_admin),
):
    return _get_or_404(db, crm_models.Customer, customer_id, "Customer")


@router.patch("/customers/{customer_id}", response_model=crm_schemas.CustomerOut)
def update_customer(
    customer_id: str,
    payload: crm_schemas.CustomerUpdate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_platform_super_admin),
):
    customer = _get_or_404(db, crm_models.Customer, customer_id, "Customer")
    if payload.status is not None:
        if payload.status not in crm_models.CUSTOMER_STATUSES:
            raise HTTPException(status_code=422, detail=f"Unknown status '{payload.status}'")
        customer.status = payload.status
    if payload.contact_phone is not None:
        customer.contact_phone = payload.contact_phone
    customer.updated_by = current_user.id
    db.commit()
    return customer


@router.post("/customers/{customer_id}/link-tenant", response_model=crm_schemas.CustomerOut)
def link_tenant(
    customer_id: str,
    payload: crm_schemas.LinkTenantRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_platform_super_admin),
):
    customer = _get_or_404(db, crm_models.Customer, customer_id, "Customer")
    if customer.tenant_id:
        raise HTTPException(status_code=409, detail="Customer is already linked to a tenant")
    _get_or_404(db, fm.Tenant, payload.tenant_id, "Tenant")
    existing = db.query(crm_models.Customer).filter(crm_models.Customer.tenant_id == payload.tenant_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="That tenant is already linked to another customer")

    customer.tenant_id = payload.tenant_id
    customer.status = "active"
    customer.updated_by = current_user.id

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="crm_customer.link_tenant", entity_type="crm_customer", entity_id=customer.id,
        new_values={"tenant_id": payload.tenant_id},
    )
    db.commit()
    return customer


# ---------------------------------------------------------------------------
# Opportunities
# ---------------------------------------------------------------------------

@router.post("/opportunities", response_model=crm_schemas.OpportunityOut, status_code=201)
def create_opportunity(
    payload: crm_schemas.OpportunityCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_platform_super_admin),
):
    if payload.stage not in crm_models.OPPORTUNITY_STAGES:
        raise HTTPException(status_code=422, detail=f"Unknown stage '{payload.stage}'")
    if payload.lead_id:
        _get_or_404(db, crm_models.Lead, payload.lead_id, "Lead")
    if payload.customer_id:
        _get_or_404(db, crm_models.Customer, payload.customer_id, "Customer")

    opportunity = crm_models.Opportunity(
        lead_id=payload.lead_id,
        customer_id=payload.customer_id,
        name=payload.name,
        stage=payload.stage,
        expected_revenue=payload.expected_revenue,
        probability_pct=payload.probability_pct,
        expected_close_date=payload.expected_close_date,
        notes=payload.notes,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(opportunity)
    db.flush()

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="crm_opportunity.create", entity_type="crm_opportunity", entity_id=opportunity.id,
        new_values={"stage": opportunity.stage, "name": opportunity.name},
    )
    db.commit()
    return opportunity


@router.get("/opportunities", response_model=list[crm_schemas.OpportunityOut])
def list_opportunities(
    stage: Optional[str] = Query(default=None),
    customer_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _admin: fm.User = Depends(require_platform_super_admin),
):
    query = db.query(crm_models.Opportunity)
    if stage:
        query = query.filter(crm_models.Opportunity.stage == stage)
    if customer_id:
        query = query.filter(crm_models.Opportunity.customer_id == customer_id)
    return query.order_by(crm_models.Opportunity.created_at.desc()).all()


@router.patch("/opportunities/{opportunity_id}", response_model=crm_schemas.OpportunityOut)
def update_opportunity(
    opportunity_id: str,
    payload: crm_schemas.OpportunityUpdate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_platform_super_admin),
):
    opportunity = _get_or_404(db, crm_models.Opportunity, opportunity_id, "Opportunity")
    if payload.stage is not None and payload.stage not in crm_models.OPPORTUNITY_STAGES:
        raise HTTPException(status_code=422, detail=f"Unknown stage '{payload.stage}'")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(opportunity, field, value)
    opportunity.updated_by = current_user.id
    db.flush()

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="crm_opportunity.update", entity_type="crm_opportunity", entity_id=opportunity.id,
        new_values=changes,
    )
    db.commit()
    return opportunity
