"""Small reusable helpers shared by anything that needs to create Digital
Twin Core rows programmatically (Tree-twin auto-linking in
`routers/v1/farm.py`, the legacy-equipment and tree-backfill migration
scripts) rather than through the `routers/v1/twins.py` API surface."""
from typing import Optional

from sqlalchemy.orm import Session

from . import models as twin_models


def get_or_create_twin_type(
    db: Session,
    tenant_id: str,
    *,
    code: str,
    name: str,
    category: str,
    is_ifc_sourced: bool = False,
) -> twin_models.TwinType:
    existing = (
        db.query(twin_models.TwinType)
        .filter(twin_models.TwinType.tenant_id == tenant_id, twin_models.TwinType.code == code)
        .one_or_none()
    )
    if existing:
        return existing
    twin_type = twin_models.TwinType(
        tenant_id=tenant_id, code=code, name=name, category=category, is_ifc_sourced=is_ifc_sourced
    )
    db.add(twin_type)
    db.flush()
    return twin_type


def create_twin(
    db: Session,
    *,
    tenant_id: str,
    twin_type: twin_models.TwinType,
    display_code: str,
    farm_id: Optional[str] = None,
    current_state: Optional[dict] = None,
    location_ref: Optional[dict] = None,
    model_ref: Optional[dict] = None,
    created_by: Optional[str] = None,
) -> twin_models.DigitalTwin:
    twin = twin_models.DigitalTwin(
        tenant_id=tenant_id,
        twin_type_id=twin_type.id,
        farm_id=farm_id,
        display_code=display_code,
        current_state=current_state or {},
        location_ref=location_ref or {},
        model_ref=model_ref or {},
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(twin)
    db.flush()
    return twin
