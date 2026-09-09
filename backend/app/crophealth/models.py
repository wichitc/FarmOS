"""Crop Health & Disease (Phase 10, FR-HEALTH) - see docs/03-BRD.md §9.

Named `crophealth`, not `health`, to avoid colliding with the legacy
`app.health` module (the pre-Phase-3 Equipment condition-scoring engine -
an unrelated domain that happens to share the English word).

`DiseaseIncident.source_detection_id` is where Phase 9's explicit deferral
closes: FR-CCTV-004 requires a human-confirmed Vision AI detection before it
can create a Disease Incident (enforced in the router, not here - a
detection's `validation_status` isn't visible to this module's models).

`TreatmentPlan` reuses the same approval-before-execution mechanism Phase 8
introduced for Irrigation/Fertigation: `provision_tenant()` also seeds a
`treatment_plan` `WorkflowDefinition` now (FR-HEALTH-003 requires human
approval before execution, and FR-CCTV-005 explicitly cross-references this
requirement - an AI diagnosis alone must never trigger treatment).

`TreatmentPlan.work_task_ref` is a free-text placeholder, not a real FK -
Farm Work Management (`FR-WORK`) doesn't exist as a queryable entity yet
(RTM: Phase 17), same treatment as `Fertilizer.stock_ref` for the
not-yet-built Inventory module.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..foundation.models import TenantScopedMixin, gen_uuid

DISEASE_PATHOGEN_TYPES = ("fungal", "bacterial", "viral", "pest", "nutrient_deficiency", "other")

INCIDENT_LIFECYCLE_STATES = (
    "detected",
    "suspected",
    "inspection_required",
    "confirmed",
    "treatment_planned",
    "treatment_applied",
    "monitoring",
    "resolved",
)
# Forward progression per FR-HEALTH-001, plus "resolved" reachable from any
# non-terminal state (false alarm / withdrawn at any stage) and "monitoring"
# able to loop back to "treatment_planned" on recurrence.
INCIDENT_ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "detected": ("suspected", "resolved"),
    "suspected": ("inspection_required", "resolved"),
    "inspection_required": ("confirmed", "resolved"),
    "confirmed": ("treatment_planned", "resolved"),
    "treatment_planned": ("treatment_applied", "resolved"),
    "treatment_applied": ("monitoring", "resolved"),
    "monitoring": ("treatment_planned", "resolved"),
    "resolved": (),
}

PLAN_STATUSES = ("draft", "pending_approval", "approved", "rejected", "completed", "cancelled")


def _uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)


class Disease(TenantScopedMixin, Base):
    """Disease/pest master data - the "Disease master" in
    docs/07-DOMAIN-MODEL.md's Crop Health & Disease bounded context."""

    __tablename__ = "diseases"

    id: Mapped[str] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(50))
    name_en: Mapped[str] = mapped_column(String(150))
    name_th: Mapped[str] = mapped_column(String(150))
    pathogen_type: Mapped[str] = mapped_column(String(30))
    symptoms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    susceptible_crop_codes: Mapped[list] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class DiseaseIncident(TenantScopedMixin, Base):
    __tablename__ = "disease_incidents"

    id: Mapped[str] = _uuid_pk()
    farm_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), index=True)
    plot_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("plots.id"), nullable=True)
    tree_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("trees.id"), nullable=True)
    disease_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("diseases.id"), index=True)
    source_detection_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("vision_detections.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="detected")
    risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reported_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)


class TreatmentPlan(TenantScopedMixin, Base):
    __tablename__ = "treatment_plans"

    id: Mapped[str] = _uuid_pk()
    incident_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("disease_incidents.id"), index=True)
    farm_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), index=True)
    method: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    chemical_or_treatment: Mapped[dict] = mapped_column(JSONB, default=dict)
    work_task_ref: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    workflow_instance_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("workflow_instances.id"), nullable=True)


class TreatmentEvent(TenantScopedMixin, Base):
    """Plan-vs-actual execution record, same shape as
    `IrrigationEvent`/`FertigationEvent` (Phase 8)."""

    __tablename__ = "treatment_events"

    id: Mapped[str] = _uuid_pk()
    plan_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("treatment_plans.id"), index=True)
    farm_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), index=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    executed_by: Mapped[str] = mapped_column(UUID(as_uuid=False))
    actual_method: Mapped[dict] = mapped_column(JSONB, default=dict)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
