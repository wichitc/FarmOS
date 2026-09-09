"""CCTV & Vision AI (Phase 9, FR-CCTV / VIS) - see docs/03-BRD.md §7,
docs/04-SRS.md §5.

Explicitly non-MVP (docs/05-RTM.md) and no vision-model/RTSP vendor has
been chosen anywhere in the docs, so this phase is a deliberate stub: the
data model, human-review workflow, and hard safety constraints (FR-CCTV-004/
005) are real and enforced now; the inference engine is a no-op
(`app.vision.inference.StubVisionInferenceEngine`) until a real one is
wired in - same treatment as `health.py` (rule-engine placeholder) and
`app.weather.provider` (stub external provider).

`Camera` is a `DigitalTwin` extension row (category `"camera"`, already in
`TWIN_TYPE_CATEGORIES`), same shared-kernel pattern as `IotDevice` (Phase 7).

Confirmed detections do NOT create a Disease Incident here - that lifecycle
(Detected -> Suspected -> ... -> Resolved) belongs to Phase 10 (FR-HEALTH),
which will consume `Detection` rows with `validation_status="confirmed"` as
its input. Building a placeholder incident table now would just be a worse
version of what Phase 10 needs to design properly.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..foundation.models import TenantScopedMixin, gen_uuid

CAMERA_PROTOCOLS = ("rtsp", "onvif", "http")
VISION_USE_CASES = (
    "tree_health",
    "fruit_detection",
    "maturity_estimation",
    "disease_symptom",
    "intrusion",
    "worker_safety",
    "vehicle",
)
DETECTION_VALIDATION_STATUSES = ("pending", "confirmed", "rejected")


def _uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)


class Camera(TenantScopedMixin, Base):
    __tablename__ = "vision_cameras"

    id: Mapped[str] = _uuid_pk()
    digital_twin_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("digital_twins.id"), index=True)
    farm_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), index=True)
    protocol: Mapped[str] = mapped_column(String(20), default="rtsp")
    stream_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    fov_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class VisionModel(TenantScopedMixin, Base):
    """Catalog of "independently deployable models" (FR-CCTV-002) - a
    configuration row per use case/version, not a real model artifact or
    inference runtime; mirrors the `TwinType` configuration-catalog
    pattern."""

    __tablename__ = "vision_models"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_vision_models_tenant_code"),)

    id: Mapped[str] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255))
    use_case: Mapped[str] = mapped_column(String(30))
    version: Mapped[str] = mapped_column(String(30), default="stub")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Detection(TenantScopedMixin, Base):
    """FR-CCTV-003 / VIS-001/002/003. `frame_ref` is an object-storage key
    placeholder (VIS-001 requires persisting the source frame, not just
    metadata) - no real upload pipeline is wired to MinIO yet, so this is
    just where that reference will live once one is."""

    __tablename__ = "vision_detections"

    id: Mapped[str] = _uuid_pk()
    camera_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("vision_cameras.id"), index=True)
    model_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("vision_models.id"), index=True)
    tree_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("trees.id"), nullable=True)
    plot_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("plots.id"), nullable=True)
    detected_class: Mapped[str] = mapped_column(String(100))
    confidence: Mapped[float] = mapped_column(Float)
    bounding_box: Mapped[dict] = mapped_column(JSONB, default=dict)
    frame_ref: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    validation_status: Mapped[str] = mapped_column(String(20), default="pending")
    reviewed_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
