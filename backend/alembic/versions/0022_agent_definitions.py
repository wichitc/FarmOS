"""Agent taxonomy registry (master-prompt integration §28, Phase 24
follow-on): `agent_definitions`, the eleven named agents (Farm Manager,
Crop, Weather, Soil, Irrigation, Fertilizer, Disease, Pest, Yield,
Finance, Sustainability), seeded per tenant like the AI Model Registry.
Same tenant-scoped + RLS pattern as every migration since Phase 3.

Revision ID: 0022
Revises: 0021
Create Date: 2027-01-25 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("agent_code", sa.String(length=100), nullable=False, index=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("allowed_action_types", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.UniqueConstraint("tenant_id", "agent_code", name="uq_agent_definitions_tenant_code"),
    )

    op.execute("ALTER TABLE agent_definitions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agent_definitions FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON agent_definitions
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON agent_definitions")
    op.drop_table("agent_definitions")
