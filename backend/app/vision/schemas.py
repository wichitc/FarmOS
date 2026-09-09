from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CameraRegisterRequest(BaseModel):
    farm_id: str
    twin_type_id: str
    display_code: str
    protocol: str = "rtsp"
    stream_url: Optional[str] = None
    fov_metadata: dict = {}


class CameraOut(BaseModel):
    id: str
    digital_twin_id: str
    farm_id: str
    protocol: str
    stream_url: Optional[str] = None
    fov_metadata: dict
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class VisionModelCreate(BaseModel):
    code: str
    name: str
    use_case: str
    version: str = "stub"
    is_active: bool = True


class VisionModelOut(BaseModel):
    id: str
    code: str
    name: str
    use_case: str
    version: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class DetectionCreate(BaseModel):
    model_id: str
    tree_id: Optional[str] = None
    plot_id: Optional[str] = None
    detected_class: str
    confidence: float
    bounding_box: dict = {}
    frame_ref: Optional[str] = None
    detected_at: Optional[datetime] = None


class DetectionOut(BaseModel):
    id: str
    camera_id: str
    model_id: str
    tree_id: Optional[str] = None
    plot_id: Optional[str] = None
    detected_class: str
    confidence: float
    bounding_box: dict
    frame_ref: Optional[str] = None
    detected_at: datetime
    validation_status: str
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DetectionReviewRequest(BaseModel):
    notes: Optional[str] = None
