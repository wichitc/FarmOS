from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.deps import assert_farm_scope, require_permission
from ...database import get_db
from ...farm import models as farm_models
from ...foundation import models as fm
from ...foundation.audit import record_audit
from ...twins import models as twin_models
from ...twins import schemas as twin_schemas

router = APIRouter(prefix="/api/v1/twins", tags=["twins"])


def _get_or_404(db: Session, model, obj_id: str, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


def _assert_twin_scope(db: Session, user: fm.User, permission_code: str, twin: twin_models.DigitalTwin) -> None:
    """Farm-scoped twins (e.g. a Tree's twin) go through the same ABAC
    narrowing as everything else in `app.farm`; a genuinely unscoped twin
    (`farm_id IS NULL`, mirroring legacy `Equipment.model_id IS NULL`) only
    needs the tenant-wide `require_permission` check the route already ran."""
    if twin.farm_id is not None:
        assert_farm_scope(db, user, permission_code, twin.farm_id)


# ---------------------------------------------------------------------------
# TwinType catalog
# ---------------------------------------------------------------------------

@router.post("/types", response_model=twin_schemas.TwinTypeOut, status_code=201)
def create_twin_type(
    payload: twin_schemas.TwinTypeCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("twin.manage")),
):
    if payload.category not in twin_models.TWIN_TYPE_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Unknown category '{payload.category}'")

    twin_type = twin_models.TwinType(
        tenant_id=current_user.tenant_id,
        code=payload.code,
        name=payload.name,
        category=payload.category,
        is_ifc_sourced=payload.is_ifc_sourced,
        property_schema=payload.property_schema,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(twin_type)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A twin type with this code already exists") from exc

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="twin_type.create",
        entity_type="twin_type",
        entity_id=twin_type.id,
        new_values={"code": twin_type.code, "category": twin_type.category},
    )
    db.commit()
    return twin_type


@router.get("/types", response_model=list[twin_schemas.TwinTypeOut])
def list_twin_types(
    db: Session = Depends(get_db),
    _user: fm.User = Depends(require_permission("twin.view")),
):
    return db.query(twin_models.TwinType).order_by(twin_models.TwinType.name.asc()).all()


# ---------------------------------------------------------------------------
# DigitalTwin
# ---------------------------------------------------------------------------

@router.post("", response_model=twin_schemas.DigitalTwinOut, status_code=201)
def create_twin(
    payload: twin_schemas.DigitalTwinCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("twin.manage")),
):
    twin_type = _get_or_404(db, twin_models.TwinType, payload.twin_type_id, "Twin type")
    if payload.farm_id:
        _get_or_404(db, farm_models.Farm, payload.farm_id, "Farm")
        assert_farm_scope(db, current_user, "twin.manage", payload.farm_id)

    twin = twin_models.DigitalTwin(
        tenant_id=current_user.tenant_id,
        twin_type_id=twin_type.id,
        farm_id=payload.farm_id,
        display_code=payload.display_code,
        current_state=payload.current_state,
        location_ref=payload.location_ref,
        model_ref=payload.model_ref,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(twin)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A twin with this display_code already exists") from exc

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="twin.create",
        entity_type="digital_twin",
        entity_id=twin.id,
        new_values={"twin_type_id": twin_type.id, "display_code": twin.display_code},
    )
    db.commit()
    return twin


@router.get("", response_model=list[twin_schemas.DigitalTwinOut])
def list_twins(
    farm_id: Optional[str] = Query(default=None),
    twin_type_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("twin.view")),
):
    if farm_id:
        assert_farm_scope(db, user, "twin.view", farm_id)

    query = db.query(twin_models.DigitalTwin).filter(twin_models.DigitalTwin.deleted_at.is_(None))
    if farm_id:
        query = query.filter(twin_models.DigitalTwin.farm_id == farm_id)
    if twin_type_id:
        query = query.filter(twin_models.DigitalTwin.twin_type_id == twin_type_id)
    return query.order_by(twin_models.DigitalTwin.display_code.asc()).all()


@router.get("/{twin_id}", response_model=twin_schemas.TwinInspectorOut)
def get_twin(
    twin_id: str,
    events_limit: int = Query(default=20, le=100),
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("twin.view")),
):
    """The "twin inspector" aggregate (TWIN-002): one consistent shape -
    current state, properties, recent events, latest telemetry per metric -
    regardless of the twin's type."""
    twin = _get_or_404(db, twin_models.DigitalTwin, twin_id, "Twin")
    _assert_twin_scope(db, user, "twin.view", twin)

    twin_type = db.get(twin_models.TwinType, twin.twin_type_id)
    properties = {p.key: p.value for p in twin.properties}
    recent_events = (
        db.query(twin_models.TwinEvent)
        .filter(twin_models.TwinEvent.twin_id == twin.id)
        .order_by(twin_models.TwinEvent.occurred_at.desc())
        .limit(events_limit)
        .all()
    )

    latest_telemetry: dict = {}
    telemetry_rows = (
        db.query(twin_models.TwinTelemetry)
        .filter(twin_models.TwinTelemetry.twin_id == twin.id)
        .order_by(twin_models.TwinTelemetry.recorded_at.desc())
        .all()
    )
    for row in telemetry_rows:
        if row.metric not in latest_telemetry:
            latest_telemetry[row.metric] = {
                "value_numeric": row.value_numeric,
                "value_text": row.value_text,
                "recorded_at": row.recorded_at.isoformat(),
            }

    return {
        "id": twin.id,
        "display_code": twin.display_code,
        "twin_type": twin_type,
        "farm_id": twin.farm_id,
        "current_state": twin.current_state,
        "status": twin.status,
        "properties": properties,
        "recent_events": recent_events,
        "latest_telemetry": latest_telemetry,
    }


@router.patch("/{twin_id}", response_model=twin_schemas.DigitalTwinOut)
def update_twin(
    twin_id: str,
    payload: twin_schemas.DigitalTwinUpdate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("twin.manage")),
):
    twin = _get_or_404(db, twin_models.DigitalTwin, twin_id, "Twin")
    _assert_twin_scope(db, current_user, "twin.manage", twin)

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(twin, field, value)
    twin.updated_by = current_user.id

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A twin with this display_code already exists") from exc

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="twin.update",
        entity_type="digital_twin",
        entity_id=twin.id,
        new_values=changes,
    )
    db.commit()
    return twin


@router.delete("/{twin_id}", status_code=204)
def delete_twin(
    twin_id: str,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("twin.manage")),
):
    twin = _get_or_404(db, twin_models.DigitalTwin, twin_id, "Twin")
    _assert_twin_scope(db, current_user, "twin.manage", twin)

    twin.deleted_at = datetime.now(timezone.utc)
    twin.status = "deleted"
    twin.updated_by = current_user.id
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="twin.delete",
        entity_type="digital_twin",
        entity_id=twin.id,
    )
    db.commit()


# ---------------------------------------------------------------------------
# Relationships (TWIN-003) - temporal, directed edges
# ---------------------------------------------------------------------------

@router.post("/{twin_id}/relationships", response_model=twin_schemas.TwinRelationshipOut, status_code=201)
def create_relationship(
    twin_id: str,
    payload: twin_schemas.TwinRelationshipCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("twin.manage")),
):
    from_twin = _get_or_404(db, twin_models.DigitalTwin, twin_id, "Twin")
    _assert_twin_scope(db, current_user, "twin.manage", from_twin)
    to_twin = _get_or_404(db, twin_models.DigitalTwin, payload.to_twin_id, "Target twin")

    relationship = twin_models.TwinRelationship(
        tenant_id=current_user.tenant_id,
        from_twin_id=from_twin.id,
        to_twin_id=to_twin.id,
        relation_type=payload.relation_type,
        valid_from=payload.valid_from or datetime.now(timezone.utc).date(),
        valid_to=payload.valid_to,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(relationship)
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="twin_relationship.create",
        entity_type="twin_relationship",
        entity_id=relationship.id,
        new_values={"from_twin_id": from_twin.id, "to_twin_id": to_twin.id, "relation_type": relationship.relation_type},
    )
    db.commit()
    return relationship


@router.get("/{twin_id}/relationships", response_model=list[twin_schemas.TwinRelationshipOut])
def list_relationships(
    twin_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("twin.view")),
):
    twin = _get_or_404(db, twin_models.DigitalTwin, twin_id, "Twin")
    _assert_twin_scope(db, user, "twin.view", twin)

    return (
        db.query(twin_models.TwinRelationship)
        .filter(or_(twin_models.TwinRelationship.from_twin_id == twin_id, twin_models.TwinRelationship.to_twin_id == twin_id))
        .order_by(twin_models.TwinRelationship.valid_from.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Properties (ADR-004's extension mechanism)
# ---------------------------------------------------------------------------

@router.put("/{twin_id}/properties", response_model=twin_schemas.TwinPropertyOut)
def set_property(
    twin_id: str,
    payload: twin_schemas.TwinPropertySet,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("twin.manage")),
):
    twin = _get_or_404(db, twin_models.DigitalTwin, twin_id, "Twin")
    _assert_twin_scope(db, current_user, "twin.manage", twin)

    prop = (
        db.query(twin_models.TwinProperty)
        .filter(twin_models.TwinProperty.twin_id == twin_id, twin_models.TwinProperty.key == payload.key)
        .one_or_none()
    )
    if prop:
        prop.value = payload.value
        prop.updated_by = current_user.id
    else:
        prop = twin_models.TwinProperty(
            tenant_id=current_user.tenant_id,
            twin_id=twin_id,
            key=payload.key,
            value=payload.value,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        db.add(prop)
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="twin_property.set",
        entity_type="twin_property",
        entity_id=prop.id,
        new_values={"twin_id": twin_id, "key": prop.key},
    )
    db.commit()
    return prop


@router.get("/{twin_id}/properties", response_model=list[twin_schemas.TwinPropertyOut])
def list_properties(
    twin_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("twin.view")),
):
    twin = _get_or_404(db, twin_models.DigitalTwin, twin_id, "Twin")
    _assert_twin_scope(db, user, "twin.view", twin)
    return db.query(twin_models.TwinProperty).filter(twin_models.TwinProperty.twin_id == twin_id).order_by(twin_models.TwinProperty.key.asc()).all()


# ---------------------------------------------------------------------------
# Events (append-only, TWIN-002 event timeline)
# ---------------------------------------------------------------------------

@router.post("/{twin_id}/events", response_model=twin_schemas.TwinEventOut, status_code=201)
def record_event(
    twin_id: str,
    payload: twin_schemas.TwinEventCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("twin.manage")),
):
    twin = _get_or_404(db, twin_models.DigitalTwin, twin_id, "Twin")
    _assert_twin_scope(db, current_user, "twin.manage", twin)

    event = twin_models.TwinEvent(
        tenant_id=current_user.tenant_id,
        twin_id=twin.id,
        event_type=payload.event_type,
        payload=payload.payload,
        occurred_at=payload.occurred_at or datetime.now(timezone.utc),
        created_by=current_user.id,
    )
    db.add(event)
    db.flush()
    db.commit()
    return event


@router.get("/{twin_id}/events", response_model=list[twin_schemas.TwinEventOut])
def list_events(
    twin_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("twin.view")),
):
    twin = _get_or_404(db, twin_models.DigitalTwin, twin_id, "Twin")
    _assert_twin_scope(db, user, "twin.view", twin)
    return (
        db.query(twin_models.TwinEvent)
        .filter(twin_models.TwinEvent.twin_id == twin_id)
        .order_by(twin_models.TwinEvent.occurred_at.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Telemetry (append-only, TWIN-004; shape only until Phase 7 IoT ingestion)
# ---------------------------------------------------------------------------

@router.post("/{twin_id}/telemetry", response_model=twin_schemas.TwinTelemetryOut, status_code=201)
def record_telemetry(
    twin_id: str,
    payload: twin_schemas.TwinTelemetryCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("twin.telemetry.write")),
):
    twin = _get_or_404(db, twin_models.DigitalTwin, twin_id, "Twin")
    _assert_twin_scope(db, current_user, "twin.telemetry.write", twin)

    reading = twin_models.TwinTelemetry(
        tenant_id=current_user.tenant_id,
        twin_id=twin.id,
        metric=payload.metric,
        value_numeric=payload.value_numeric,
        value_text=payload.value_text,
        recorded_at=payload.recorded_at or datetime.now(timezone.utc),
    )
    db.add(reading)
    db.commit()
    return reading


@router.get("/{twin_id}/telemetry", response_model=list[twin_schemas.TwinTelemetryOut])
def list_telemetry(
    twin_id: str,
    metric: Optional[str] = Query(default=None),
    limit: int = Query(default=100, le=1000),
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("twin.view")),
):
    twin = _get_or_404(db, twin_models.DigitalTwin, twin_id, "Twin")
    _assert_twin_scope(db, user, "twin.view", twin)

    query = db.query(twin_models.TwinTelemetry).filter(twin_models.TwinTelemetry.twin_id == twin_id)
    if metric:
        query = query.filter(twin_models.TwinTelemetry.metric == metric)
    return query.order_by(twin_models.TwinTelemetry.recorded_at.desc()).limit(limit).all()
