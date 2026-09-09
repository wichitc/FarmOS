"""Crop Health & Disease (Phase 10, FR-HEALTH): disease master data,
disease incidents (lifecycle per FR-HEALTH-001), treatment plans/events -
same tenant-scoped + RLS pattern as prior migrations.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

TENANT_SCOPED_TABLES = [
    "diseases",
    "disease_incidents",
    "treatment_plans",
    "treatment_events",
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
        "diseases",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name_en", sa.String(length=150), nullable=False),
        sa.Column("name_th", sa.String(length=150), nullable=False),
        sa.Column("pathogen_type", sa.String(length=30), nullable=False),
        sa.Column("symptoms", sa.Text, nullable=True),
        sa.Column("susceptible_crop_codes", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *_standard_columns(),
        sa.UniqueConstraint("tenant_id", "code", name="uq_diseases_tenant_code"),
    )

    op.create_table(
        "disease_incidents",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id"), nullable=False, index=True),
        sa.Column("plot_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("plots.id"), nullable=True),
        sa.Column("tree_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("trees.id"), nullable=True),
        sa.Column("disease_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("diseases.id"), nullable=False, index=True),
        sa.Column("source_detection_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("vision_detections.id"), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="detected"),
        sa.Column("risk_score", sa.Float, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("evidence", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("reported_by", postgresql.UUID(as_uuid=False), nullable=True),
        *_standard_columns(),
    )

    op.create_table(
        "treatment_plans",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("incident_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("disease_incidents.id"), nullable=False, index=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id"), nullable=False, index=True),
        sa.Column("method", sa.String(length=255), nullable=True),
        sa.Column("chemical_or_treatment", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("work_task_ref", sa.String(length=150), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("workflow_instance_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("workflow_instances.id"), nullable=True),
        *_standard_columns(),
    )

    op.create_table(
        "treatment_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("treatment_plans.id"), nullable=False, index=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id"), nullable=False, index=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_by", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("actual_method", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("notes", sa.Text, nullable=True),
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
    op.drop_table("treatment_events")
    op.drop_table("treatment_plans")
    op.drop_table("disease_incidents")
    op.drop_table("diseases")
