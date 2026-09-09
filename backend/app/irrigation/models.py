"""Irrigation & Fertigation (Phase 8, FR-IRR / FR-FERT) - see
docs/03-BRD.md §6.

Approval-before-execution (FR-IRR-003/004) is enforced structurally: a plan
can only reach `status="approved"` by going through
`app.foundation.workflow_engine` against the `irrigation_plan`/
`fertigation_plan` `WorkflowDefinition` every tenant is auto-seeded with
(`app.foundation.seed.provision_tenant`) - per docs/09-SECURITY-ARCHITECTURE.md
§6, pump/valve activation is hardcoded at approval-level L3 minimum and no
tenant policy can downgrade that floor.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..foundation.models import TenantScopedMixin, gen_uuid

PLAN_SOURCES = ("manual", "scheduled", "rule_based", "ai_recommended")
PLAN_STATUSES = ("draft", "pending_approval", "approved", "rejected", "completed", "cancelled")


def _uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)


class IrrigationPlan(TenantScopedMixin, Base):
    __tablename__ = "irrigation_plans"

    id: Mapped[str] = _uuid_pk()
    farm_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), index=True)
    plot_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("plots.id"), nullable=True)
    source_twin_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("digital_twins.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    recommended_volume_liters: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recommended_duration_minutes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    workflow_instance_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("workflow_instances.id"), nullable=True)


class IrrigationEvent(TenantScopedMixin, Base):
    """Plan-vs-actual execution record. `plan_id` is nullable so an
    off-plan/emergency event can still be recorded (still requires an
    `executed_by` actor, per FR-IRR-004's traceability requirement)."""

    __tablename__ = "irrigation_events"

    id: Mapped[str] = _uuid_pk()
    plan_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("irrigation_plans.id"), nullable=True)
    farm_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), index=True)
    plot_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("plots.id"), nullable=True)
    actual_volume_liters: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    actual_duration_minutes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_by: Mapped[str] = mapped_column(UUID(as_uuid=False))
    safety_checks: Mapped[dict] = mapped_column(JSONB, default=dict)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Fertilizer(TenantScopedMixin, Base):
    """Fertilizer master data (FR-FERT-001). `stock_ref` is a free-text
    placeholder, not a real FK - Inventory doesn't exist until Phase 13."""

    __tablename__ = "fertilizers"

    id: Mapped[str] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(255))
    composition: Mapped[dict] = mapped_column(JSONB, default=dict)
    stock_ref: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)


class FertigationPlan(TenantScopedMixin, Base):
    __tablename__ = "fertigation_plans"

    id: Mapped[str] = _uuid_pk()
    farm_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), index=True)
    plot_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("plots.id"), nullable=True)
    fertilizer_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("fertilizers.id"), index=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    target_n_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_p_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_k_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recommended_quantity_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    workflow_instance_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("workflow_instances.id"), nullable=True)


class FertigationEvent(TenantScopedMixin, Base):
    """Plan-vs-actual, down to tree granularity (FR-FERT-002) via nullable
    `tree_id` - defaults to plot-level when not given."""

    __tablename__ = "fertigation_events"

    id: Mapped[str] = _uuid_pk()
    plan_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("fertigation_plans.id"), nullable=True)
    farm_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), index=True)
    plot_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("plots.id"), nullable=True)
    tree_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("trees.id"), nullable=True)
    actual_quantity_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    actual_breakdown: Mapped[dict] = mapped_column(JSONB, default=dict)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    executed_by: Mapped[str] = mapped_column(UUID(as_uuid=False))
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
