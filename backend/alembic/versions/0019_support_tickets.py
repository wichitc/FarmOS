"""Support tickets (master-prompt integration, Phase 20, §11): a ticket
and its conversation thread. Not RLS-protected like `crm_leads`/
`crm_customers`/`crm_opportunities` (support staff need cross-tenant
visibility, which RLS would block); `routers/v1/crm.py` enforces
"your own tenant's tickets, or all of them if you're platform staff" in
code instead.

Revision ID: 0019
Revises: 0018
Create Date: 2027-01-05 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def _standard_columns():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_by", postgresql.UUID(as_uuid=False), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "crm_support_tickets",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=True, index=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("crm_customers.id"), nullable=True),
        sa.Column("requester_name", sa.String(length=255), nullable=False),
        sa.Column("requester_email", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False, server_default="other"),
        sa.Column("priority", sa.String(length=10), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        *_standard_columns(),
    )

    op.create_table(
        "crm_ticket_messages",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("crm_support_tickets.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("author_type", sa.String(length=20), nullable=False),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("author_name", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("is_internal_note", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("crm_ticket_messages")
    op.drop_table("crm_support_tickets")
