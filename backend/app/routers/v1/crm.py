from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...core.deps import get_current_user, require_platform_super_admin
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


# ---------------------------------------------------------------------------
# Support tickets (master prompt §11, Phase 20 follow-on). Unlike the
# pipeline above, an ordinary authenticated tenant user (not just platform
# staff) can create a ticket and reply on their own tenant's tickets -
# `_assert_ticket_access` is the code-level "your own tenant, or all of
# them if you're platform staff" check that stands in for RLS here (see
# `crm/models.py`'s module docstring for why this table isn't RLS-scoped).
# ---------------------------------------------------------------------------

def _assert_ticket_access(user: fm.User, ticket: crm_models.SupportTicket) -> None:
    if user.is_platform_super_admin:
        return
    if ticket.tenant_id == user.tenant_id:
        return
    raise HTTPException(status_code=403, detail="Not your organization's ticket")


@router.post("/tickets", response_model=crm_schemas.TicketOut, status_code=201)
def create_ticket(
    payload: crm_schemas.TicketCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(get_current_user),
):
    if payload.category not in crm_models.TICKET_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Unknown category '{payload.category}'")
    if payload.priority not in crm_models.TICKET_PRIORITIES:
        raise HTTPException(status_code=422, detail=f"Unknown priority '{payload.priority}'")

    customer = db.query(crm_models.Customer).filter(crm_models.Customer.tenant_id == current_user.tenant_id).first()
    sla_hours = crm_models.TICKET_SLA_HOURS[payload.priority]

    ticket = crm_models.SupportTicket(
        tenant_id=current_user.tenant_id,
        customer_id=customer.id if customer else None,
        requester_name=current_user.full_name,
        requester_email=current_user.email,
        subject=payload.subject,
        category=payload.category,
        priority=payload.priority,
        status="open",
        sla_due_at=datetime.now(timezone.utc) + timedelta(hours=sla_hours),
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(ticket)
    db.flush()

    db.add(
        crm_models.TicketMessage(
            ticket_id=ticket.id, author_type="customer", author_user_id=current_user.id,
            author_name=current_user.full_name, body=payload.message,
        )
    )

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="crm_ticket.create", entity_type="crm_support_ticket", entity_id=ticket.id,
        new_values={"subject": ticket.subject, "priority": ticket.priority},
    )
    db.commit()
    return ticket


@router.get("/tickets", response_model=list[crm_schemas.TicketOut])
def list_tickets(
    status: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(get_current_user),
):
    query = db.query(crm_models.SupportTicket)
    if not current_user.is_platform_super_admin:
        query = query.filter(crm_models.SupportTicket.tenant_id == current_user.tenant_id)
    if status:
        query = query.filter(crm_models.SupportTicket.status == status)
    if priority:
        query = query.filter(crm_models.SupportTicket.priority == priority)
    return query.order_by(crm_models.SupportTicket.created_at.desc()).all()


@router.get("/tickets/{ticket_id}", response_model=crm_schemas.TicketOut)
def get_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(get_current_user),
):
    ticket = _get_or_404(db, crm_models.SupportTicket, ticket_id, "Ticket")
    _assert_ticket_access(current_user, ticket)
    return ticket


@router.patch("/tickets/{ticket_id}", response_model=crm_schemas.TicketOut)
def update_ticket(
    ticket_id: str,
    payload: crm_schemas.TicketUpdate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_platform_super_admin),
):
    """Status/priority/assignment changes are platform-staff actions -
    a customer's own input happens via replying on the ticket, not by
    directly setting its status."""
    ticket = _get_or_404(db, crm_models.SupportTicket, ticket_id, "Ticket")
    if payload.priority is not None and payload.priority not in crm_models.TICKET_PRIORITIES:
        raise HTTPException(status_code=422, detail=f"Unknown priority '{payload.priority}'")
    if payload.status is not None and payload.status not in crm_models.TICKET_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown status '{payload.status}'")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(ticket, field, value)
    if payload.status == "resolved" and ticket.resolved_at is None:
        ticket.resolved_at = datetime.now(timezone.utc)
    ticket.updated_by = current_user.id
    db.flush()

    record_audit(
        db, tenant_id=current_user.tenant_id, actor_user_id=current_user.id,
        action="crm_ticket.update", entity_type="crm_support_ticket", entity_id=ticket.id,
        new_values=changes,
    )
    db.commit()
    return ticket


@router.post("/tickets/{ticket_id}/messages", response_model=crm_schemas.TicketMessageOut, status_code=201)
def add_ticket_message(
    ticket_id: str,
    payload: crm_schemas.TicketMessageCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(get_current_user),
):
    ticket = _get_or_404(db, crm_models.SupportTicket, ticket_id, "Ticket")
    _assert_ticket_access(current_user, ticket)

    is_agent = current_user.is_platform_super_admin
    message = crm_models.TicketMessage(
        ticket_id=ticket.id,
        author_type="agent" if is_agent else "customer",
        author_user_id=current_user.id,
        author_name=current_user.full_name,
        body=payload.body,
        # Only platform staff may leave a note the customer can't see.
        is_internal_note=payload.is_internal_note if is_agent else False,
    )
    db.add(message)
    if not is_agent and ticket.status == "waiting_on_customer":
        ticket.status = "in_progress"
    ticket.updated_by = current_user.id
    db.commit()
    return message


@router.get("/tickets/{ticket_id}/messages", response_model=list[crm_schemas.TicketMessageOut])
def list_ticket_messages(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(get_current_user),
):
    ticket = _get_or_404(db, crm_models.SupportTicket, ticket_id, "Ticket")
    _assert_ticket_access(current_user, ticket)

    query = db.query(crm_models.TicketMessage).filter(crm_models.TicketMessage.ticket_id == ticket_id)
    if not current_user.is_platform_super_admin:
        # Internal notes are platform-staff-only, regardless of who else
        # can see the rest of the thread.
        query = query.filter(crm_models.TicketMessage.is_internal_note.is_(False))
    return query.order_by(crm_models.TicketMessage.created_at.asc()).all()
