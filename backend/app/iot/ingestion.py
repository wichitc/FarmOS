"""Ingestion pipeline core (SRS IOT-001): validate -> store (with duplicate
tolerance, IOT-003) -> update twin state -> evaluate rules -> raise alerts.

Deliberately a plain, DB-session-taking function rather than something that
only makes sense inside an MQTT callback - `mqtt_ingestion_worker.py` calls
it per message, and the test suite calls it directly, exercising the same
validate/store/evaluate/alert logic without needing a real broker in CI.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..core.security import verify_password
from ..foundation.models import gen_uuid
from ..twins import models as twin_models
from . import models as iot_models

_OPERATORS = {
    "gt": lambda value, threshold: value > threshold,
    "gte": lambda value, threshold: value >= threshold,
    "lt": lambda value, threshold: value < threshold,
    "lte": lambda value, threshold: value <= threshold,
    "eq": lambda value, threshold: value == threshold,
}


@dataclass
class ProcessResult:
    accepted: bool
    reason: Optional[str] = None
    alerts: list[iot_models.Alert] = field(default_factory=list)


def process_reading(
    db: Session,
    *,
    device: iot_models.IotDevice,
    metric: str,
    value: float,
    secret: str,
    recorded_at: Optional[datetime] = None,
) -> ProcessResult:
    """FR-IOT-003 validation stage (secret check) then storage/rules. A
    wrong secret is rejected with no side effects at all - it never touches
    `last_seen_at` or telemetry, so a device with a stale/rotated secret
    doesn't get to look "online" by failing loudly in the right place."""
    if not verify_password(secret, device.hashed_secret):
        return ProcessResult(accepted=False, reason="invalid_secret")

    recorded_at = recorded_at or datetime.now(timezone.utc)

    telemetry_table = twin_models.TwinTelemetry.__table__
    insert_stmt = (
        pg_insert(telemetry_table)
        .values(
            id=gen_uuid(),
            tenant_id=device.tenant_id,
            twin_id=device.digital_twin_id,
            metric=metric,
            value_numeric=value,
            recorded_at=recorded_at,
        )
        .on_conflict_do_nothing(index_elements=["twin_id", "metric", "recorded_at"])
        .returning(telemetry_table.c.id)
    )
    # `.returning(...)` rather than `result.rowcount`: rowcount is not a
    # reliable signal for INSERT ... ON CONFLICT DO NOTHING over this
    # psycopg3/SQLAlchemy Core path - it reported 0 even for rows that were
    # genuinely inserted. A returned row means the insert actually happened;
    # no row means the conflict target skipped it.
    is_new_reading = db.execute(insert_stmt).first() is not None

    device.last_seen_at = recorded_at
    device.is_online = True

    twin = db.get(twin_models.DigitalTwin, device.digital_twin_id)
    if twin is not None:
        twin.current_state = {**twin.current_state, metric: value}

    alerts_raised: list[iot_models.Alert] = []
    if is_new_reading and twin is not None:
        alerts_raised = _evaluate_rules(db, device=device, twin=twin, metric=metric, value=value, recorded_at=recorded_at)

    db.commit()
    return ProcessResult(accepted=True, reason=None if is_new_reading else "duplicate", alerts=alerts_raised)


def _evaluate_rules(
    db: Session,
    *,
    device: iot_models.IotDevice,
    twin: twin_models.DigitalTwin,
    metric: str,
    value: float,
    recorded_at: datetime,
) -> list[iot_models.Alert]:
    rules = (
        db.query(iot_models.Rule)
        .filter(
            iot_models.Rule.tenant_id == device.tenant_id,
            iot_models.Rule.twin_type_id == twin.twin_type_id,
            iot_models.Rule.metric == metric,
            iot_models.Rule.is_active.is_(True),
        )
        .all()
    )

    raised = []
    for rule in rules:
        if not _OPERATORS[rule.operator](value, rule.threshold_value):
            continue

        # One open alert per (twin, rule) at a time - a sustained breach
        # shouldn't spam a fresh alert on every single reading.
        already_open = (
            db.query(iot_models.Alert)
            .filter(
                iot_models.Alert.tenant_id == device.tenant_id,
                iot_models.Alert.entity_type == "digital_twin",
                iot_models.Alert.entity_id == twin.id,
                iot_models.Alert.source_rule_id == rule.id,
                iot_models.Alert.status == "open",
            )
            .first()
        )
        if already_open:
            continue

        alert = iot_models.Alert(
            tenant_id=device.tenant_id,
            entity_type="digital_twin",
            entity_id=twin.id,
            severity=rule.severity,
            status="open",
            source_rule_id=rule.id,
            message=rule.message_template.format(metric=metric, value=value, threshold=rule.threshold_value),
            raised_at=recorded_at,
        )
        db.add(alert)
        db.flush()

        db.add(
            twin_models.TwinEvent(
                tenant_id=device.tenant_id,
                twin_id=twin.id,
                event_type="alert_raised",
                payload={"alert_id": alert.id, "metric": metric, "value": value, "rule_id": rule.id},
                occurred_at=recorded_at,
            )
        )
        raised.append(alert)

    return raised


def check_offline_devices(db: Session, tenant_id: str, timeout_seconds: int = 300) -> list[iot_models.Alert]:
    """FR-IOT-004: sensor-offline is a first-class alert condition, not a
    silent gap. Idempotent - a device already flagged offline with an open
    alert doesn't get a second one."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
    stale_devices = (
        db.query(iot_models.IotDevice)
        .filter(
            iot_models.IotDevice.tenant_id == tenant_id,
            iot_models.IotDevice.is_online.is_(True),
            or_(iot_models.IotDevice.last_seen_at.is_(None), iot_models.IotDevice.last_seen_at < cutoff),
        )
        .all()
    )

    raised = []
    for device in stale_devices:
        device.is_online = False

        already_open = (
            db.query(iot_models.Alert)
            .filter(
                iot_models.Alert.tenant_id == tenant_id,
                iot_models.Alert.entity_type == "iot_device",
                iot_models.Alert.entity_id == device.id,
                iot_models.Alert.status == "open",
            )
            .first()
        )
        if already_open:
            continue

        alert = iot_models.Alert(
            tenant_id=tenant_id,
            entity_type="iot_device",
            entity_id=device.id,
            severity="high",
            status="open",
            message=f"Device '{device.device_key}' has gone offline (no reading in {timeout_seconds}s)",
            raised_at=datetime.now(timezone.utc),
        )
        db.add(alert)
        raised.append(alert)

    db.commit()
    return raised
