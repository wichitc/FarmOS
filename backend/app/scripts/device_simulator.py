"""Device simulator (FR-IOT-005): publishes randomized MQTT readings for a
registered device so the ingestion pipeline, rules engine, and alerts can be
developed/demoed/tested without physical hardware.

Usage:
    python -m app.scripts.device_simulator <tenant_slug> <device_key> <device_secret> \
        [--metric temp_c] [--min 20] [--max 35] [--interval 5] [--count 0]

`--count 0` (default) publishes forever; any other value stops after N readings.
"""
import argparse
import json
import random
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from ..config import settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tenant_slug")
    parser.add_argument("device_key")
    parser.add_argument("device_secret")
    parser.add_argument("--metric", default="temp_c")
    parser.add_argument("--min", type=float, default=20.0)
    parser.add_argument("--max", type=float, default=35.0)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--count", type=int, default=0, help="0 = publish forever")
    args = parser.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(settings.mqtt_host, settings.mqtt_port)
    client.loop_start()

    topic = f"tenants/{args.tenant_slug}/devices/{args.device_key}/telemetry"
    published = 0
    try:
        while args.count == 0 or published < args.count:
            value = round(random.uniform(args.min, args.max), 2)
            payload = {
                "metric": args.metric,
                "value": value,
                "secret": args.device_secret,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
            client.publish(topic, json.dumps(payload))
            print(f"published {topic} -> {payload}")
            published += 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
