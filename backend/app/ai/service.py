"""AI Model Registry helpers (ADR-008). `seed_baseline_catalog` registers
the rule-engine placeholders that already exist (health.py, crophealth
risk, harvest yield estimation) as `AIModel`/`ModelVersion` rows at
provisioning time, the same way `foundation.seed` auto-seeds roles and
mandatory approval workflows rather than leaving a tenant to configure
them. `record_prediction` is the one place every engine call site routes
through to satisfy AI-001 (model/version/confidence on every prediction).
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from . import models as ai_models

BASELINE_MODELS: list[tuple[str, str, str, str, str]] = [
    # code, name, task_type, version, implementation_ref
    ("health_score_rule_engine", "Equipment/Asset Health Score (rule-based)", "failure_prediction", "v1", "app.health.compute_health_score"),
    ("disease_risk_rule_engine", "Crop Disease Risk (rule-based)", "disease_risk", "v1", "app.crophealth.risk.compute_disease_risk"),
    ("yield_estimation_rule_engine", "Yield Range Estimation (rule-based)", "yield_forecast", "v1", "app.harvest.estimation.estimate_yield_range"),
    ("irrigation_recommendation_rule_engine", "Irrigation Recommendation (rule-based)", "irrigation_demand", "v1", "app.irrigation.recommendation.recommend_irrigation"),
]

# code, name, domain, description, allowed_action_types (master prompt
# §28's eleven named agents). "farm_manager" is the orchestrator at the
# root of that diagram - it proposes nothing directly itself yet (no
# cross-domain synthesis engine exists to drive it), so its allowed list
# is empty; it exists in the catalog as a documented placeholder for that
# future role rather than a callable agent today.
AGENT_CATALOG: list[tuple[str, str, str, str, list[str]]] = [
    ("farm_manager", "Farm Manager Agent", "orchestration", "Coordinates the domain agents below it; no direct actions yet.", []),
    ("crop", "Crop Agent", "crop", "Tracks crop/tree growth stage and health.", ["crop_health_assessment"]),
    ("weather", "Weather Agent", "weather", "Summarizes weather risk for irrigation/disease decisions.", ["weather_risk_alert"]),
    ("soil", "Soil Agent", "soil", "Assesses soil moisture/nutrient status.", ["soil_health_assessment"]),
    ("irrigation", "Irrigation Agent", "irrigation", "Recommends and, once approved, records irrigation execution.", ["irrigation_recommendation", "irrigation_valve_activation"]),
    ("fertilizer", "Fertilizer Agent", "fertilizer", "Recommends fertigation quantities.", ["fertigation_recommendation"]),
    ("disease", "Disease Agent", "disease", "Assesses disease risk and recommends treatment.", ["disease_risk_assessment", "treatment_recommendation"]),
    ("pest", "Pest Agent", "pest", "Assesses pest risk.", ["pest_risk_assessment"]),
    ("yield", "Yield Agent", "yield", "Forecasts yield ranges.", ["yield_forecast"]),
    ("finance", "Finance Agent", "finance", "Flags budget variance and posts routine financial entries.", ["financial_posting", "budget_alert"]),
    ("sustainability", "Sustainability Agent", "sustainability", "Reports on resource-use trends.", ["sustainability_report"]),
]


def seed_baseline_catalog(db: Session, tenant_id: str) -> None:
    for code, name, task_type, version, implementation_ref in BASELINE_MODELS:
        model = ai_models.AIModel(tenant_id=tenant_id, code=code, name=name, task_type=task_type)
        db.add(model)
        db.flush()
        db.add(
            ai_models.ModelVersion(
                tenant_id=tenant_id,
                model_id=model.id,
                version=version,
                status="active",
                implementation_ref=implementation_ref,
                released_at=datetime.now(timezone.utc),
            )
        )


def seed_agent_registry(db: Session, tenant_id: str) -> None:
    for code, name, domain, description, allowed_action_types in AGENT_CATALOG:
        db.add(
            ai_models.AgentDefinition(
                tenant_id=tenant_id, agent_code=code, name=name, domain=domain,
                description=description, allowed_action_types=allowed_action_types,
            )
        )


def get_agent_definition(db: Session, tenant_id: str, agent_code: str) -> Optional[ai_models.AgentDefinition]:
    return (
        db.query(ai_models.AgentDefinition)
        .filter(ai_models.AgentDefinition.tenant_id == tenant_id, ai_models.AgentDefinition.agent_code == agent_code)
        .first()
    )


def get_active_version(db: Session, tenant_id: str, model_code: str) -> Optional[ai_models.ModelVersion]:
    model = (
        db.query(ai_models.AIModel)
        .filter(ai_models.AIModel.tenant_id == tenant_id, ai_models.AIModel.code == model_code)
        .first()
    )
    if model is None:
        return None
    return (
        db.query(ai_models.ModelVersion)
        .filter(ai_models.ModelVersion.model_id == model.id, ai_models.ModelVersion.status == "active")
        .order_by(ai_models.ModelVersion.released_at.desc())
        .first()
    )


def record_prediction(
    db: Session,
    *,
    tenant_id: str,
    model_code: str,
    entity_type: str,
    entity_id: str,
    input_ref: dict,
    output: dict,
    confidence: Optional[float],
    created_by: Optional[str] = None,
) -> Optional[ai_models.Prediction]:
    """Best-effort: if the tenant's catalog wasn't seeded (pre-Phase-15
    tenant that hasn't been re-provisioned), silently skips rather than
    breaking the calling engine's own primary response - AI-001 recording
    is additive instrumentation, not a hard dependency of the underlying
    feature."""
    version = get_active_version(db, tenant_id, model_code)
    if version is None:
        return None
    prediction = ai_models.Prediction(
        tenant_id=tenant_id,
        model_version_id=version.id,
        entity_type=entity_type,
        entity_id=entity_id,
        input_ref=input_ref,
        output=output,
        confidence=confidence,
        predicted_at=datetime.now(timezone.utc),
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(prediction)
    db.flush()
    return prediction
