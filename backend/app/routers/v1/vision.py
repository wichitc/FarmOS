from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.deps import assert_farm_scope, require_permission
from ...database import get_db
from ...farm import models as farm_models
from ...foundation import models as fm
from ...foundation.audit import record_audit
from ...twins.models import TwinType
from ...twins.service import create_twin
from ...vision import models as vision_models
from ...vision import schemas as vision_schemas

router = APIRouter(prefix="/api/v1/vision", tags=["vision"])


def _get_or_404(db: Session, model, obj_id: str, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


# ---------------------------------------------------------------------------
# Cameras (FR-CCTV-001) - a Camera is a DigitalTwin underneath (ADR-004),
# same pattern as IotDevice (Phase 7).
# ---------------------------------------------------------------------------

@router.post("/cameras", response_model=vision_schemas.CameraOut, status_code=201)
def register_camera(
    payload: vision_schemas.CameraRegisterRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("vision.camera.manage")),
):
    farm = _get_or_404(db, farm_models.Farm, payload.farm_id, "Farm")
    assert_farm_scope(db, current_user, "vision.camera.manage", farm.id)
    twin_type = _get_or_404(db, TwinType, payload.twin_type_id, "Twin type")
    if payload.protocol not in vision_models.CAMERA_PROTOCOLS:
        raise HTTPException(status_code=422, detail=f"Unknown protocol '{payload.protocol}'")

    twin = create_twin(
        db,
        tenant_id=current_user.tenant_id,
        twin_type=twin_type,
        display_code=payload.display_code,
        farm_id=farm.id,
        created_by=current_user.id,
    )
    camera = vision_models.Camera(
        tenant_id=current_user.tenant_id,
        digital_twin_id=twin.id,
        farm_id=farm.id,
        protocol=payload.protocol,
        stream_url=payload.stream_url,
        fov_metadata=payload.fov_metadata,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(camera)
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="vision_camera.register",
        entity_type="vision_camera",
        entity_id=camera.id,
        new_values={"farm_id": farm.id, "protocol": camera.protocol},
    )
    db.commit()
    return camera


@router.get("/cameras", response_model=list[vision_schemas.CameraOut])
def list_cameras(
    farm_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("vision.camera.view")),
):
    if farm_id:
        assert_farm_scope(db, user, "vision.camera.view", farm_id)
    query = db.query(vision_models.Camera)
    if farm_id:
        query = query.filter(vision_models.Camera.farm_id == farm_id)
    return query.order_by(vision_models.Camera.created_at.asc()).all()


@router.get("/cameras/{camera_id}", response_model=vision_schemas.CameraOut)
def get_camera(
    camera_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("vision.camera.view")),
):
    camera = _get_or_404(db, vision_models.Camera, camera_id, "Camera")
    assert_farm_scope(db, user, "vision.camera.view", camera.farm_id)
    return camera


# ---------------------------------------------------------------------------
# Vision model catalog (FR-CCTV-002) - configuration rows, not real model
# artifacts; tenant-wide, mirrors TwinType.
# ---------------------------------------------------------------------------

@router.post("/models", response_model=vision_schemas.VisionModelOut, status_code=201)
def create_vision_model(
    payload: vision_schemas.VisionModelCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("vision.model.manage")),
):
    if payload.use_case not in vision_models.VISION_USE_CASES:
        raise HTTPException(status_code=422, detail=f"Unknown use_case '{payload.use_case}'")

    model = vision_models.VisionModel(
        tenant_id=current_user.tenant_id,
        code=payload.code,
        name=payload.name,
        use_case=payload.use_case,
        version=payload.version,
        is_active=payload.is_active,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(model)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A vision model with this code already exists") from exc

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="vision_model.create",
        entity_type="vision_model",
        entity_id=model.id,
        new_values={"code": model.code, "use_case": model.use_case},
    )
    db.commit()
    return model


@router.get("/models", response_model=list[vision_schemas.VisionModelOut])
def list_vision_models(
    db: Session = Depends(get_db),
    _user: fm.User = Depends(require_permission("vision.model.view")),
):
    return db.query(vision_models.VisionModel).order_by(vision_models.VisionModel.name.asc()).all()


# ---------------------------------------------------------------------------
# Detections (FR-CCTV-003 / VIS-001..003) - entered directly today (see
# app.vision.inference's module docstring); a real inference engine calls
# the same path later.
# ---------------------------------------------------------------------------

@router.post("/cameras/{camera_id}/detections", response_model=vision_schemas.DetectionOut, status_code=201)
def create_detection(
    camera_id: str,
    payload: vision_schemas.DetectionCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("vision.detection.manage")),
):
    camera = _get_or_404(db, vision_models.Camera, camera_id, "Camera")
    assert_farm_scope(db, current_user, "vision.detection.manage", camera.farm_id)
    model = _get_or_404(db, vision_models.VisionModel, payload.model_id, "Vision model")
    if payload.tree_id:
        _get_or_404(db, farm_models.Tree, payload.tree_id, "Tree")
    if payload.plot_id:
        _get_or_404(db, farm_models.Plot, payload.plot_id, "Plot")

    detection = vision_models.Detection(
        tenant_id=current_user.tenant_id,
        camera_id=camera.id,
        model_id=model.id,
        tree_id=payload.tree_id,
        plot_id=payload.plot_id,
        detected_class=payload.detected_class,
        confidence=payload.confidence,
        bounding_box=payload.bounding_box,
        frame_ref=payload.frame_ref,
        detected_at=payload.detected_at or datetime.now(timezone.utc),
        validation_status="pending",
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(detection)
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="vision_detection.create",
        entity_type="vision_detection",
        entity_id=detection.id,
        new_values={"camera_id": camera.id, "detected_class": detection.detected_class, "confidence": detection.confidence},
    )
    db.commit()
    return detection


@router.get("/cameras/{camera_id}/detections", response_model=list[vision_schemas.DetectionOut])
def list_camera_detections(
    camera_id: str,
    validation_status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("vision.detection.view")),
):
    camera = _get_or_404(db, vision_models.Camera, camera_id, "Camera")
    assert_farm_scope(db, user, "vision.detection.view", camera.farm_id)
    query = db.query(vision_models.Detection).filter(vision_models.Detection.camera_id == camera_id)
    if validation_status:
        query = query.filter(vision_models.Detection.validation_status == validation_status)
    return query.order_by(vision_models.Detection.detected_at.desc()).all()


@router.get("/detections/{detection_id}", response_model=vision_schemas.DetectionOut)
def get_detection(
    detection_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("vision.detection.view")),
):
    detection = _get_or_404(db, vision_models.Detection, detection_id, "Detection")
    camera = _get_or_404(db, vision_models.Camera, detection.camera_id, "Camera")
    assert_farm_scope(db, user, "vision.detection.view", camera.farm_id)
    return detection


def _review_detection(detection_id: str, status: str, notes: Optional[str], db: Session, current_user: fm.User):
    detection = _get_or_404(db, vision_models.Detection, detection_id, "Detection")
    camera = _get_or_404(db, vision_models.Camera, detection.camera_id, "Camera")
    assert_farm_scope(db, current_user, "vision.detection.manage", camera.farm_id)
    if detection.validation_status != "pending":
        raise HTTPException(status_code=409, detail=f"Detection already {detection.validation_status}")

    detection.validation_status = status
    detection.reviewed_by = current_user.id
    detection.reviewed_at = datetime.now(timezone.utc)
    detection.review_notes = notes
    detection.updated_by = current_user.id
    db.flush()

    # FR-CCTV-004/005 (VIS-002): confirming a detection does NOT, by itself,
    # create a Disease Incident or trigger any treatment - that lifecycle is
    # Phase 10's (FR-HEALTH). There is deliberately no code path here that
    # does either.
    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action=f"vision_detection.{status}",
        entity_type="vision_detection",
        entity_id=detection.id,
        reason=notes,
    )
    db.commit()
    return detection


@router.post("/detections/{detection_id}/confirm", response_model=vision_schemas.DetectionOut)
def confirm_detection(
    detection_id: str,
    payload: vision_schemas.DetectionReviewRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("vision.detection.manage")),
):
    return _review_detection(detection_id, "confirmed", payload.notes, db, current_user)


@router.post("/detections/{detection_id}/reject", response_model=vision_schemas.DetectionOut)
def reject_detection(
    detection_id: str,
    payload: vision_schemas.DetectionReviewRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("vision.detection.manage")),
):
    return _review_detection(detection_id, "rejected", payload.notes, db, current_user)
