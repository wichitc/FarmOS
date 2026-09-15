"""Vendor CRM (master-prompt integration): leads/customers/opportunities
for DurianOS's own customer-acquisition pipeline. Deliberately NOT in the
tenant-scoped + RLS pattern every other migration since Phase 3 follows -
these rows live above the tenant boundary (a prospect isn't a tenant
yet), same as `tenants` itself; `core.deps.require_platform_super_admin`
is the safety boundary instead of a row-level policy.

Revision ID: 0018
Revises: 0017
Create Date: 2026-12-28 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0018"
down_revision = "0017"
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
        "crm_leads",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("farm_type", sa.String(length=100), nullable=True),
        sa.Column("farm_area_rai", sa.Float, nullable=True),
        sa.Column("interest", sa.String(length=255), nullable=True),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="landing_page"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="new"),
        sa.Column("score", sa.Integer, nullable=True),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        *_standard_columns(),
    )

    op.create_table(
        "crm_customers",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("crm_leads.id"), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=True, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=False),
        sa.Column("contact_phone", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="trial"),
        *_standard_columns(),
    )

    op.create_table(
        "crm_opportunities",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("crm_leads.id"), nullable=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("crm_customers.id"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("stage", sa.String(length=20), nullable=False, server_default="pipeline"),
        sa.Column("expected_revenue", sa.Float, nullable=True),
        sa.Column("probability_pct", sa.Float, nullable=True),
        sa.Column("expected_close_date", sa.Date, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        *_standard_columns(),
    )


def downgrade() -> None:
    op.drop_table("crm_opportunities")
    op.drop_table("crm_customers")
    op.drop_table("crm_leads")
