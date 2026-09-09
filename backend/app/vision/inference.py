"""Vision inference integration point (FR-CCTV-002). No real model/vendor
has been chosen, so there is nothing to run - this mirrors
`app.weather.provider`'s `WeatherProvider` stub pattern from Phase 8: a
`Protocol` a real inference runtime implements later, and a stub that's
honest about producing nothing rather than fabricating detections.

Detections enter the system today via `POST /api/v1/vision/cameras/{id}/detections`
directly (a human annotating a frame, or a test harness) - a future real
engine would call that same endpoint (or the same underlying service
function), not a different one, so wiring one in later is additive.
"""
from dataclasses import dataclass
from typing import Protocol


@dataclass
class DetectionCandidate:
    detected_class: str
    confidence: float
    bounding_box: dict
    frame_ref: str | None = None


class VisionInferenceEngine(Protocol):
    def run_inference(self, *, camera_id: str, use_case: str, frame_ref: str) -> list[DetectionCandidate]: ...


class StubVisionInferenceEngine:
    """No real model wired up - always returns no detections."""

    def run_inference(self, *, camera_id: str, use_case: str, frame_ref: str) -> list[DetectionCandidate]:
        return []


default_engine: VisionInferenceEngine = StubVisionInferenceEngine()
