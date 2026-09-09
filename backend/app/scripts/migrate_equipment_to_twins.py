"""Migrates legacy (pre-Phase-3, unauthenticated) `Equipment` rows into the
Phase 6 Digital Twin Core, per SRS TWIN-005 and
docs/00-EXISTING-CODEBASE-ANALYSIS.md §4's migration mapping.

`tree_*`-prefixed rows are deliberately skipped: Phase 4 already gave trees
a real `farm.models.Tree` domain table with actual agronomic data, so
migrating the old placeholder tree-shaped Equipment rows would only create
confusing duplicates of a twin whose real data already lives elsewhere (see
`backfill_tree_twins.py` for that side instead).

The legacy `equipment`/`models` tables have no tenant_id - this script
attaches the migrated twins to whichever tenant slug you pass; running it
twice against the same tenant is safe (a `legacy_equipment_id` TwinProperty
marker is checked before creating a duplicate).

Usage: python -m app.scripts.migrate_equipment_to_twins <tenant_slug>
"""
import sys

from sqlalchemy import text

from .. import models as legacy_models
from ..core.deps import set_tenant_context
from ..database import SessionLocal
from ..farm import models as farm_models  # noqa: F401 - registers `farms` etc. for DigitalTwin.farm_id's FK
from ..foundation import models as fm
from ..twins import models as twin_models
from ..twins.service import create_twin, get_or_create_twin_type


def _already_migrated(db, tenant_id: str, equipment_id: str) -> bool:
    # `to_jsonb(:id::text)` builds the same JSON-string representation the
    # ORM writes when a plain Python str is assigned to a JSONB column, so
    # this compares jsonb = jsonb rather than jsonb = varchar (which Postgres
    # has no operator for).
    row = db.execute(
        text(
            "SELECT 1 FROM twin_properties "
            "WHERE tenant_id = :tid AND key = 'legacy_equipment_id' AND value = to_jsonb(CAST(:eid AS text)) LIMIT 1"
        ),
        {"tid": tenant_id, "eid": equipment_id},
    ).first()
    return row is not None


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)
    slug = sys.argv[1]

    db = SessionLocal()
    try:
        tenant = db.query(fm.Tenant).filter(fm.Tenant.slug == slug).one_or_none()
        if tenant is None:
            print(f"No tenant with slug '{slug}'")
            raise SystemExit(1)
        set_tenant_context(db, tenant.id)

        equipment_rows = (
            db.query(legacy_models.Equipment)
            .filter(~legacy_models.Equipment.type.like("tree_%"))
            .all()
        )

        migrated = 0
        skipped = 0
        for equipment in equipment_rows:
            if _already_migrated(db, tenant.id, equipment.id):
                skipped += 1
                continue

            twin_type = get_or_create_twin_type(
                db, tenant.id, code=f"asset:{equipment.type}", name=equipment.type.replace("_", " ").title(), category="asset"
            )
            twin = create_twin(
                db,
                tenant_id=tenant.id,
                twin_type=twin_type,
                display_code=equipment.name or f"{equipment.type}-{equipment.id[:8]}",
                current_state={
                    "status": equipment.status,
                    "temperature_c": equipment.temperature_c,
                    "vibration_mm_s": equipment.vibration_mm_s,
                    "operating_hours": equipment.operating_hours,
                },
                location_ref={
                    "pos_x": equipment.pos_x,
                    "pos_y": equipment.pos_y,
                    "pos_z": equipment.pos_z,
                    "rotation_y": equipment.rotation_y,
                    "scale": equipment.scale,
                },
                model_ref={"legacy_model_id": equipment.model_id} if equipment.model_id else {},
            )

            for key, value in {
                "legacy_equipment_id": equipment.id,
                "install_date": equipment.install_date.isoformat() if equipment.install_date else None,
                "last_maintenance_date": equipment.last_maintenance_date.isoformat() if equipment.last_maintenance_date else None,
                "notes": equipment.notes,
            }.items():
                if value is not None:
                    db.add(twin_models.TwinProperty(tenant_id=tenant.id, twin_id=twin.id, key=key, value=value))

            migrated += 1

        db.commit()
        print(f"Migrated {migrated} equipment record(s) into digital twins for tenant '{slug}' ({skipped} already migrated).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
