import json

from app.core.deps import set_tenant_context
from app.farm import models as farm_models
from app.foundation import models as fm
from app.iot import models as iot_models
from app.scripts.seed_demo import DEMO_SLUG, seed_demo


def test_seed_demo_is_idempotent_and_populates_real_data(tmp_path, raw_db):
    out_path = str(tmp_path / "demo_devices.json")
    result = seed_demo(out_path)

    tenant = raw_db.query(fm.Tenant).filter(fm.Tenant.slug == DEMO_SLUG).one_or_none()
    assert tenant is not None

    if not result["already_existed"]:
        assert result["device_count"] == 5  # 2 soil-moisture + temp + humidity + rain
        assert result["tree_count"] == 6  # 2 zones x 3 trees

        creds = json.loads((tmp_path / "demo_devices.json").read_text())
        assert creds["tenant_slug"] == DEMO_SLUG
        assert len(creds["devices"]) == 5
        assert "soil-moisture-z1" in creds["devices"]

        set_tenant_context(raw_db, tenant.id)
        farms = raw_db.query(farm_models.Farm).filter(farm_models.Farm.tenant_id == tenant.id).all()
        assert len(farms) == 1
        assert farms[0].area_hectares == 16.0

        devices = raw_db.query(iot_models.IotDevice).filter(iot_models.IotDevice.tenant_id == tenant.id).all()
        assert len(devices) == 5

    # Idempotency: calling again against the same (now-existing) tenant is a no-op.
    second_out_path = str(tmp_path / "demo_devices_2.json")
    second_result = seed_demo(second_out_path)
    assert second_result["already_existed"] is True
    assert second_result["tenant_id"] == tenant.id
