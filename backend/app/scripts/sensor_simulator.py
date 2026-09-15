"""Sensor simulator (master prompt §47): generates realistic readings for
the demo tenant's registered devices and publishes them over MQTT to the
exact topic/payload shape `mqtt_ingestion_worker.py` already consumes
(`tenants/{tenant_slug}/devices/{device_key}/telemetry`) - this is a real
publisher exercising the real ingestion path, not a shortcut that calls
`process_reading()` directly.

Reads device credentials from the file `seed_demo.py` wrote (the
plaintext secret is only ever known once, at registration - this file is
this demo's stand-in for wherever a real device's credentials would be
kept). Requires `seed_demo.py` to have been run first.

Value ranges follow the platform brief's own worked example (soil
moisture 48=normal, 18=warning, 5=critical). Default mode "auto" mostly
generates normal readings with occasional random warning/anomaly values,
so a demo feels alive without manual flag-flipping; `--mode` pins every
reading to one band for a deterministic demo instead.

Usage:
    python -m app.scripts.sensor_simulator [--devices data/demo_devices.json]
        [--mode auto|normal|warning|anomaly] [--interval 10] [--once]
"""
import argparse
import json
import random
import time
from pathlib import Path

import paho.mqtt.client as mqtt

from ..config import settings

# (low, high) per band, per metric.
_RANGES = {
    "soil_moisture_pct": {"normal": (35, 60), "warning": (12, 25), "anomaly": (0, 8)},
    "temperature_c": {"normal": (26, 34), "warning": (36, 40), "anomaly": (41, 46)},
    "humidity_pct": {"normal": (50, 80), "warning": (85, 95), "anomaly": (96, 100)},
    "rainfall_mm": {"normal": (0, 5), "warning": (10, 25), "anomaly": (40, 80)},
}

_MODE_WEIGHTS = {"normal": 0.85, "warning": 0.10, "anomaly": 0.05}


def _metric_for_device_key(device_key: str) -> str:
    if device_key.startswith("soil-moisture"):
        return "soil_moisture_pct"
    if "temp" in device_key:
        return "temperature_c"
    if "humidity" in device_key:
        return "humidity_pct"
    if "rain" in device_key:
        return "rainfall_mm"
    return "temperature_c"


def _pick_mode(forced_mode: str) -> str:
    if forced_mode != "auto":
        return forced_mode
    return random.choices(list(_MODE_WEIGHTS), weights=list(_MODE_WEIGHTS.values()))[0]


def generate_reading(device_key: str, mode: str) -> tuple[str, float, str]:
    """Returns (metric, value, band) - band is returned for the printed
    log line only, not part of the published payload (a real sensor
    doesn't know its own threshold classification; that's the platform's
    rules engine's job, per Phase 7's `iot.Rule`)."""
    metric = _metric_for_device_key(device_key)
    band = _pick_mode(mode)
    low, high = _RANGES[metric][band]
    value = round(random.uniform(low, high), 1)
    return metric, value, band


def publish_once(client: mqtt.Client, tenant_slug: str, device_key: str, secret: str, mode: str) -> None:
    metric, value, band = generate_reading(device_key, mode)
    topic = f"tenants/{tenant_slug}/devices/{device_key}/telemetry"
    payload = json.dumps({"metric": metric, "value": value, "secret": secret})
    client.publish(topic, payload)
    print(f"[{band:8s}] {device_key:24s} {metric}={value}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--devices", default="data/demo_devices.json")
    parser.add_argument("--mode", choices=["auto", "normal", "warning", "anomaly"], default="auto")
    parser.add_argument("--interval", type=float, default=10.0, help="Seconds between rounds")
    parser.add_argument("--once", action="store_true", help="Publish one round for every device, then exit")
    args = parser.parse_args()

    devices_path = Path(args.devices)
    if not devices_path.exists():
        raise SystemExit(f"{devices_path} not found - run `python -m app.scripts.seed_demo` first")
    config = json.loads(devices_path.read_text())
    tenant_slug = config["tenant_slug"]
    devices: dict[str, str] = config["devices"]

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(settings.mqtt_host, settings.mqtt_port)
    client.loop_start()

    print(f"Simulating {len(devices)} device(s) for tenant '{tenant_slug}', mode={args.mode}")
    try:
        while True:
            for device_key, secret in devices.items():
                publish_once(client, tenant_slug, device_key, secret, args.mode)
            if args.once:
                break
            time.sleep(args.interval)
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
