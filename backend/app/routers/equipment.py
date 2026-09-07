from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models as db_models
from ..schemas import EquipmentCreate, EquipmentUpdate, EquipmentOut, HealthOut
from ..health import compute_health

router = APIRouter(prefix="/api/equipment", tags=["equipment"])


@router.get("", response_model=list[EquipmentOut])
def list_equipment(model_id: Optional[str] = Query(None), db: Session = Depends(get_db)):
    q = db.query(db_models.Equipment)
    if model_id:
        q = q.filter(db_models.Equipment.model_id == model_id)
    else:
        q = q.filter(db_models.Equipment.model_id.is_(None))
    return q.order_by(db_models.Equipment.created_at.asc()).all()


@router.post("", response_model=EquipmentOut)
def create_equipment(payload: EquipmentCreate, db: Session = Depends(get_db)):
    if payload.model_id:
        model = db.get(db_models.ModelRecord, payload.model_id)
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")

    today = datetime.utcnow().date()
    record = db_models.Equipment(
        model_id=payload.model_id,
        type=payload.type,
        name=payload.name,
        pos_x=payload.pos_x,
        pos_y=payload.pos_y,
        pos_z=payload.pos_z,
        rotation_y=payload.rotation_y,
        scale=payload.scale,
        notes=payload.notes,
        status=payload.status or "running",
        install_date=payload.install_date or today,
        last_maintenance_date=payload.last_maintenance_date or today,
        operating_hours=payload.operating_hours if payload.operating_hours is not None else 0.0,
        temperature_c=payload.temperature_c,
        vibration_mm_s=payload.vibration_mm_s,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/{equipment_id}", response_model=EquipmentOut)
def get_equipment(equipment_id: str, db: Session = Depends(get_db)):
    record = db.get(db_models.Equipment, equipment_id)
    if not record:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return record


@router.put("/{equipment_id}", response_model=EquipmentOut)
def update_equipment(equipment_id: str, payload: EquipmentUpdate, db: Session = Depends(get_db)):
    record = db.get(db_models.Equipment, equipment_id)
    if not record:
        raise HTTPException(status_code=404, detail="Equipment not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/{equipment_id}", status_code=204)
def delete_equipment(equipment_id: str, db: Session = Depends(get_db)):
    record = db.get(db_models.Equipment, equipment_id)
    if not record:
        raise HTTPException(status_code=404, detail="Equipment not found")
    db.delete(record)
    db.commit()
    return None


@router.get("/{equipment_id}/health", response_model=HealthOut)
def get_equipment_health(equipment_id: str, db: Session = Depends(get_db)):
    record = db.get(db_models.Equipment, equipment_id)
    if not record:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return compute_health(record)
