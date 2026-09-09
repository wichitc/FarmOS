"""Irrigation & Fertigation (Phase 8, FR-IRR / FR-FERT) + Weather (FR-WX):
plan/event tables, fertilizer master data, weather readings - same
tenant-scoped + RLS pattern as prior migrations.

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

TENANT_SCOPED_TABLES = [
    "irrigation_plans",
    "irrigation_events",
    "fertilizers",
    "fertigation_plans",
    "fertigation_events",
    "weather_readings",
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
        "irrigation_plans",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id"), nullable=False, index=True),
        sa.Column("plot_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("plots.id"), nullable=True),
        sa.Column("source_twin_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("digital_twins.id"), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("recommended_volume_liters", sa.Float, nullable=True),
        sa.Column("recommended_duration_minutes", sa.Float, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("workflow_instance_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("workflow_instances.id"), nullable=True),
        *_standard_columns(),
    )

    op.create_table(
        "irrigation_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("irrigation_plans.id"), nullable=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id"), nullable=False, index=True),
        sa.Column("plot_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("plots.id"), nullable=True),
        sa.Column("actual_volume_liters", sa.Float, nullable=True),
        sa.Column("actual_duration_minutes", sa.Float, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_by", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("safety_checks", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("notes", sa.Text, nullable=True),
        *_standard_columns(),
    )

    op.create_table(
        "fertilizers",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("composition", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("stock_ref", sa.String(length=150), nullable=True),
        *_standard_columns(),
        sa.UniqueConstraint("tenant_id", "code", name="uq_fertilizers_tenant_code"),
    )

    op.create_table(
        "fertigation_plans",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id"), nullable=False, index=True),
        sa.Column("plot_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("plots.id"), nullable=True),
        sa.Column("fertilizer_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("fertilizers.id"), nullable=False, index=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("target_n_kg", sa.Float, nullable=True),
        sa.Column("target_p_kg", sa.Float, nullable=True),
        sa.Column("target_k_kg", sa.Float, nullable=True),
        sa.Column("recommended_quantity_kg", sa.Float, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("workflow_instance_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("workflow_instances.id"), nullable=True),
        *_standard_columns(),
    )

    op.create_table(
        "fertigation_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("fertigation_plans.id"), nullable=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id"), nullable=False, index=True),
        sa.Column("plot_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("plots.id"), nullable=True),
        sa.Column("tree_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("trees.id"), nullable=True),
        sa.Column("actual_quantity_kg", sa.Float, nullable=True),
        sa.Column("actual_breakdown", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_by", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        *_standard_columns(),
    )

    op.create_table(
        "weather_readings",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id"), nullable=False, index=True),
        sa.Column("metric", sa.String(length=50), nullable=False, index=True),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False, index=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
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
    op.drop_table("weather_readings")
    op.drop_table("fertigation_events")
    op.drop_table("fertigation_plans")
    op.drop_table("fertilizers")
    op.drop_table("irrigation_events")
    op.drop_table("irrigation_plans")
