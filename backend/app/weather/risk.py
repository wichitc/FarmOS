"""Weather risk banding (master-prompt integration, Phase 32) - the
single source of truth for "what counts as risky weather", extracted
from `ai/farm_score.py` (Phase 27) which originally kept these bands
private with a documented note that duplicating them for a second
consumer wasn't worth it yet. The Weather Agent wiring below
(`routers/v1/weather.py::ingest_reading`) is that second consumer, so
the bands live here now and `farm_score.py` imports them instead of
carrying its own copy.

Same normal/warning/anomaly shape `sensor_simulator.py` (Phase 23)
already generates values against - that script produces values, this
module classifies them, so a small duplication of the band boundaries
against a scripts/-not-app/ module remains the simplest honest option.
"""
from typing import Optional

WEATHER_RISK_RANGES: dict[str, dict[str, tuple[float, float]]] = {
    "temperature_c": {"warning": (36, 40), "anomaly": (41, 200)},
    "humidity_pct": {"warning": (85, 95), "anomaly": (96, 100)},
}


def classify_weather_risk(metric: str, value: float) -> Optional[str]:
    """Returns "anomaly", "warning", or None - None both for a normal
    value and for a metric with no defined bands (not every metric this
    platform tracks is risk-classified)."""
    ranges = WEATHER_RISK_RANGES.get(metric)
    if ranges is None:
        return None
    anomaly_low, anomaly_high = ranges["anomaly"]
    if anomaly_low <= value <= anomaly_high:
        return "anomaly"
    warning_low, warning_high = ranges["warning"]
    if warning_low <= value <= warning_high:
        return "warning"
    return None
