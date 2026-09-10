"""AI/ML Platform (Phase 15, FR-AIML / FR-COPILOT / FR-AGENT) - see
docs/03-BRD.md §17, docs/04-SRS.md §4, ADR-008/ADR-011 (11-ADR.md).

`AIModel`/`ModelVersion` are the shared registry ADR-008 calls for - one
place a new model type (disease detection, yield forecast, irrigation
demand, machine anomaly...) registers against, instead of each producing
context reinventing its own versioning/tracking. `Prediction` is the
AI-001 envelope: every rule-engine output that matters downstream (health
score, disease risk, yield range) is recorded here with its model
version/input reference/confidence, satisfying "every prediction carries
model name/version/confidence" even though the model implementations
themselves are still the rule-based placeholders built in Phases 10-12 -
this phase formalizes the contract those engines already conform to
in spirit, it does not replace their internals (that's real ML/ops work,
explicitly out of scope here - see docs/05-RTM.md Phase 15 checklist).

`AgentAction` implements the Observe -> Analyze -> Recommend -> Request
Approval -> Execute -> Verify -> Record Audit Trail lifecycle (FR-AGENT-001)
and the L0-L4 action-level classification (FR-AGENT-002/AI-004). L3+
actions route through the same `foundation.workflow_engine` every other
approval-gated Plan entity uses (see `foundation/seed.py`'s
`_seed_mandatory_approval_workflows`, extended here with an
`agent_action` entry) rather than a parallel approval mechanism.
`AgentPolicyGrant` is the only path to L4 (unattended execution within an
approved policy) - absent an active grant, the gateway conservatively
falls back to L3's human-approval requirement (see `agent_gateway.py`).

`CopilotConversation`/`CopilotMessage` back FR-COPILOT-001: `citations` on
each assistant message is what makes "answers only from real platform
data, cites source/timestamp/confidence" checkable rather than just
promised.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..foundation.models import TenantScopedMixin, gen_uuid

MODEL_VERSION_STATUSES = ("shadow", "canary", "active", "retired")
FEEDBACK_STATUSES = ("accepted", "rejected", "corrected")

# FR-AGENT-002: L0 (read-only) .. L4 (automatic within an approved policy).
ACTION_LEVELS = ("L0", "L1", "L2", "L3", "L4")

# Explicit floor per FR-AGENT-002 - "pesticide application, pump activation
# beyond safe threshold, procurement, financial posting, deletion, device
# configuration must never execute above L2 without an explicit auditable
# policy grant". Encoded as data (not scattered `if` checks) so the floor
# is one place to audit, per ADR-008's "one place to look" rationale for
# the model registry - the same shape applied to the action gateway.
ACTION_LEVEL_FLOORS: dict[str, str] = {
    "pesticide_application": "L3",
    "pump_activation": "L3",
    "irrigation_valve_activation": "L3",
    "procurement_request": "L3",
    "purchase_order_issue": "L3",
    "financial_posting": "L3",
    "record_deletion": "L3",
    "device_configuration_change": "L3",
}
AGENT_ACTION_STATUSES = ("proposed", "pending_approval", "approved", "rejected", "executed", "failed", "cancelled")


def _uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)


class AIModel(TenantScopedMixin, Base):
    """A registered model *type* (e.g. "disease_risk_rule_engine") -
    ADR-008's shared registry entry point. `task_type` groups models the
    way FR-AIML-001 lists them (disease/yield/harvest-date/irrigation/
    fertilizer/anomaly/failure/forecast)."""

    __tablename__ = "ai_models"

    id: Mapped[str] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(255))
    task_type: Mapped[str] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ModelVersion(TenantScopedMixin, Base):
    """One deployable version of an `AIModel`. `implementation_ref` documents
    which placeholder function currently backs it (e.g.
    "app.health.compute_health_score") - the seam ADR-008/AI-002 expect a
    real trained-model artifact to plug into later without changing the
    contract callers already use."""

    __tablename__ = "ai_model_versions"

    id: Mapped[str] = _uuid_pk()
    model_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("ai_models.id"), index=True)
    version: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="active")
    implementation_ref: Mapped[str] = mapped_column(String(255))
    training_dataset_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Prediction(TenantScopedMixin, Base):
    """AI-001's envelope: `entity_type`/`entity_id` is the generic
    reference-pair pattern already used platform-wide (harvest lot
    reference, accounting dimensions...) rather than a nullable FK column
    per possible subject type."""

    __tablename__ = "ai_predictions"

    id: Mapped[str] = _uuid_pk()
    model_version_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("ai_model_versions.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[str] = mapped_column(String(100), index=True)
    input_ref: Mapped[dict] = mapped_column(JSONB, default=dict)
    output: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PredictionFeedback(TenantScopedMixin, Base):
    """AI-005: user feedback on a prediction, linked to the model version it
    judged (via `Prediction.model_version_id`) so accuracy can be tracked
    per version once real ML models replace the rule engines."""

    __tablename__ = "ai_prediction_feedback"

    id: Mapped[str] = _uuid_pk()
    prediction_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("ai_predictions.id"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    corrected_value: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AgentPolicyGrant(TenantScopedMixin, Base):
    """The only path to L4 (FR-AGENT-002's "automatic within approved
    policy"). Absent an active grant for a given `action_type`,
    `agent_gateway.py` conservatively requires L3 human approval - there is
    no code path that executes an L4-classified action without one of
    these existing and `is_active`."""

    __tablename__ = "agent_policy_grants"

    id: Mapped[str] = _uuid_pk()
    action_type: Mapped[str] = mapped_column(String(100), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    granted_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AgentAction(TenantScopedMixin, Base):
    """One iteration of the FR-AGENT-001 lifecycle. `rationale` is the
    Recommend step's explanation; `input_context` is what Observe/Analyze
    gathered; `result` is what Verify recorded after Execute. A row's
    presence at all *is* the audit trail (FR-AGENT-001's last step) -
    combined with `foundation.audit.record_audit` calls at each transition
    for the platform-wide audit log."""

    __tablename__ = "agent_actions"

    id: Mapped[str] = _uuid_pk()
    agent_code: Mapped[str] = mapped_column(String(100), index=True)
    action_type: Mapped[str] = mapped_column(String(100), index=True)
    level: Mapped[str] = mapped_column(String(2))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(100))
    farm_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), nullable=True, index=True)
    rationale: Mapped[str] = mapped_column(Text)
    input_context: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    workflow_instance_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("workflow_instances.id"), nullable=True)
    policy_grant_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("agent_policy_grants.id"), nullable=True)
    result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class CopilotConversation(TenantScopedMixin, Base):
    __tablename__ = "copilot_conversations"

    id: Mapped[str] = _uuid_pk()
    farm_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), nullable=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class CopilotMessage(TenantScopedMixin, Base):
    """`citations` is a list of `{source_type, source_id, timestamp,
    confidence}` objects - FR-COPILOT-001's citation requirement made
    checkable rather than merely promised in a system prompt."""

    __tablename__ = "copilot_messages"

    id: Mapped[str] = _uuid_pk()
    conversation_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("copilot_conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSONB, default=list)
