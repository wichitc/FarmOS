"""Rule-based irrigation/fertigation recommendation engine (FR-IRR-002,
FR-FERT-001). Same treatment as `app.health.compute_health`: indicative
defaults, not a certified agronomic model - real ET-based/ML modeling is
Phase 15 (AI Platform) work that replaces these internals behind the same
return shape, not their callers. Pure functions (no DB) so they're testable
without a database, same as `compute_health`.

Per FR-FERT-003 ("every AI fertigation recommendation shall display its
reason, supporting data, confidence, and stated limitations - never a bare
number"), every recommendation carries a `reason` string and this module's
own docstring stands as the "stated limitation."
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IrrigationRecommendation:
    should_irrigate: bool
    recommended_volume_liters: Optional[float]
    recommended_duration_minutes: Optional[float]
    reason: str


@dataclass
class FertigationRecommendation:
    recommended_quantity_kg: float
    reason: str
    breakdown_kg: dict = field(default_factory=dict)


# Liters per hectare per 1% moisture deficit - a placeholder constant, not a
# soil-type/crop-calibrated figure. Tune per-crop once real agronomic data
# is available (Phase 15).
LITERS_PER_HECTARE_PER_PERCENT_DEFICIT = 150.0
LITERS_PER_MINUTE_ASSUMED_FLOW_RATE = 200.0
RAIN_SKIP_THRESHOLD_MM = 10.0


def recommend_irrigation(
    *,
    soil_moisture_pct: float,
    target_moisture_pct: float,
    forecast_rain_mm: float,
    area_hectares: float,
) -> IrrigationRecommendation:
    if forecast_rain_mm >= RAIN_SKIP_THRESHOLD_MM:
        return IrrigationRecommendation(
            should_irrigate=False,
            recommended_volume_liters=None,
            recommended_duration_minutes=None,
            reason=(
                f"Forecast rainfall ({forecast_rain_mm:.1f}mm) meets or exceeds the "
                f"{RAIN_SKIP_THRESHOLD_MM:.0f}mm skip threshold - irrigation deferred"
            ),
        )

    deficit_pct = target_moisture_pct - soil_moisture_pct
    if deficit_pct <= 0:
        return IrrigationRecommendation(
            should_irrigate=False,
            recommended_volume_liters=None,
            recommended_duration_minutes=None,
            reason=(
                f"Soil moisture ({soil_moisture_pct:.1f}%) already at or above target "
                f"({target_moisture_pct:.1f}%) - no irrigation needed"
            ),
        )

    volume = deficit_pct * area_hectares * LITERS_PER_HECTARE_PER_PERCENT_DEFICIT
    duration = volume / LITERS_PER_MINUTE_ASSUMED_FLOW_RATE
    return IrrigationRecommendation(
        should_irrigate=True,
        recommended_volume_liters=round(volume, 1),
        recommended_duration_minutes=round(duration, 1),
        reason=(
            f"Soil moisture ({soil_moisture_pct:.1f}%) is {deficit_pct:.1f} points below target "
            f"({target_moisture_pct:.1f}%) with no significant rain forecast "
            f"({forecast_rain_mm:.1f}mm) - indicative volume from a placeholder "
            f"{LITERS_PER_HECTARE_PER_PERCENT_DEFICIT:.0f} L/ha/% deficit rule, not a calibrated ET model"
        ),
    )


def recommend_fertigation(*, target_n_kg: float, fertilizer_composition: dict) -> FertigationRecommendation:
    """Quantity of a fertilizer product needed to deliver `target_n_kg` of
    nitrogen, given its N percentage in `fertilizer_composition` (e.g.
    `{"N": 15, "P": 15, "K": 15}` for a 15-15-15 blend). Only targets N -
    P/K/other nutrient balancing from a single product mix is a real
    formulation problem, out of scope for this placeholder."""
    n_pct = fertilizer_composition.get("N", 0)
    if n_pct <= 0:
        return FertigationRecommendation(
            recommended_quantity_kg=0.0,
            reason="Fertilizer has no nitrogen content on file - cannot compute quantity from an N target",
        )

    quantity_kg = target_n_kg / (n_pct / 100)
    breakdown = {
        nutrient: round(quantity_kg * (pct / 100), 3)
        for nutrient, pct in fertilizer_composition.items()
        if isinstance(pct, (int, float))
    }
    return FertigationRecommendation(
        recommended_quantity_kg=round(quantity_kg, 3),
        reason=(
            f"{quantity_kg:.2f}kg delivers the {target_n_kg:.2f}kg N target at "
            f"{n_pct:.1f}% N composition; does not balance P/K against separate targets"
        ),
        breakdown_kg=breakdown,
    )
