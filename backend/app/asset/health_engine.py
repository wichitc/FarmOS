"""Adapts `health.py`'s shared rule engine (FR-PDM-001) to an asset-category
`DigitalTwin`: pulls `temperature_c`/`vibration_mm_s`/`status` from
`current_state` (the same keys `migrate_equipment_to_twins.py` populates)
and `install_date`/`last_maintenance_date` from `TwinProperty` (also the
same keys that script writes), then calls the identical scoring function
the legacy `Equipment` health endpoint uses - one engine, two callers.
"""
from datetime import date

from sqlalchemy.orm import Session

from ..health import compute_health_score
from ..twins import models as twin_models


def _asset_subtype(twin_type_code: str) -> str:
    """`migrate_equipment_to_twins.py` names asset TwinTypes `asset:<subtype>`
    (e.g. `asset:pump`) so they sort/group separately from other categories
    in a shared per-tenant TwinType list; `health.py`'s THRESHOLDS table is
    keyed on the bare subtype."""
    return twin_type_code.split(":", 1)[1] if ":" in twin_type_code else twin_type_code


def _property_date(db: Session, twin_id: str, key: str) -> date | None:
    prop = (
        db.query(twin_models.TwinProperty)
        .filter(twin_models.TwinProperty.twin_id == twin_id, twin_models.TwinProperty.key == key)
        .one_or_none()
    )
    if prop is None or not prop.value:
        return None
    try:
        return date.fromisoformat(prop.value)
    except (TypeError, ValueError):
        return None


def assess_asset_health(db: Session, *, twin: twin_models.DigitalTwin, twin_type: twin_models.TwinType):
    state = twin.current_state or {}
    return compute_health_score(
        asset_type=_asset_subtype(twin_type.code),
        temperature_c=state.get("temperature_c"),
        vibration_mm_s=state.get("vibration_mm_s"),
        status=state.get("status", twin.status),
        last_maintenance_date=_property_date(db, twin.id, "last_maintenance_date"),
        install_date=_property_date(db, twin.id, "install_date"),
    )
