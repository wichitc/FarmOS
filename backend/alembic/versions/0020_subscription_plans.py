"""Subscription & Plans (master-prompt integration §37, Phase 21):
`subscription_plans` (global catalog, seeded like `permissions`) and
`subscriptions` (one per tenant, seeded at provisioning time like
mandatory approval workflows). Neither is RLS-protected - `Plan` is a
global catalog like `Permission`; `Subscription` is the vendor's own
billing record about a tenant, same non-RLS treatment as `crm_customers`.

Revision ID: 0020
Revises: 0019
Create Date: 2027-01-12 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscription_plans",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("code", sa.String(length=20), nullable=False, unique=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("price_per_month", sa.Float, nullable=False, server_default="0"),
        sa.Column("farm_limit", sa.Integer, nullable=True),
        sa.Column("user_limit", sa.Integer, nullable=True),
        sa.Column("sensor_limit", sa.Integer, nullable=True),
        sa.Column("features", postgresql.JSONB, nullable=False, server_default="[]"),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, unique=True, index=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("subscription_plans.id"), nullable=False, index=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="trialing"),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("subscriptions")
    op.drop_table("subscription_plans")
