"""baseline: existing models/equipment tables (pre-Phase-3, unmanaged until now)

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "models",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "equipment",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("model_id", sa.String(length=36), sa.ForeignKey("models.id", ondelete="CASCADE"), nullable=True),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("pos_x", sa.Float, nullable=False, server_default="0"),
        sa.Column("pos_y", sa.Float, nullable=False, server_default="0"),
        sa.Column("pos_z", sa.Float, nullable=False, server_default="0"),
        sa.Column("rotation_y", sa.Float, nullable=False, server_default="0"),
        sa.Column("scale", sa.Float, nullable=False, server_default="1"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="running"),
        sa.Column("install_date", sa.Date, nullable=True),
        sa.Column("last_maintenance_date", sa.Date, nullable=True),
        sa.Column("operating_hours", sa.Float, nullable=False, server_default="0"),
        sa.Column("temperature_c", sa.Float, nullable=True),
        sa.Column("vibration_mm_s", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("equipment")
    op.drop_table("models")
