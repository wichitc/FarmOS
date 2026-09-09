"""Rule-based yield estimation (FR-YIELD-002). Same "indicative defaults,
not a certified model" treatment as `health.py`/`app.irrigation.recommendation`/
`app.crophealth.risk`. Always a range + confidence, per FR-YIELD-002's
explicit requirement that a yield prediction is never a single point
number. Pure function (no DB), testable without a database.
"""
from dataclasses import dataclass, field

# +/-20% around the point estimate by default - a placeholder spread, not a
# statistically fitted confidence interval.
DEFAULT_VARIABILITY_PCT = 20.0


@dataclass
class YieldEstimate:
    estimated_yield_kg_low: float
    estimated_yield_kg_high: float
    confidence: float
    evidence: list[str] = field(default_factory=list)


def estimate_yield_range(
    *,
    tree_count: int,
    avg_fruit_count_per_tree: float,
    avg_fruit_weight_kg: float,
    variability_pct: float = DEFAULT_VARIABILITY_PCT,
) -> YieldEstimate:
    if tree_count <= 0 or avg_fruit_count_per_tree <= 0 or avg_fruit_weight_kg <= 0:
        return YieldEstimate(
            estimated_yield_kg_low=0.0,
            estimated_yield_kg_high=0.0,
            confidence=0.0,
            evidence=["Insufficient input (tree count, fruit count, or fruit weight is zero/missing)"],
        )

    point_estimate = tree_count * avg_fruit_count_per_tree * avg_fruit_weight_kg
    spread = point_estimate * (variability_pct / 100)
    low = round(max(0.0, point_estimate - spread), 1)
    high = round(point_estimate + spread, 1)

    # More trees observed -> more confidence in the average holding up
    # across the population, capped well short of 1.0 (placeholder rule,
    # not a validated statistical model).
    confidence = round(min(0.4 + min(tree_count, 50) * 0.01, 0.85), 2)

    evidence = [
        f"{tree_count} tree(s) x {avg_fruit_count_per_tree:.1f} fruit/tree x {avg_fruit_weight_kg:.2f}kg/fruit = {point_estimate:.1f}kg point estimate",
        f"+/-{variability_pct:.0f}% placeholder variability band, not a fitted confidence interval",
    ]
    return YieldEstimate(
        estimated_yield_kg_low=low, estimated_yield_kg_high=high, confidence=confidence, evidence=evidence
    )
