import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.deps import assert_farm_scope, require_permission
from ...core.security import hash_password
from ...database import get_db
from ...farm import models as farm_models
from ...foundation import models as fm
from ...foundation.audit import record_audit
from ...iot import models as iot_models
from ...iot import schemas as iot_schemas
from ...twins import models as twin_models
from ...twins.service import create_twin

router = APIRouter(prefix="/api/v1/iot", tags=["iot"])


def _get_or_404(db: Session, model, obj_id: str, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


# ---------------------------------------------------------------------------
# Devices / Gateways (FR-IOT-001) - a Device is a DigitalTwin underneath
# (ADR-004); IotDevice is the thin extension row.
# ---------------------------------------------------------------------------

@router.post("/devices", response_model=iot_schemas.DeviceRegisterOut, status_code=201)
def register_device(
    payload: iot_schemas.DeviceRegisterRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("iot.device.manage")),
):
    """Returns the plaintext secret exactly once - it is never stored or
    retrievable again, same one-time-reveal pattern as a password."""
    farm = _get_or_404(db, farm_models.Farm, payload.farm_id, "Farm")
    assert_farm_scope(db, current_user, "iot.device.manage", farm.id)

    twin_type = _get_or_404(db, twin_models.TwinType, payload.twin_type_id, "Twin type")
    if payload.protocol not in iot_models.DEVICE_PROTOCOLS:
        raise HTTPException(status_code=422, detail=f"Unknown protocol '{payload.protocol}'")
    if payload.gateway_id:
        _get_or_404(db, iot_models.IotDevice, payload.gateway_id, "Gateway")

    secret = secrets.token_urlsafe(32)
    twin = create_twin(
        db,
        tenant_id=current_user.tenant_id,
        twin_type=twin_type,
        display_code=payload.display_code,
        farm_id=farm.id,
        created_by=current_user.id,
    )
    device = iot_models.IotDevice(
        tenant_id=current_user.tenant_id,
        digital_twin_id=twin.id,
        farm_id=farm.id,
        device_key=payload.device_key,
        hashed_secret=hash_password(secret),
        protocol=payload.protocol,
        gateway_id=payload.gateway_id,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(device)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A device with this key already exists") from exc

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="iot_device.register",
        entity_type="iot_device",
        entity_id=device.id,
        new_values={"device_key": device.device_key, "protocol": device.protocol, "farm_id": farm.id},
    )
    db.commit()
    return iot_schemas.DeviceRegisterOut(**iot_schemas.DeviceOut.model_validate(device).model_dump(), secret=secret)


@router.get("/devices", response_model=list[iot_schemas.DeviceOut])
def list_devices(
    farm_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("iot.device.view")),
):
    if farm_id:
        assert_farm_scope(db, user, "iot.device.view", farm_id)
    query = db.query(iot_models.IotDevice)
    if farm_id:
        query = query.filter(iot_models.IotDevice.farm_id == farm_id)
    return query.order_by(iot_models.IotDevice.device_key.asc()).all()


@router.get("/devices/{device_id}", response_model=iot_schemas.DeviceOut)
def get_device(
    device_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("iot.device.view")),
):
    device = _get_or_404(db, iot_models.IotDevice, device_id, "Device")
    assert_farm_scope(db, user, "iot.device.view", device.farm_id)
    return device


# ---------------------------------------------------------------------------
# Rules (FR-IOT-004) - tenant-wide, not farm-scoped (a rule targets a
# TwinType, which is tenant-level configuration, same as Crop/Variety).
# ---------------------------------------------------------------------------

@router.post("/rules", response_model=iot_schemas.RuleOut, status_code=201)
def create_rule(
    payload: iot_schemas.RuleCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("iot.rule.manage")),
):
    _get_or_404(db, twin_models.TwinType, payload.twin_type_id, "Twin type")
    if payload.operator not in iot_models.RULE_OPERATORS:
        raise HTTPException(status_code=422, detail=f"Unknown operator '{payload.operator}'")
    if payload.severity not in iot_models.ALERT_SEVERITIES:
        raise HTTPException(status_code=422, detail=f"Unknown severity '{payload.severity}'")

    rule = iot_models.Rule(
        tenant_id=current_user.tenant_id,
        twin_type_id=payload.twin_type_id,
        metric=payload.metric,
        operator=payload.operator,
        threshold_value=payload.threshold_value,
        severity=payload.severity,
        message_template=payload.message_template,
        is_active=payload.is_active,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(rule)
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="iot_rule.create",
        entity_type="iot_rule",
        entity_id=rule.id,
        new_values={"metric": rule.metric, "operator": rule.operator, "threshold_value": rule.threshold_value},
    )
    db.commit()
    return rule


@router.get("/rules", response_model=list[iot_schemas.RuleOut])
def list_rules(
    db: Session = Depends(get_db),
    _user: fm.User = Depends(require_permission("iot.rule.view")),
):
    return db.query(iot_models.Rule).order_by(iot_models.Rule.metric.asc()).all()


# ---------------------------------------------------------------------------
# Alerts (FR-ALERT-001/002)
# ---------------------------------------------------------------------------

@router.get("/alerts", response_model=list[iot_schemas.AlertOut])
def list_alerts(
    status: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _user: fm.User = Depends(require_permission("alert.view")),
):
    query = db.query(iot_models.Alert)
    if status:
        query = query.filter(iot_models.Alert.status == status)
    if severity:
        query = query.filter(iot_models.Alert.severity == severity)
    return query.order_by(iot_models.Alert.raised_at.desc()).all()


@router.get("/alerts/{alert_id}", response_model=iot_schemas.AlertOut)
def get_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    _user: fm.User = Depends(require_permission("alert.view")),
):
    return _get_or_404(db, iot_models.Alert, alert_id, "Alert")


@router.post("/alerts/{alert_id}/acknowledge", response_model=iot_schemas.AlertOut)
def acknowledge_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("alert.manage")),
):
    alert = _get_or_404(db, iot_models.Alert, alert_id, "Alert")
    if alert.status != "open":
        raise HTTPException(status_code=409, detail=f"Alert is already {alert.status}")

    alert.status = "acknowledged"
    alert.acknowledged_at = datetime.now(timezone.utc)
    alert.acknowledged_by = current_user.id
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="iot_alert.acknowledge",
        entity_type="iot_alert",
        entity_id=alert.id,
    )
    db.commit()
    return alert


@router.post("/alerts/{alert_id}/resolve", response_model=iot_schemas.AlertOut)
def resolve_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("alert.manage")),
):
    alert = _get_or_404(db, iot_models.Alert, alert_id, "Alert")
    if alert.status == "resolved":
        raise HTTPException(status_code=409, detail="Alert is already resolved")

    alert.status = "resolved"
    alert.resolved_at = datetime.now(timezone.utc)
    alert.resolved_by = current_user.id
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="iot_alert.resolve",
        entity_type="iot_alert",
        entity_id=alert.id,
    )
    db.commit()
    return alert
