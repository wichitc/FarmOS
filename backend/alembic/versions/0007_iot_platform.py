"""IoT Platform (Phase 7, FR-IOT / IOT) + Alerts (FR-ALERT): device/gateway
registry, threshold rules engine, alerts - same tenant-scoped + RLS pattern
as 0002/0004/0005/0006 - plus converting `twin_telemetry` (Phase 6) into a
real TimescaleDB hypertable now that it has a real producer (ADR-002).

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

TENANT_SCOPED_TABLES = [
    "iot_devices",
    "iot_rules",
    "iot_alerts",
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
        "iot_devices",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("digital_twin_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("digital_twins.id"), nullable=False, index=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id"), nullable=False, index=True),
        sa.Column("device_key", sa.String(length=100), nullable=False),
        sa.Column("hashed_secret", sa.String(length=255), nullable=False),
        sa.Column("protocol", sa.String(length=20), nullable=False),
        sa.Column("gateway_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("iot_devices.id"), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_online", sa.Boolean, nullable=False, server_default=sa.false()),
        *_standard_columns(),
        sa.UniqueConstraint("tenant_id", "device_key", name="uq_iot_devices_tenant_key"),
    )

    op.create_table(
        "iot_rules",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("twin_type_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("twin_types.id"), nullable=False, index=True),
        sa.Column("metric", sa.String(length=100), nullable=False, index=True),
        sa.Column("operator", sa.String(length=10), nullable=False),
        sa.Column("threshold_value", sa.Float, nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("message_template", sa.String(length=500), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *_standard_columns(),
    )

    op.create_table(
        "iot_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("entity_type", sa.String(length=50), nullable=False, index=True),
        sa.Column("entity_id", sa.String(length=100), nullable=False, index=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("source_rule_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("iot_rules.id"), nullable=True),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=False), nullable=True),
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

    # --- twin_telemetry -> real TimescaleDB hypertable (ADR-002) ---
    # TimescaleDB requires every unique/primary-key constraint on a
    # hypertable to include the partitioning column (`recorded_at`), so the
    # single-column `id` primary key from 0006 has to become a composite
    # (id, recorded_at) key before `create_hypertable` will accept the table.
    op.execute("ALTER TABLE twin_telemetry DROP CONSTRAINT twin_telemetry_pkey")
    op.execute("ALTER TABLE twin_telemetry ADD PRIMARY KEY (id, recorded_at)")
    op.execute(
        "ALTER TABLE twin_telemetry ADD CONSTRAINT uq_twin_telemetry_twin_metric_time "
        "UNIQUE (twin_id, metric, recorded_at)"
    )
    op.execute("SELECT create_hypertable('twin_telemetry', 'recorded_at', migrate_data => true)")
    op.execute("SELECT add_retention_policy('twin_telemetry', INTERVAL '90 days')")


def downgrade() -> None:
    op.execute("SELECT remove_retention_policy('twin_telemetry')")
    # create_hypertable/composite PK are not reverted - downgrading a
    # populated hypertable back to a plain table is a destructive,
    # deployment-specific operation intentionally left to a human.

    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.drop_table("iot_alerts")
    op.drop_table("iot_rules")
    op.drop_table("iot_devices")
