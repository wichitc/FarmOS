"""Yield & Harvest (Phase 11, FR-YIELD / FR-HARV): fruit lifecycle
observations, yield forecasts (always a range per FR-YIELD-002), harvest
lots / packing lots for QR traceability (FR-HARV-002) - same tenant-scoped
+ RLS pattern as prior migrations.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

TENANT_SCOPED_TABLES = [
    "fruit_observations",
    "yield_forecasts",
    "harvest_lots",
    "packing_lots",
    "packing_lot_items",
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
        "fruit_observations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("tree_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("trees.id"), nullable=False, index=True),
        sa.Column("stage", sa.String(length=20), nullable=False),
        sa.Column("estimated_count", sa.Integer, nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("recorded_by", postgresql.UUID(as_uuid=False), nullable=True),
        *_standard_columns(),
    )

    op.create_table(
        "yield_forecasts",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id"), nullable=False, index=True),
        sa.Column("plot_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("plots.id"), nullable=True),
        sa.Column("tree_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("trees.id"), nullable=True),
        sa.Column("season_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("seasons.id"), nullable=True),
        sa.Column("estimated_yield_kg_low", sa.Float, nullable=False),
        sa.Column("estimated_yield_kg_high", sa.Float, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("basis", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("forecast_date", sa.DateTime(timezone=True), nullable=False),
        *_standard_columns(),
    )

    op.create_table(
        "harvest_lots",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id"), nullable=False, index=True),
        sa.Column("plot_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("plots.id"), nullable=True),
        sa.Column("tree_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("trees.id"), nullable=True),
        sa.Column("season_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("seasons.id"), nullable=True),
        sa.Column("qr_code", sa.String(length=64), nullable=False),
        sa.Column("harvested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quantity_kg", sa.Float, nullable=False),
        sa.Column("grade", sa.String(length=50), nullable=True),
        sa.Column("harvested_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        *_standard_columns(),
        sa.UniqueConstraint("tenant_id", "qr_code", name="uq_harvest_lots_tenant_qr"),
    )

    op.create_table(
        "packing_lots",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id"), nullable=False, index=True),
        sa.Column("qr_code", sa.String(length=64), nullable=False),
        sa.Column("packed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("packed_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        *_standard_columns(),
        sa.UniqueConstraint("tenant_id", "qr_code", name="uq_packing_lots_tenant_qr"),
    )

    op.create_table(
        "packing_lot_items",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("packing_lot_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("packing_lots.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("harvest_lot_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("harvest_lots.id"), nullable=False, index=True),
        sa.Column("quantity_kg", sa.Float, nullable=True),
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
    op.drop_table("packing_lot_items")
    op.drop_table("packing_lots")
    op.drop_table("harvest_lots")
    op.drop_table("yield_forecasts")
    op.drop_table("fruit_observations")
