"""Rule-based disease-risk engine (FR-HEALTH-002/004). Same "indicative
defaults, not a certified model" treatment as `app.health.compute_health`
and `app.irrigation.recommendation` - real epidemiological modeling is
Phase 15 (AI Platform) work behind this same contract. A pure function (no
DB) so it's testable without a database; the caller (the API endpoint)
gathers the inputs from weather readings, recent Vision AI detections, and
incident history.

FR-HEALTH-004 ("every disease/risk recommendation shall display confidence
and supporting evidence") is why this always returns an `evidence` list of
plain strings alongside the score - never a bare number.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DiseaseRiskResult:
    risk_score: float
    band: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# Placeholder weights - loosely modeled on the fact that most fungal/
# bacterial orchard pathogens favor high humidity + sustained leaf wetness,
# not a calibrated epidemiological model.
HUMIDITY_RISK_THRESHOLD_PCT = 85.0
LEAF_WETNESS_RISK_THRESHOLD_HOURS = 6.0
RAINFALL_RISK_THRESHOLD_MM = 20.0


def compute_disease_risk(
    *,
    humidity_pct: Optional[float] = None,
    rainfall_mm_7d: Optional[float] = None,
    leaf_wetness_hours: Optional[float] = None,
    recent_confirmed_incident_count: int = 0,
    recent_vision_detection_confidence: Optional[float] = None,
) -> DiseaseRiskResult:
    score = 0.0
    evidence: list[str] = []

    if humidity_pct is not None:
        evidence.append(f"Humidity {humidity_pct:.0f}%")
        if humidity_pct >= HUMIDITY_RISK_THRESHOLD_PCT:
            score += 25
            evidence.append(f"Humidity at/above the {HUMIDITY_RISK_THRESHOLD_PCT:.0f}% risk threshold (+25)")

    if leaf_wetness_hours is not None:
        evidence.append(f"Leaf wetness {leaf_wetness_hours:.1f}h")
        if leaf_wetness_hours >= LEAF_WETNESS_RISK_THRESHOLD_HOURS:
            score += 25
            evidence.append(f"Leaf wetness at/above {LEAF_WETNESS_RISK_THRESHOLD_HOURS:.0f}h risk threshold (+25)")

    if rainfall_mm_7d is not None:
        evidence.append(f"7-day rainfall {rainfall_mm_7d:.1f}mm")
        if rainfall_mm_7d >= RAINFALL_RISK_THRESHOLD_MM:
            score += 15
            evidence.append(f"7-day rainfall at/above {RAINFALL_RISK_THRESHOLD_MM:.0f}mm risk threshold (+15)")

    if recent_confirmed_incident_count > 0:
        bump = min(recent_confirmed_incident_count * 10, 25)
        score += bump
        evidence.append(f"{recent_confirmed_incident_count} confirmed incident(s) nearby in the recent history (+{bump})")

    if recent_vision_detection_confidence is not None:
        bump = recent_vision_detection_confidence * 20
        score += bump
        evidence.append(f"Vision AI detection confidence {recent_vision_detection_confidence:.0%} (+{bump:.1f})")

    score = max(0.0, min(100.0, round(score, 1)))
    signal_count = sum(
        x is not None
        for x in (humidity_pct, rainfall_mm_7d, leaf_wetness_hours, recent_vision_detection_confidence)
    ) + (1 if recent_confirmed_incident_count else 0)
    # Confidence in the *signal*, not the diagnosis - more independent
    # inputs feeding the score raises it, capped well short of 1.0 since
    # this is a placeholder rule set, not a validated model.
    confidence = min(0.5 + signal_count * 0.1, 0.9) if signal_count else 0.2

    if score >= 75:
        band = "critical"
        recommendations = ["Schedule an in-field inspection immediately; conditions strongly favor disease development"]
    elif score >= 50:
        band = "high"
        recommendations = ["Schedule an in-field inspection within the next few days"]
    elif score >= 25:
        band = "medium"
        recommendations = ["Monitor conditions; no inspection required yet"]
    else:
        band = "low"
        recommendations = ["No elevated risk signal at this time"]

    if not evidence:
        evidence.append("No input signals available - score defaults to 0")

    return DiseaseRiskResult(risk_score=score, band=band, confidence=round(confidence, 2), evidence=evidence, recommendations=recommendations)
