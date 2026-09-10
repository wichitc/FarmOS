"""AI/ML Platform (Phase 15, FR-AIML / FR-COPILOT / FR-AGENT): model
registry, predictions + feedback, agent action gateway + policy grants,
copilot conversations - same tenant-scoped + RLS pattern as prior
migrations.

Revision ID: 0015
Revises: 0014
Create Date: 2026-12-15 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

TENANT_SCOPED_TABLES = [
    "ai_models",
    "ai_model_versions",
    "ai_predictions",
    "ai_prediction_feedback",
    "agent_policy_grants",
    "agent_actions",
    "copilot_conversations",
    "copilot_messages",
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
        "ai_models",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("code", sa.String(length=100), nullable=False, index=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("task_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        *_standard_columns(),
    )

    op.create_table(
        "ai_model_versions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("model_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("ai_models.id"), nullable=False, index=True),
        sa.Column("version", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("implementation_ref", sa.String(length=255), nullable=False),
        sa.Column("training_dataset_ref", sa.String(length=255), nullable=True),
        sa.Column("metrics", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        *_standard_columns(),
    )

    op.create_table(
        "ai_predictions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("ai_model_versions.id"), nullable=False, index=True),
        sa.Column("entity_type", sa.String(length=50), nullable=False, index=True),
        sa.Column("entity_id", sa.String(length=100), nullable=False, index=True),
        sa.Column("input_ref", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("output", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("predicted_at", sa.DateTime(timezone=True), nullable=False),
        *_standard_columns(),
    )

    op.create_table(
        "ai_prediction_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("prediction_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("ai_predictions.id"), nullable=False, index=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("corrected_value", postgresql.JSONB, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        *_standard_columns(),
    )

    op.create_table(
        "agent_policy_grants",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("action_type", sa.String(length=100), nullable=False, index=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("granted_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        *_standard_columns(),
    )

    op.create_table(
        "agent_actions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("agent_code", sa.String(length=100), nullable=False, index=True),
        sa.Column("action_type", sa.String(length=100), nullable=False, index=True),
        sa.Column("level", sa.String(length=2), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id"), nullable=True, index=True),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("input_context", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="proposed"),
        sa.Column("workflow_instance_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("workflow_instances.id"), nullable=True),
        sa.Column("policy_grant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("agent_policy_grants.id"), nullable=True),
        sa.Column("result", postgresql.JSONB, nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        *_standard_columns(),
    )

    op.create_table(
        "copilot_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id"), nullable=True, index=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        *_standard_columns(),
    )

    op.create_table(
        "copilot_messages",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("copilot_conversations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("citations", postgresql.JSONB, nullable=False, server_default="[]"),
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
    op.drop_table("copilot_messages")
    op.drop_table("copilot_conversations")
    op.drop_table("agent_actions")
    op.drop_table("agent_policy_grants")
    op.drop_table("ai_prediction_feedback")
    op.drop_table("ai_predictions")
    op.drop_table("ai_model_versions")
    op.drop_table("ai_models")
