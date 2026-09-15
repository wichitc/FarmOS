"""Demo tenant + seed data (master prompt §46, §51): "AI Durian Farm" -
a populated tenant that works without any real hardware, so the platform
can be demoed cold. Idempotent on tenant slug: re-running against an
already-seeded demo tenant is a no-op (reports what already exists
rather than erroring or duplicating).

Registers real `IotDevice` rows via the same one-time-reveal secret flow
`routers/v1/iot.py::register_device` uses - the plaintext secrets are
never stored, so this script writes them to `demo_devices.json` (device
key -> secret) for `sensor_simulator.py` to read and publish with. This
mirrors how a real device's credentials are captured once at provisioning
time and kept by whoever manages the device - here, this file plays that
role for the simulator.

Usage: python -m app.scripts.seed_demo [--out /app/data/demo_devices.json]
"""
import argparse
import json
import secrets
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..core.security import hash_password
from ..crophealth import models as crophealth_models
from ..database import SessionLocal
from ..farm import models as farm_models
from ..foundation import models as fm
from ..foundation.seed import provision_tenant
from ..harvest import models as harvest_models
from ..iot import models as iot_models
from ..twins import models as twin_models
from ..twins.service import create_twin, get_or_create_twin_type
from ..weather import models as weather_models

DEMO_SLUG = "ai-durian-farm"
DEMO_ADMIN_EMAIL = "admin@ai-durian-farm.example.com"
DEMO_ADMIN_PASSWORD = "demo-farm-not-for-production"


def _register_device(db, *, tenant_id, farm_id, twin_type, device_key, display_code) -> tuple[iot_models.IotDevice, str]:
    secret = secrets.token_urlsafe(32)
    twin = create_twin(db, tenant_id=tenant_id, twin_type=twin_type, display_code=display_code, farm_id=farm_id)
    device = iot_models.IotDevice(
        tenant_id=tenant_id, digital_twin_id=twin.id, farm_id=farm_id,
        device_key=device_key, hashed_secret=hash_password(secret), protocol="mqtt",
    )
    db.add(device)
    db.flush()
    return device, secret


def seed_demo(out_path: str) -> dict:
    db = SessionLocal()
    try:
        tenant = db.query(fm.Tenant).filter(fm.Tenant.slug == DEMO_SLUG).one_or_none()
        if tenant is not None:
            print(f"Demo tenant '{DEMO_SLUG}' already exists ({tenant.id}) - not re-seeding.")
            return {"tenant_id": tenant.id, "already_existed": True}

        tenant, _admin = provision_tenant(
            db, slug=DEMO_SLUG, name="AI Durian Farm",
            admin_email=DEMO_ADMIN_EMAIL, admin_password=DEMO_ADMIN_PASSWORD, admin_full_name="Demo Admin",
        )

        crop = fm.Crop(tenant_id=tenant.id, code="durian", name_en="Durian", name_th="ทุเรียน")
        db.add(crop)
        db.flush()
        variety = fm.Variety(tenant_id=tenant.id, crop_id=crop.id, code="monthong", name_en="Monthong", name_th="หมอนทอง")
        db.add(variety)
        db.flush()

        # 100 rai (master prompt §46) = 16 hectares (1 rai = 0.16 ha).
        farm = farm_models.Farm(tenant_id=tenant.id, code="ADF-01", name="AI Durian Farm", area_hectares=16.0, lat=6.6, lng=101.28)
        db.add(farm)
        db.flush()

        sensor_type = get_or_create_twin_type(db, tenant.id, code="sensor-generic", name="Sensor", category="sensor")
        asset_type = get_or_create_twin_type(db, tenant.id, code="pump-generic", name="Pump", category="asset")
        tree_type = get_or_create_twin_type(db, tenant.id, code="durian-tree", name="Durian Tree", category="tree")

        secrets_out: dict[str, str] = {}
        tree_count = 0
        for zone_idx in range(1, 3):  # 2 zones
            zone = farm_models.Zone(tenant_id=tenant.id, farm_id=farm.id, code=f"Z{zone_idx}", name=f"Zone {zone_idx}")
            db.add(zone)
            db.flush()

            if zone_idx == 1:
                pump_twin = create_twin(db, tenant_id=tenant.id, twin_type=asset_type, display_code=f"PUMP-Z{zone_idx}", farm_id=farm.id, current_state={"status": "idle"})

            plot = farm_models.Plot(tenant_id=tenant.id, zone_id=zone.id, code="P1", name=f"Plot {zone_idx}-1", area_hectares=8.0)
            db.add(plot)
            db.flush()

            moisture_device, secret = _register_device(
                db, tenant_id=tenant.id, farm_id=farm.id, twin_type=sensor_type,
                device_key=f"soil-moisture-z{zone_idx}", display_code=f"Soil Moisture Z{zone_idx}",
            )
            secrets_out[moisture_device.device_key] = secret

            block = farm_models.Block(tenant_id=tenant.id, plot_id=plot.id, code="B1", name="Block 1", area_hectares=8.0)
            db.add(block)
            db.flush()
            row = farm_models.Row(tenant_id=tenant.id, block_id=block.id, code="R1", name="Row 1", spacing_m=8.0)
            db.add(row)
            db.flush()

            for tree_idx in range(1, 4):  # 3 trees per row
                tree_count += 1
                tree_twin = create_twin(db, tenant_id=tenant.id, twin_type=tree_type, display_code=f"TREE-{tree_count:03d}", farm_id=farm.id)
                tree = farm_models.Tree(
                    tenant_id=tenant.id, row_id=row.id, crop_id=crop.id, variety_id=variety.id,
                    digital_twin_id=tree_twin.id, code=f"TREE-{tree_count:03d}",
                    planting_date=date.today() - timedelta(days=365 * 3), growth_stage="fruiting",
                )
                db.add(tree)

        temp_device, secret = _register_device(db, tenant_id=tenant.id, farm_id=farm.id, twin_type=sensor_type, device_key="weather-temp-01", display_code="Weather Station - Temp")
        secrets_out[temp_device.device_key] = secret
        humidity_device, secret = _register_device(db, tenant_id=tenant.id, farm_id=farm.id, twin_type=sensor_type, device_key="weather-humidity-01", display_code="Weather Station - Humidity")
        secrets_out[humidity_device.device_key] = secret
        rain_device, secret = _register_device(db, tenant_id=tenant.id, farm_id=farm.id, twin_type=sensor_type, device_key="weather-rain-01", display_code="Weather Station - Rainfall")
        secrets_out[rain_device.device_key] = secret

        # A little illustrative history so the demo isn't a completely blank slate.
        db.add(weather_models.WeatherReading(tenant_id=tenant.id, farm_id=farm.id, metric="temperature_c", value=32.5, source="station", observed_at=datetime.now(timezone.utc), recorded_at=datetime.now(timezone.utc)))
        db.add(harvest_models.YieldForecast(
            tenant_id=tenant.id, farm_id=farm.id, estimated_yield_kg_low=1800.0, estimated_yield_kg_high=2400.0,
            confidence=0.6, basis={"tree_count": tree_count, "note": "demo seed baseline"}, forecast_date=datetime.now(timezone.utc),
        ))
        disease = crophealth_models.Disease(tenant_id=tenant.id, code="anthracnose", name_en="Anthracnose", name_th="แอนแทรคโนส", pathogen_type="fungal")
        db.add(disease)
        db.flush()
        db.add(crophealth_models.DiseaseIncident(tenant_id=tenant.id, farm_id=farm.id, disease_id=disease.id, status="detected", evidence={"note": "demo seed baseline"}))

        db.commit()

        out_file = Path(out_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps({"tenant_slug": DEMO_SLUG, "devices": secrets_out}, indent=2))

        print(f"Seeded demo tenant '{DEMO_SLUG}' ({tenant.id}): 1 farm, {tree_count} trees, {len(secrets_out)} sensors.")
        print(f"Device credentials written to {out_file}")
        print(f"Login: {DEMO_ADMIN_EMAIL} / {DEMO_ADMIN_PASSWORD}")
        return {"tenant_id": tenant.id, "already_existed": False, "device_count": len(secrets_out), "tree_count": tree_count}
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="data/demo_devices.json", help="Where to write device_key -> secret credentials")
    args = parser.parse_args()
    seed_demo(args.out)


if __name__ == "__main__":
    main()
