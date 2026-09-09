"""Asset & Machinery (Phase 12, FR-ASSET) + Maintenance / Predictive
Maintenance (FR-MNT / FR-PDM) - see docs/03-BRD.md §12/§13.

Per ADR-004 and docs/07-DOMAIN-MODEL.md §3.2 ("Asset... adds manufacturer/
serial/warranty/meter-runtime/condition fields as TwinProperty extensions
rather than a parallel table - this replaces today's flat Equipment
table"), there is deliberately no `Asset` model here: an asset is just a
`DigitalTwin` (category `"asset"`), its manufacturer/model/serial/warranty
live in `TwinProperty`, its condition snapshot lives in `current_state`,
and its meter/runtime history (FR-ASSET-002) is `TwinTelemetry` - all
Phase 6/7 infrastructure, reused rather than duplicated.

`HealthAssessment` is the versioned, audited output of `health.py`'s rule
engine (FR-PDM-001's "interim implementation contract") - a value object
produced on demand, not a mutable field, so score history is never lost
the way it would be if this were just a column on the twin.

FR-PDM-002 requires Prediction / Recommendation / Approved Action as
separate, separately-audited states - that maps directly to
`HealthAssessment` (Prediction + Recommendation) -> `MaintenanceRequest`
(proposed action) -> `WorkOrder` (Approved Action, only reachable through
`workflow_engine`, same approval-gated pattern as every Phase 8/10 plan).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..foundation.models import TenantScopedMixin, gen_uuid

MAINTENANCE_STRATEGIES = ("corrective", "preventive", "predictive", "condition_based")
REQUEST_STATUSES = ("draft", "pending_approval", "approved", "rejected", "converted", "cancelled")
WORK_ORDER_STATUSES = ("open", "in_progress", "completed", "cancelled")


def _uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)


class HealthAssessment(TenantScopedMixin, Base):
    __tablename__ = "asset_health_assessments"

    id: Mapped[str] = _uuid_pk()
    twin_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("digital_twins.id"), index=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    score: Mapped[int] = mapped_column(Integer)
    band: Mapped[str] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(String(500))
    metrics: Mapped[list] = mapped_column(JSONB, default=list)
    recommendations: Mapped[list] = mapped_column(JSONB, default=list)
    method_id: Mapped[str] = mapped_column(String(50), default="rule_engine")
    method_version: Mapped[str] = mapped_column(String(20), default="v1")


class MaintenanceRequest(TenantScopedMixin, Base):
    __tablename__ = "maintenance_requests"

    id: Mapped[str] = _uuid_pk()
    twin_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("digital_twins.id"), index=True)
    farm_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), nullable=True, index=True)
    strategy: Mapped[str] = mapped_column(String(20), default="corrective")
    description: Mapped[str] = mapped_column(Text)
    source_assessment_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("asset_health_assessments.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    workflow_instance_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("workflow_instances.id"), nullable=True)
    requested_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)


class WorkOrder(TenantScopedMixin, Base):
    """The "Approved Action" (FR-PDM-002) - only ever created from an
    approved `MaintenanceRequest` (see `execute_maintenance_request` in the
    router), never directly."""

    __tablename__ = "work_orders"

    id: Mapped[str] = _uuid_pk()
    twin_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("digital_twins.id"), index=True)
    farm_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), nullable=True, index=True)
    request_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("maintenance_requests.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_to: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    parts_used: Mapped[list] = mapped_column(JSONB, default=list)
    labor_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    inspection_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
