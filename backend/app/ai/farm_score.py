"""AI Farm Score (master prompt §26/§48) - a single 0-100 composite score
combining real signals other phases already compute (equipment health,
disease risk, weather, sensor connectivity), with a GOOD/WARNING/RISK/
CRITICAL band and a plain-language explanation of what's pulling the
score down ("ทำไม Score ลดลง" - why the score dropped), per the master
prompt's own requirement that the score never be a bare, unexplained
number.

Same "indicative rule-based weighting, not a calibrated model" treatment
every other placeholder engine in this platform gets (health.py,
crophealth.risk, irrigation.recommendation) - a real function with real
inputs and a documented, swappable formula, not a random number.

Only combines factors this platform actually has a real score for today:
Equipment Health (Phase 12), Disease Risk (Phase 10), Weather (Phase 8),
and Sensor Connectivity (Phase 7). The master prompt's fuller list (Soil
Health, Water Health, Pest Risk as distinct from Disease Risk) has no
dedicated scoring engine yet - see docs/05-RTM.md's Phase 27 checklist
for why those are left out rather than faked.
"""
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from ..crophealth import models as crophealth_models
from ..dashboard.aggregation import equipment_health_widget
from ..iot import models as iot_models
from ..weather.provider import current_reading

# Weights sum to 100 - each factor contributes its 0-100 sub-score
# proportionally. A factor with no data defaults to 100 (benefit of the
# doubt) but is called out explicitly in `factors` as "no data" rather
# than silently inflating the score without saying so.
FACTOR_WEIGHTS = {"equipment_health": 0.30, "disease_risk": 0.30, "weather": 0.20, "sensor_connectivity": 0.20}

# Master prompt §26's own bands.
BAND_THRESHOLDS = (("good", 80), ("warning", 60), ("risk", 40), ("critical", 0))

_WEATHER_RISK_RANGES = {
    # Same normal/warning/anomaly bands `sensor_simulator.py` (Phase 23)
    # already uses, reused here so "what counts as risky weather" is
    # defined in exactly one place... except the simulator generates
    # values, this reads them, so duplicating the band boundaries here
    # (not importing the simulator, which is scripts/ not app/) is the
    # simplest honest option - see the RTM deferral note.
    "temperature_c": {"warning": (36, 40), "anomaly": (41, 200)},
    "humidity_pct": {"warning": (85, 95), "anomaly": (96, 100)},
}


@dataclass
class ScoreFactor:
    name: str
    score: float
    weight: float
    explanation: str
    has_data: bool = True


@dataclass
class FarmScoreResult:
    score: int
    band: str
    factors: list[ScoreFactor] = field(default_factory=list)


def _band_for(score: float) -> str:
    for band, threshold in BAND_THRESHOLDS:
        if score >= threshold:
            return band
    return "critical"


def _equipment_health_factor(db: Session, tenant_id: str, farm_id: str) -> ScoreFactor:
    widget = equipment_health_widget(db, tenant_id, farm_id=farm_id)
    if widget.total == 0:
        return ScoreFactor("equipment_health", 100.0, FACTOR_WEIGHTS["equipment_health"], "No registered equipment for this farm.", has_data=False)
    return ScoreFactor(
        "equipment_health", widget.average_score, FACTOR_WEIGHTS["equipment_health"],
        f"Average equipment health score {widget.average_score:.0f}/100 across {widget.total} asset(s) "
        f"({widget.by_band.get('critical', 0)} critical, {widget.by_band.get('warning', 0)} warning).",
    )


def _disease_risk_factor(db: Session, tenant_id: str, farm_id: str) -> ScoreFactor:
    incidents = (
        db.query(crophealth_models.DiseaseIncident)
        .filter(
            crophealth_models.DiseaseIncident.farm_id == farm_id,
            crophealth_models.DiseaseIncident.status.notin_(("resolved", "false_positive")),
        )
        .all()
    )
    if not incidents:
        return ScoreFactor("disease_risk", 100.0, FACTOR_WEIGHTS["disease_risk"], "No open disease incidents.", has_data=False)
    scores = [i.risk_score for i in incidents if i.risk_score is not None]
    highest = max(scores) if scores else 50.0  # unscored open incident - assume moderate risk rather than zero risk
    return ScoreFactor(
        "disease_risk", max(0.0, 100.0 - highest), FACTOR_WEIGHTS["disease_risk"],
        f"{len(incidents)} open disease incident(s), highest risk score {highest:.0f}/100.",
    )


def _weather_factor(db: Session, farm_id: str) -> ScoreFactor:
    readings = {metric: current_reading(db, farm_id=farm_id, metric=metric) for metric in _WEATHER_RISK_RANGES}
    present = {metric: r for metric, r in readings.items() if r is not None}
    if not present:
        return ScoreFactor("weather", 100.0, FACTOR_WEIGHTS["weather"], "No recent weather readings.", has_data=False)

    deductions = []
    for metric, reading in present.items():
        ranges = _WEATHER_RISK_RANGES[metric]
        anomaly_low, anomaly_high = ranges["anomaly"]
        warning_low, warning_high = ranges["warning"]
        if anomaly_low <= reading.value <= anomaly_high:
            deductions.append((metric, reading.value, 40))
        elif warning_low <= reading.value <= warning_high:
            deductions.append((metric, reading.value, 20))

    score = max(0.0, 100.0 - sum(d for _, _, d in deductions))
    if not deductions:
        explanation = f"Weather within normal range ({', '.join(f'{m}={r.value:.0f}' for m, r in present.items())})."
    else:
        explanation = "; ".join(f"{m}={v:.0f} is outside the normal range (-{d})" for m, v, d in deductions)
    return ScoreFactor("weather", score, FACTOR_WEIGHTS["weather"], explanation)


def _sensor_connectivity_factor(db: Session, tenant_id: str, farm_id: str) -> ScoreFactor:
    devices = db.query(iot_models.IotDevice).filter(
        iot_models.IotDevice.tenant_id == tenant_id, iot_models.IotDevice.farm_id == farm_id, iot_models.IotDevice.is_active.is_(True)
    ).all()
    if not devices:
        return ScoreFactor("sensor_connectivity", 100.0, FACTOR_WEIGHTS["sensor_connectivity"], "No active sensors registered for this farm.", has_data=False)
    online = sum(1 for d in devices if d.is_online)
    pct = round(online / len(devices) * 100, 1)
    return ScoreFactor(
        "sensor_connectivity", pct, FACTOR_WEIGHTS["sensor_connectivity"],
        f"{online}/{len(devices)} active sensor(s) online.",
    )


def compute_farm_score(db: Session, *, tenant_id: str, farm_id: str) -> FarmScoreResult:
    factors = [
        _equipment_health_factor(db, tenant_id, farm_id),
        _disease_risk_factor(db, tenant_id, farm_id),
        _weather_factor(db, farm_id),
        _sensor_connectivity_factor(db, tenant_id, farm_id),
    ]
    weighted_total = sum(f.score * f.weight for f in factors)
    score = round(weighted_total)
    factors.sort(key=lambda f: f.score)  # worst-first, so the explanation leads with what's actually dragging the score down
    return FarmScoreResult(score=score, band=_band_for(score), factors=factors)
