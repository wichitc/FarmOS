"""IoT ingestion service (SRS IOT-001): MQTT -> validate -> store ->
transform -> rules engine -> alert/twin update.

Subscribes to `tenants/+/devices/+/telemetry`. Expected JSON payload:
    {"metric": "temp_c", "value": 25.5, "secret": "<device secret>", "recorded_at": "2026-01-01T00:00:00Z"}
`recorded_at` is optional (defaults to receipt time).

Runs as the `iot-ingestion` docker-compose service. Also periodically scans
every tenant for devices that have gone quiet (FR-IOT-004) - offline
detection isn't a separate service, just another thing this loop does.

Usage: python -m app.scripts.mqtt_ingestion_worker
"""
import json
import logging
import threading
import time
from datetime import datetime

import paho.mqtt.client as mqtt

from ..config import settings
from ..core.deps import set_tenant_context
from ..database import SessionLocal
from ..farm import models as farm_models  # noqa: F401 - registers FK targets (farms) in metadata
from ..foundation import models as fm
from ..iot import models as iot_models
from ..iot.ingestion import check_offline_devices, process_reading
from ..twins import models as twin_models  # noqa: F401 - registers FK targets (digital_twins) in metadata

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("iot-ingestion")

TOPIC_FILTER = "tenants/+/devices/+/telemetry"


def _parse_topic(topic: str) -> tuple[str, str] | None:
    parts = topic.split("/")
    if len(parts) != 5 or parts[0] != "tenants" or parts[2] != "devices" or parts[4] != "telemetry":
        return None
    return parts[1], parts[3]


def _handle_message(tenant_slug: str, device_key: str, raw_payload: bytes) -> None:
    db = SessionLocal()
    try:
        tenant = db.query(fm.Tenant).filter(fm.Tenant.slug == tenant_slug).one_or_none()
        if tenant is None:
            log.warning("unknown tenant slug '%s'", tenant_slug)
            return
        set_tenant_context(db, tenant.id)

        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            log.warning("malformed JSON payload on tenant '%s' device '%s'", tenant_slug, device_key)
            return

        metric = payload.get("metric")
        value = payload.get("value")
        secret = payload.get("secret")
        if not metric or value is None or not secret:
            log.warning("payload missing metric/value/secret: tenant '%s' device '%s'", tenant_slug, device_key)
            return

        device = (
            db.query(iot_models.IotDevice)
            .filter(iot_models.IotDevice.tenant_id == tenant.id, iot_models.IotDevice.device_key == device_key)
            .one_or_none()
        )
        if device is None:
            log.warning("unknown device '%s' for tenant '%s'", device_key, tenant_slug)
            return

        recorded_at_raw = payload.get("recorded_at")
        recorded_at = datetime.fromisoformat(recorded_at_raw) if recorded_at_raw else None
        result = process_reading(
            db,
            device=device,
            metric=metric,
            value=float(value),
            secret=secret,
            recorded_at=recorded_at,
        )
        if not result.accepted:
            log.warning("rejected reading from '%s/%s': %s", tenant_slug, device_key, result.reason)
        else:
            log.info(
                "%s/%s %s=%s%s%s",
                tenant_slug, device_key, metric, value,
                " (duplicate)" if result.reason == "duplicate" else "",
                f" - {len(result.alerts)} alert(s) raised" if result.alerts else "",
            )
    finally:
        db.close()


def _on_connect(client, userdata, flags, reason_code, properties=None):
    log.info("connected to MQTT broker (%s), subscribing to %s", reason_code, TOPIC_FILTER)
    client.subscribe(TOPIC_FILTER)


def _on_message(client, userdata, msg):
    parsed = _parse_topic(msg.topic)
    if parsed is None:
        log.warning("ignoring message on unexpected topic '%s'", msg.topic)
        return
    tenant_slug, device_key = parsed
    try:
        _handle_message(tenant_slug, device_key, msg.payload)
    except Exception:
        log.exception("error processing message on topic '%s'", msg.topic)


def _offline_check_loop() -> None:
    while True:
        time.sleep(settings.iot_offline_check_interval_seconds)
        db = SessionLocal()
        try:
            for tenant in db.query(fm.Tenant).all():
                set_tenant_context(db, tenant.id)
                alerts = check_offline_devices(db, tenant.id, settings.iot_offline_timeout_seconds)
                if alerts:
                    log.info("tenant '%s': %d device(s) marked offline", tenant.slug, len(alerts))
        except Exception:
            log.exception("error in offline-check loop")
        finally:
            db.close()


def main() -> None:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = _on_connect
    client.on_message = _on_message
    client.connect(settings.mqtt_host, settings.mqtt_port)

    threading.Thread(target=_offline_check_loop, daemon=True).start()

    log.info("IoT ingestion worker starting, broker=%s:%s", settings.mqtt_host, settings.mqtt_port)
    client.loop_forever()


if __name__ == "__main__":
    main()
