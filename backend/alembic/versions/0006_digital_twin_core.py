"""Digital Twin Core (Phase 6, FR-TWIN / TWIN): generic TwinType/DigitalTwin/
TwinRelationship/TwinProperty/TwinEvent/TwinTelemetry model (ADR-004), plus
the `trees.digital_twin_id` FK Phase 4 deferred to this phase - same
tenant-scoped + RLS pattern as 0002/0004/0005.

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

TENANT_SCOPED_TABLES = [
    "twin_types",
    "digital_twins",
    "twin_relationships",
    "twin_properties",
    "twin_events",
    "twin_telemetry",
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
        "twin_types",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("is_ifc_sourced", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("property_schema", postgresql.JSONB, nullable=False, server_default="{}"),
        *_standard_columns(),
        sa.UniqueConstraint("tenant_id", "code", name="uq_twin_types_tenant_code"),
    )

    op.create_table(
        "digital_twins",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("twin_type_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("twin_types.id"), nullable=False, index=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id"), nullable=True, index=True),
        sa.Column("display_code", sa.String(length=150), nullable=False),
        sa.Column("current_state", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("location_ref", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("model_ref", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_standard_columns(),
        sa.UniqueConstraint("tenant_id", "display_code", name="uq_digital_twins_tenant_code"),
    )

    op.create_table(
        "twin_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("from_twin_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("digital_twins.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("to_twin_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("digital_twins.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("relation_type", sa.String(length=50), nullable=False, index=True),
        sa.Column("valid_from", sa.Date, nullable=False, server_default=sa.func.current_date()),
        sa.Column("valid_to", sa.Date, nullable=True),
        *_standard_columns(),
    )

    op.create_table(
        "twin_properties",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("twin_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("digital_twins.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", postgresql.JSONB, nullable=False),
        *_standard_columns(),
        sa.UniqueConstraint("twin_id", "key", name="uq_twin_properties_twin_key"),
    )

    op.create_table(
        "twin_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("twin_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("digital_twins.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("event_type", sa.String(length=50), nullable=False, index=True),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "twin_telemetry",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("twin_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("digital_twins.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("metric", sa.String(length=100), nullable=False, index=True),
        sa.Column("value_numeric", sa.Float, nullable=True),
        sa.Column("value_text", sa.String(length=255), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )

    op.add_column(
        "trees",
        sa.Column("digital_twin_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("digital_twins.id"), nullable=True),
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
    op.drop_column("trees", "digital_twin_id")
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.drop_table("twin_telemetry")
    op.drop_table("twin_events")
    op.drop_table("twin_properties")
    op.drop_table("twin_relationships")
    op.drop_table("digital_twins")
    op.drop_table("twin_types")
