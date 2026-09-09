"""CCTV & Vision AI (Phase 9, FR-CCTV / VIS): camera registry, vision model
catalog, detections with a human-review workflow - same tenant-scoped +
RLS pattern as prior migrations. Stub scaffold: no real inference engine,
see app/vision/inference.py.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

TENANT_SCOPED_TABLES = [
    "vision_cameras",
    "vision_models",
    "vision_detections",
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
        "vision_cameras",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("digital_twin_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("digital_twins.id"), nullable=False, index=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id"), nullable=False, index=True),
        sa.Column("protocol", sa.String(length=20), nullable=False, server_default="rtsp"),
        sa.Column("stream_url", sa.String(length=500), nullable=True),
        sa.Column("fov_metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *_standard_columns(),
    )

    op.create_table(
        "vision_models",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("use_case", sa.String(length=30), nullable=False),
        sa.Column("version", sa.String(length=30), nullable=False, server_default="stub"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *_standard_columns(),
        sa.UniqueConstraint("tenant_id", "code", name="uq_vision_models_tenant_code"),
    )

    op.create_table(
        "vision_detections",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("camera_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("vision_cameras.id"), nullable=False, index=True),
        sa.Column("model_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("vision_models.id"), nullable=False, index=True),
        sa.Column("tree_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("trees.id"), nullable=True),
        sa.Column("plot_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("plots.id"), nullable=True),
        sa.Column("detected_class", sa.String(length=100), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("bounding_box", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("frame_ref", sa.String(length=500), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("validation_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text, nullable=True),
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
    op.drop_table("vision_detections")
    op.drop_table("vision_models")
    op.drop_table("vision_cameras")
