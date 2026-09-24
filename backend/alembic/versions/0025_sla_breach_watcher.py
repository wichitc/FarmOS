"""SLA breach watcher (master-prompt integration, Phase 33): adds
`sla_breached_at` to `crm_support_tickets` - the idempotency marker
`crm.service.check_sla_breaches` uses so a ticket already flagged past
its SLA isn't re-processed on every sweep. Resolves the deferral
`iot_models.Alert`'s own docstring names explicitly ("Escalation/SLA
timing is not modeled yet - it needs a scheduler this repo doesn't
have") by adding the simplest real scheduler this platform needs: a
polling loop, not a cron dependency (see `app/scripts/sla_watcher.py`).

Revision ID: 0025
Revises: 0024
Create Date: 2027-02-15 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("crm_support_tickets", sa.Column("sla_breached_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("crm_support_tickets", "sla_breached_at")
