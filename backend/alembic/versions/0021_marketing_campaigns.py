"""Marketing: Campaigns & Coupons (master-prompt integration §9, Phase
22): completes the vendor CRM module's three-way split (pipeline /
support / marketing). `crm_leads.campaign_id` is the attribution link,
added to the existing table.

Revision ID: 0021
Revises: 0020
Create Date: 2027-01-18 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0021"
down_revision = "0020"
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
        "crm_campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False, server_default="other"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("budget", sa.Float, nullable=True),
        sa.Column("utm_source", sa.String(length=100), nullable=True),
        sa.Column("utm_medium", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        *_standard_columns(),
    )

    op.create_table(
        "crm_coupons",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False, unique=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("discount_type", sa.String(length=10), nullable=False, server_default="percent"),
        sa.Column("discount_value", sa.Float, nullable=False),
        sa.Column("applies_to_plan_code", sa.String(length=20), nullable=True),
        sa.Column("valid_from", sa.Date, nullable=True),
        sa.Column("valid_to", sa.Date, nullable=True),
        sa.Column("max_redemptions", sa.Integer, nullable=True),
        sa.Column("redemption_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *_standard_columns(),
    )

    op.add_column("crm_leads", sa.Column("campaign_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("crm_campaigns.id"), nullable=True))


def downgrade() -> None:
    op.drop_column("crm_leads", "campaign_id")
    op.drop_table("crm_coupons")
    op.drop_table("crm_campaigns")
