"""IoT / Sensor Platform (Phase 7, FR-IOT / IOT) - see docs/03-BRD.md §5,
docs/04-SRS.md §3.

Per ADR-004 ("no new table per type"), a `Device` (or `Gateway` - a Gateway
is just an `IotDevice` with `protocol='gateway'` that other devices point
`gateway_id` at) is a `DigitalTwin` underneath; `IotDevice` is the thin
extension row carrying IoT-specific fields, the same shared-kernel split
Phase 4/6 already established for `Tree`.

`Rule`/`Alert` implement FR-IOT-004's rules engine and FR-ALERT-001/002's
alerting, bundled into this phase per docs/05-RTM.md's phase mapping
("Phase 7, with IoT").
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..foundation.models import TenantScopedMixin, gen_uuid


def _uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)


DEVICE_PROTOCOLS = ("mqtt", "modbus", "lorawan", "http", "gateway")
RULE_OPERATORS = ("gt", "gte", "lt", "lte", "eq")
ALERT_SEVERITIES = ("info", "low", "medium", "high", "critical")
ALERT_STATUSES = ("open", "acknowledged", "resolved")


class IotDevice(TenantScopedMixin, Base):
    __tablename__ = "iot_devices"
    __table_args__ = (UniqueConstraint("tenant_id", "device_key", name="uq_iot_devices_tenant_key"),)

    id: Mapped[str] = _uuid_pk()
    digital_twin_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("digital_twins.id"), index=True)
    farm_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), index=True)
    device_key: Mapped[str] = mapped_column(String(100))
    hashed_secret: Mapped[str] = mapped_column(String(255))
    protocol: Mapped[str] = mapped_column(String(20))
    gateway_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("iot_devices.id"), nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)


class Rule(TenantScopedMixin, Base):
    """Tenant/farm-configurable threshold rule (FR-IOT-004) - a plain
    threshold table, not a condition DSL, since that's what's needed to
    prove the "reading -> breach -> alert" loop; more expressive rules
    extend this same shape later rather than requiring a rewrite."""

    __tablename__ = "iot_rules"

    id: Mapped[str] = _uuid_pk()
    twin_type_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("twin_types.id"), index=True)
    metric: Mapped[str] = mapped_column(String(100), index=True)
    operator: Mapped[str] = mapped_column(String(10))
    threshold_value: Mapped[float] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    message_template: Mapped[str] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Alert(TenantScopedMixin, Base):
    """FR-ALERT-001/002. `entity_type`/`entity_id` is generic (points at a
    twin today, any alertable entity later) rather than a twin-specific FK,
    matching the domain-event catalog's alert-producing events
    (`SensorOffline`, `PumpAnomalyDetected`, ...) coming from many contexts.
    Escalation/SLA timing (FR-ALERT-002) is not modeled yet - it needs a
    scheduler this repo doesn't have; ack/resolve covers the acceptance
    path."""

    __tablename__ = "iot_alerts"

    id: Mapped[str] = _uuid_pk()
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="open")
    source_rule_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("iot_rules.id"), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
