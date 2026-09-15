"""IoT device secret revocation (SEC-006 follow-on): adds `is_active` to
`iot_devices` so a device's auth can actually be revoked, not just have
its secret rotated - `ingestion.process_reading` will reject every
reading from an inactive device outright.

Revision ID: 0017
Revises: 0016
Create Date: 2026-12-22 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("iot_devices", sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("iot_devices", "is_active")
