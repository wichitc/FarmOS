"""Farm Work Management (Phase 17, FR-WORK) - see docs/03-BRD.md §11.

FR-WORK-002's lifecycle (Request -> Plan -> Assign -> Accept -> Execute ->
Evidence -> Complete -> Supervisor Review -> Close) is not routed through
`foundation.workflow_engine` the way Irrigation/Fertigation/Treatment/
Maintenance/Purchase plans are: those route through it because a *risky
action* needs human approval *before* it executes (the hardcoded L3 floor
in docs/09-SECURITY-ARCHITECTURE.md §6). A work task's "Supervisor Review"
is a review *after* the work already happened - closer to
`crophealth.models.DiseaseIncident`'s own lifecycle dict than to an
approval gate, so `WORK_TASK_STATUSES` plus per-endpoint current-status
checks in the router (same inline-check style `irrigation.py`/`asset.py`
already use, not a generic PATCH-status validator) is the right shape
here, not the workflow engine.

"Evidence" (FR-WORK-003's photos/measurements/materials/labor) is folded
into the `complete` transition's payload as one `evidence` JSONB field
rather than a separate lifecycle state - the mobile capture UI that would
populate it in real time is deferred (FR-MOB, frontend/PWA work), but the
data shape it would write is real and stored now, same "shape now, real
capture later" treatment as every other placeholder in this platform.

`source_type`/`source_id` is the generic reference-pair pattern (nullable,
optional) other modules use - a caller MAY link a task back to whatever
prompted it (an approved IrrigationPlan, a MaintenanceRequest...), but
nothing auto-populates or auto-creates a WorkTask from those flows; wiring
that up would mean reaching back into every prior phase's router, the same
explicitly-deferred integration Phase 14 documented for ledger postings.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..foundation.models import TenantScopedMixin, gen_uuid

WORK_TYPES = (
    "irrigation", "fertilization", "pruning", "spraying", "mowing",
    "disease_inspection", "harvesting", "equipment_inspection", "maintenance", "cleaning",
)
WORK_TASK_STATUSES = ("requested", "planned", "assigned", "accepted", "rejected", "in_progress", "completed", "closed", "cancelled")


def _uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)


class WorkTask(TenantScopedMixin, Base):
    __tablename__ = "work_tasks"

    id: Mapped[str] = _uuid_pk()
    farm_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), index=True)
    plot_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("plots.id"), nullable=True)
    work_type: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="requested")
    source_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    requested_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_to: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)

    reviewed_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    cancel_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
