"""Farm & Crop Domain (Phase 4, FR-FARM): Farm -> Zone -> Plot -> Block ->
Row -> Tree hierarchy, Season, and the append-only TreeEvent history table -
same tenant-scoped + RLS pattern as 0002_platform_foundation.py.

Revision ID: 0004
Revises: 0003
Create Date: 2026-02-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TENANT_SCOPED_TABLES = [
    "farms",
    "zones",
    "plots",
    "blocks",
    "rows",
    "trees",
    "seasons",
    "tree_events",
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
        "farms",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("lat", sa.Float, nullable=True),
        sa.Column("lng", sa.Float, nullable=True),
        sa.Column("area_hectares", sa.Float, nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        *_standard_columns(),
        sa.UniqueConstraint("tenant_id", "code", name="uq_farms_tenant_code"),
    )

    op.create_table(
        "zones",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        *_standard_columns(),
        sa.UniqueConstraint("farm_id", "code", name="uq_zones_farm_code"),
    )

    op.create_table(
        "plots",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("zone_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("zones.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("area_hectares", sa.Float, nullable=True),
        *_standard_columns(),
        sa.UniqueConstraint("zone_id", "code", name="uq_plots_zone_code"),
    )

    op.create_table(
        "blocks",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("plot_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("plots.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("area_hectares", sa.Float, nullable=True),
        *_standard_columns(),
        sa.UniqueConstraint("plot_id", "code", name="uq_blocks_plot_code"),
    )

    op.create_table(
        "rows",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("block_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("blocks.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("spacing_m", sa.Float, nullable=True),
        *_standard_columns(),
        sa.UniqueConstraint("block_id", "code", name="uq_rows_block_code"),
    )

    op.create_table(
        "trees",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("row_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("rows.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("crop_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("crops.id"), nullable=False, index=True),
        sa.Column("variety_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("varieties.id"), nullable=True),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("planting_date", sa.Date, nullable=True),
        sa.Column("rootstock", sa.String(length=150), nullable=True),
        sa.Column("height_m", sa.Float, nullable=True),
        sa.Column("canopy_diameter_m", sa.Float, nullable=True),
        sa.Column("trunk_diameter_cm", sa.Float, nullable=True),
        sa.Column("growth_stage", sa.String(length=20), nullable=False, server_default="seedling"),
        sa.Column("lat", sa.Float, nullable=True),
        sa.Column("lng", sa.Float, nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_standard_columns(),
        sa.UniqueConstraint("tenant_id", "code", name="uq_trees_tenant_code"),
    )

    op.create_table(
        "seasons",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *_standard_columns(),
        sa.UniqueConstraint("farm_id", "name", name="uq_seasons_farm_name"),
    )

    op.create_table(
        "tree_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("tree_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("trees.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("event_type", sa.String(length=50), nullable=False, index=True),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Row-level security, same pattern as 0002_platform_foundation.py.
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
    op.drop_table("tree_events")
    op.drop_table("seasons")
    op.drop_table("trees")
    op.drop_table("rows")
    op.drop_table("blocks")
    op.drop_table("plots")
    op.drop_table("zones")
    op.drop_table("farms")
