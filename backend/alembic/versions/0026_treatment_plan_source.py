"""Treatment plan source (master-prompt integration, Phase 37): adds
`source` to `treatment_plans`, the same "was this AI-originated" signal
`irrigation_plans`/`fertigation_plans` have had since Phase 8 - closes
the gap Phase 30 explicitly declined to fabricate a trigger for when it
wired the Disease Agent's `disease_risk_assessment` action but not its
other cataloged action type, `treatment_recommendation`.

Revision ID: 0026
Revises: 0025
Create Date: 2027-02-20 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("treatment_plans", sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"))


def downgrade() -> None:
    op.drop_column("treatment_plans", "source")
