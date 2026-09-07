import os
import uuid

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models as db_models
from ..schemas import ModelOut
from ..config import settings

router = APIRouter(prefix="/api/models", tags=["models"])


@router.post("", response_model=ModelOut)
async def upload_model(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(".ifc"):
        raise HTTPException(status_code=400, detail="Only .ifc files are supported")

    os.makedirs(settings.data_dir, exist_ok=True)
    model_id = str(uuid.uuid4())
    dest_path = os.path.join(settings.data_dir, f"{model_id}.ifc")
    contents = await file.read()
    with open(dest_path, "wb") as f:
        f.write(contents)

    record = db_models.ModelRecord(id=model_id, name=file.filename, file_path=dest_path)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("", response_model=list[ModelOut])
def list_models(db: Session = Depends(get_db)):
    return db.query(db_models.ModelRecord).order_by(db_models.ModelRecord.uploaded_at.desc()).all()


@router.get("/{model_id}", response_model=ModelOut)
def get_model(model_id: str, db: Session = Depends(get_db)):
    record = db.get(db_models.ModelRecord, model_id)
    if not record:
        raise HTTPException(status_code=404, detail="Model not found")
    return record


@router.get("/{model_id}/file")
def get_model_file(model_id: str, db: Session = Depends(get_db)):
    record = db.get(db_models.ModelRecord, model_id)
    if not record or not os.path.exists(record.file_path):
        raise HTTPException(status_code=404, detail="Model file not found")
    return FileResponse(record.file_path, media_type="application/octet-stream", filename=record.name)


@router.delete("/{model_id}", status_code=204)
def delete_model(model_id: str, db: Session = Depends(get_db)):
    record = db.get(db_models.ModelRecord, model_id)
    if not record:
        raise HTTPException(status_code=404, detail="Model not found")
    if os.path.exists(record.file_path):
        os.remove(record.file_path)
    db.delete(record)
    db.commit()
    return None
