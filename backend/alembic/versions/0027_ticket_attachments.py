"""Ticket message attachments (master-prompt integration, Phase 39,
SEC-005): adds nullable attachment columns to `crm_ticket_messages` -
the actual file bytes live in MinIO (already provisioned since Phase 3,
DEP-001), this table only stores the object key plus display metadata.
Closes the gap named explicitly in Phase 20's checklist: "No attachment
support... no file-upload endpoint exists anywhere in this platform yet."

Revision ID: 0027
Revises: 0026
Create Date: 2027-02-25 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("crm_ticket_messages", sa.Column("attachment_object_key", sa.String(length=500), nullable=True))
    op.add_column("crm_ticket_messages", sa.Column("attachment_filename", sa.String(length=255), nullable=True))
    op.add_column("crm_ticket_messages", sa.Column("attachment_content_type", sa.String(length=100), nullable=True))
    op.add_column("crm_ticket_messages", sa.Column("attachment_size_bytes", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("crm_ticket_messages", "attachment_size_bytes")
    op.drop_column("crm_ticket_messages", "attachment_content_type")
    op.drop_column("crm_ticket_messages", "attachment_filename")
    op.drop_column("crm_ticket_messages", "attachment_object_key")
