"""Digital Twin Core (Phase 6, FR-TWIN / TWIN) - see docs/07-DOMAIN-MODEL.md
§3.1, ADR-004 (11-ADR.md).

Generic model: a new twin kind (a new equipment category, a new sensor
type) is a `TwinType` configuration row, never a new table - this is what
retires the legacy `app.models.Equipment` flat table's tree/asset
string-prefix conflation (Risk R-02 in 05-RTM.md) without inventing a
parallel `Asset` table with its own fixed columns. Kind-specific fields
(manufacturer, serial number, warranty...) live in `TwinProperty`.

Deliberately not built this pass (see the Phase 6 plan): `TwinCommand`
(Phase 7 IoT actuation), `TwinDocument` (no consumer yet), `TwinAlert`
(Phase 7 FR-ALERT). `TwinTelemetry` exists as a shape now; TimescaleDB
hypertable conversion happens when Phase 7 gives it real ingestion volume.
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ..foundation.models import TenantScopedMixin, gen_uuid


def _uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)


TWIN_TYPE_CATEGORIES = ("tree", "asset", "sensor", "camera", "building", "other")


class TwinType(TenantScopedMixin, Base):
    """Catalog entry (ADR-004) - the configuration point that lets a new
    asset/tree category be added without a schema change, mirroring the
    Crop Configuration Engine pattern (`foundation.models.Crop`)."""

    __tablename__ = "twin_types"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_twin_types_tenant_code"),)

    id: Mapped[str] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(20))
    is_ifc_sourced: Mapped[bool] = mapped_column(Boolean, default=False)
    property_schema: Mapped[dict] = mapped_column(JSONB, default=dict)


class DigitalTwin(TenantScopedMixin, Base):
    """Aggregate root (docs/07-DOMAIN-MODEL.md §3.1). `id` is the immutable
    Twin ID, assigned once and never reassigned (BR-006) - `display_code` is
    the mutable, user-facing label. `farm_id` is nullable purely for ABAC
    scoping (mirrors legacy `Equipment.model_id IS NULL` meaning "unscoped");
    it is not part of the twin graph itself, which is `TwinRelationship`'s
    job."""

    __tablename__ = "digital_twins"
    __table_args__ = (UniqueConstraint("tenant_id", "display_code", name="uq_digital_twins_tenant_code"),)

    id: Mapped[str] = _uuid_pk()
    twin_type_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("twin_types.id"), index=True)
    farm_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), nullable=True, index=True)
    display_code: Mapped[str] = mapped_column(String(150))
    current_state: Mapped[dict] = mapped_column(JSONB, default=dict)
    location_ref: Mapped[dict] = mapped_column(JSONB, default=dict)
    model_ref: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="active")
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    properties: Mapped[list["TwinProperty"]] = relationship(back_populates="twin", cascade="all, delete-orphan")


class TwinRelationship(TenantScopedMixin, Base):
    """Temporal, directed edge (TWIN-003) - relationship history is
    preserved via `valid_to`, not overwritten, so "this valve used to be
    supplied by Pump A, now by Pump B" stays queryable."""

    __tablename__ = "twin_relationships"

    id: Mapped[str] = _uuid_pk()
    from_twin_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("digital_twins.id", ondelete="CASCADE"), index=True)
    to_twin_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("digital_twins.id", ondelete="CASCADE"), index=True)
    relation_type: Mapped[str] = mapped_column(String(50), index=True)
    valid_from: Mapped[date] = mapped_column(server_default=func.current_date())
    valid_to: Mapped[Optional[date]] = mapped_column(nullable=True)


class TwinProperty(TenantScopedMixin, Base):
    """The `TwinProperty` extension mechanism ADR-004 relies on in place of
    a new base table per twin kind - e.g. an asset-category twin's
    manufacturer/serial/warranty live here, not as columns anywhere."""

    __tablename__ = "twin_properties"
    __table_args__ = (UniqueConstraint("twin_id", "key", name="uq_twin_properties_twin_key"),)

    id: Mapped[str] = _uuid_pk()
    twin_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("digital_twins.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(100))
    value: Mapped[dict] = mapped_column(JSONB)

    twin: Mapped["DigitalTwin"] = relationship(back_populates="properties")


class TwinEvent(Base):
    """Append-only event timeline (TWIN-002) - same shape as
    `farm.models.TreeEvent`: no `updated_at`, no update/delete route."""

    __tablename__ = "twin_events"

    id: Mapped[str] = _uuid_pk()
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    twin_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("digital_twins.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TwinTelemetry(Base):
    """Append-only time-series (TWIN-004), keyed by (twin_id, metric,
    recorded_at) - a real TimescaleDB hypertable as of Phase 7
    (`0007_iot_platform.py`), per docs/08-DATA-ARCHITECTURE.md §1.

    `recorded_at` is part of the primary key (composite with `id`) because
    TimescaleDB requires every unique/primary-key constraint on a hypertable
    to include its partitioning column - the same reason the dedup
    constraint below is `(twin_id, metric, recorded_at)` rather than just
    `(twin_id, metric)`."""

    __tablename__ = "twin_telemetry"
    __table_args__ = (UniqueConstraint("twin_id", "metric", "recorded_at", name="uq_twin_telemetry_twin_metric_time"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    twin_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("digital_twins.id", ondelete="CASCADE"), index=True)
    metric: Mapped[str] = mapped_column(String(100), index=True)
    value_numeric: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    value_text: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, server_default=func.now()
    )
