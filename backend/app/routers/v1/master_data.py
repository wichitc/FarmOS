from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.deps import require_permission
from ...database import get_db
from ...foundation import models as fm
from ...foundation.audit import record_audit
from ...foundation.schemas import CropCreate, CropOut, VarietyCreate, VarietyOut

router = APIRouter(prefix="/api/v1/master-data", tags=["master-data"])


@router.get("/crops", response_model=list[CropOut])
def list_crops(
    db: Session = Depends(get_db),
    _user: fm.User = Depends(require_permission("master_data.crop.view")),
):
    return db.query(fm.Crop).order_by(fm.Crop.name_en.asc()).all()


@router.post("/crops", response_model=CropOut, status_code=201)
def create_crop(
    payload: CropCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("master_data.crop.manage")),
):
    crop = fm.Crop(
        tenant_id=current_user.tenant_id,
        code=payload.code,
        name_en=payload.name_en,
        name_th=payload.name_th,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(crop)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A crop with this code already exists") from exc

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="crop.create",
        entity_type="crop",
        entity_id=crop.id,
        new_values={"code": crop.code, "name_en": crop.name_en, "name_th": crop.name_th},
    )
    db.commit()
    return crop


@router.post("/crops/{crop_id}/varieties", response_model=VarietyOut, status_code=201)
def create_variety(
    crop_id: str,
    payload: VarietyCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("master_data.crop.manage")),
):
    crop = db.get(fm.Crop, crop_id)
    if not crop:
        raise HTTPException(status_code=404, detail="Crop not found")

    variety = fm.Variety(
        tenant_id=current_user.tenant_id,
        crop_id=crop_id,
        code=payload.code,
        name_en=payload.name_en,
        name_th=payload.name_th,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(variety)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A variety with this code already exists for this crop") from exc

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="variety.create",
        entity_type="variety",
        entity_id=variety.id,
        new_values={"crop_id": crop_id, "code": variety.code},
    )
    db.commit()
    return variety
