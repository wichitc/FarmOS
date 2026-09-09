"""GIS & Spatial (Phase 5, FR-GIS): PostGIS geometry columns on the Phase-4
Farm/Zone/Plot/Block/Row/Tree hierarchy, plus the `map_features` table for
infrastructure layers (roads, drains, ponds, pipes, pumps, valves, CCTV,
sensors, buildings) - same tenant-scoped + RLS pattern as 0002/0004.

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TENANT_SCOPED_TABLES = ["map_features"]

# (table, column, geometry type) - spatial_index=False here because the
# GIST indexes below are created explicitly rather than relying on
# GeoAlchemy2's DDL-event index management, which is not guaranteed to fire
# for a bare `op.add_column` the way it does for `Table`+`create_all`.
BOUNDARY_COLUMNS = [
    ("farms", "boundary", "POLYGON"),
    ("zones", "boundary", "POLYGON"),
    ("plots", "boundary", "POLYGON"),
    ("blocks", "boundary", "POLYGON"),
    ("rows", "centerline", "LINESTRING"),
    ("trees", "location", "POINT"),
]


def _standard_columns():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_by", postgresql.UUID(as_uuid=False), nullable=True),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    for table, column, geom_type in BOUNDARY_COLUMNS:
        op.add_column(
            table,
            sa.Column(column, Geometry(geometry_type=geom_type, srid=4326, spatial_index=False), nullable=True),
        )
        op.execute(f"CREATE INDEX ix_{table}_{column}_gist ON {table} USING GIST ({column})")

    op.create_table(
        "map_features",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("feature_type", sa.String(length=30), nullable=False, index=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("geom", Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False), nullable=False),
        sa.Column("properties", postgresql.JSONB, nullable=False, server_default="{}"),
        *_standard_columns(),
    )
    op.execute("CREATE INDEX ix_map_features_geom_gist ON map_features USING GIST (geom)")

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
    op.drop_table("map_features")

    for table, column, _geom_type in BOUNDARY_COLUMNS:
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_{column}_gist")
        op.drop_column(table, column)
