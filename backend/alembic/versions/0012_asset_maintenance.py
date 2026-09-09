"""Asset & Machinery (Phase 12, FR-ASSET) + Maintenance / Predictive
Maintenance (FR-MNT / FR-PDM): health assessments, maintenance requests,
work orders - same tenant-scoped + RLS pattern as prior migrations. No new
Asset table (assets are DigitalTwin + TwinProperty, per ADR-004).

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

TENANT_SCOPED_TABLES = [
    "asset_health_assessments",
    "maintenance_requests",
    "work_orders",
]


def _standard_columns():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_by", postgresql.UUID(as_uuid=False), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "asset_health_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("twin_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("digital_twins.id"), nullable=False, index=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("band", sa.String(length=20), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("metrics", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("recommendations", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("method_id", sa.String(length=50), nullable=False, server_default="rule_engine"),
        sa.Column("method_version", sa.String(length=20), nullable=False, server_default="v1"),
        *_standard_columns(),
    )

    op.create_table(
        "maintenance_requests",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("twin_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("digital_twins.id"), nullable=False, index=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id"), nullable=True, index=True),
        sa.Column("strategy", sa.String(length=20), nullable=False, server_default="corrective"),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("source_assessment_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("asset_health_assessments.id"), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("workflow_instance_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("workflow_instances.id"), nullable=True),
        sa.Column("requested_by", postgresql.UUID(as_uuid=False), nullable=True),
        *_standard_columns(),
    )

    op.create_table(
        "work_orders",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("twin_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("digital_twins.id"), nullable=False, index=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id"), nullable=True, index=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("maintenance_requests.id"), nullable=False, index=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("parts_used", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("labor_hours", sa.Float, nullable=True),
        sa.Column("inspection_notes", sa.Text, nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by", postgresql.UUID(as_uuid=False), nullable=True),
        *_standard_columns(),
    )

    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
            """
        )


def downgrade() -> None:
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.drop_table("work_orders")
    op.drop_table("maintenance_requests")
    op.drop_table("asset_health_assessments")
