"""ML Service (master prompt §30) - the `/api/v1/ml/*` route surface the
master prompt names explicitly (`POST /api/v1/ml/{yield,irrigation,
disease,farm-score}/predict`). Every one of these is a thin wrapper over
an engine that already exists and is already exercised by a real business
endpoint elsewhere (`routers/v1/harvest.py`'s yield forecasts,
`routers/v1/irrigation.py`'s plans, `routers/v1/crophealth.py`'s risk
endpoint, `routers/v1/ai.py`'s farm score) - this router adds no new
computation, just the master prompt's own stateless "just predict, don't
save anything" naming convention on top of it, for a caller that wants a
number without creating a business record.

`crop-health/predict`, `pest/predict`, and `anomaly/predict` (also listed
in §30) are deliberately NOT routed here: there is no dedicated pest-risk
or anomaly-detection engine anywhere in this platform to wrap (disease
risk already covers the "crop health" ground `compute_disease_risk`
handles), and stubbing a route with no real engine behind it would be
exactly the kind of fabricated capability this platform's placeholder
engines elsewhere (health.py, irrigation.recommendation, ...) are
written not to be - see docs/05-RTM.md's Phase 27 checklist.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...ai import farm_score as ai_farm_score
from ...ai.service import record_prediction
from ...core.deps import assert_farm_scope, require_permission
from ...crophealth.risk import compute_disease_risk
from ...database import get_db
from ...farm import models as farm_models
from ...foundation import models as fm
from ...foundation.models import gen_uuid
from ...harvest.estimation import estimate_yield_range
from ...irrigation.recommendation import recommend_irrigation

router = APIRouter(prefix="/api/v1/ml", tags=["ml"])


class YieldPredictRequest(BaseModel):
    tree_count: int
    avg_fruit_count_per_tree: float
    avg_fruit_weight_kg: float
    variability_pct: Optional[float] = None


class YieldPredictResponse(BaseModel):
    estimated_yield_kg_low: float
    estimated_yield_kg_high: float
    confidence: float
    evidence: list[str]


@router.post("/yield/predict", response_model=YieldPredictResponse)
def predict_yield(
    payload: YieldPredictRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("harvest.yield.view")),
):
    kwargs = {"tree_count": payload.tree_count, "avg_fruit_count_per_tree": payload.avg_fruit_count_per_tree, "avg_fruit_weight_kg": payload.avg_fruit_weight_kg}
    if payload.variability_pct is not None:
        kwargs["variability_pct"] = payload.variability_pct
    result = estimate_yield_range(**kwargs)
    record_prediction(
        db, tenant_id=current_user.tenant_id, model_code="yield_estimation_rule_engine",
        entity_type="ml_yield_query", entity_id=gen_uuid(), input_ref=payload.model_dump(),
        output={"estimated_yield_kg_low": result.estimated_yield_kg_low, "estimated_yield_kg_high": result.estimated_yield_kg_high},
        confidence=result.confidence, created_by=current_user.id,
    )
    db.commit()
    return YieldPredictResponse(
        estimated_yield_kg_low=result.estimated_yield_kg_low, estimated_yield_kg_high=result.estimated_yield_kg_high,
        confidence=result.confidence, evidence=result.evidence,
    )


class DiseasePredictRequest(BaseModel):
    humidity_pct: Optional[float] = None
    rainfall_mm_7d: Optional[float] = None
    leaf_wetness_hours: Optional[float] = None
    recent_confirmed_incident_count: int = 0
    recent_vision_detection_confidence: Optional[float] = None


class DiseasePredictResponse(BaseModel):
    risk_score: float
    band: str
    confidence: float
    evidence: list[str]
    recommendations: list[str]


@router.post("/disease/predict", response_model=DiseasePredictResponse)
def predict_disease_risk(
    payload: DiseasePredictRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("crophealth.incident.view")),
):
    result = compute_disease_risk(**payload.model_dump())
    record_prediction(
        db, tenant_id=current_user.tenant_id, model_code="disease_risk_rule_engine",
        entity_type="ml_disease_query", entity_id=gen_uuid(), input_ref=payload.model_dump(),
        output={"risk_score": result.risk_score, "band": result.band}, confidence=result.confidence, created_by=current_user.id,
    )
    db.commit()
    return DiseasePredictResponse(
        risk_score=result.risk_score, band=result.band, confidence=result.confidence,
        evidence=result.evidence, recommendations=result.recommendations,
    )


class IrrigationPredictRequest(BaseModel):
    soil_moisture_pct: float
    target_moisture_pct: float
    forecast_rain_mm: float
    area_hectares: float


class IrrigationPredictResponse(BaseModel):
    should_irrigate: bool
    recommended_volume_liters: Optional[float] = None
    recommended_duration_minutes: Optional[float] = None
    reason: str


@router.post("/irrigation/predict", response_model=IrrigationPredictResponse)
def predict_irrigation(
    payload: IrrigationPredictRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("irrigation.plan.view")),
):
    result = recommend_irrigation(**payload.model_dump())
    record_prediction(
        db, tenant_id=current_user.tenant_id, model_code="irrigation_recommendation_rule_engine",
        entity_type="ml_irrigation_query", entity_id=gen_uuid(), input_ref=payload.model_dump(),
        output={"should_irrigate": result.should_irrigate, "recommended_volume_liters": result.recommended_volume_liters},
        confidence=None, created_by=current_user.id,
    )
    db.commit()
    return IrrigationPredictResponse(
        should_irrigate=result.should_irrigate, recommended_volume_liters=result.recommended_volume_liters,
        recommended_duration_minutes=result.recommended_duration_minutes, reason=result.reason,
    )


class FarmScorePredictRequest(BaseModel):
    farm_id: str


@router.post("/farm-score/predict")
def predict_farm_score(
    payload: FarmScorePredictRequest,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("dashboard.view")),
):
    if db.get(farm_models.Farm, payload.farm_id) is None:
        raise HTTPException(status_code=404, detail="Farm not found")
    assert_farm_scope(db, current_user, "dashboard.view", payload.farm_id)
    result = ai_farm_score.compute_farm_score(db, tenant_id=current_user.tenant_id, farm_id=payload.farm_id)
    record_prediction(
        db, tenant_id=current_user.tenant_id, model_code="farm_ai_score_rule_engine",
        entity_type="farm", entity_id=payload.farm_id,
        input_ref={"factors": [f.name for f in result.factors]},
        output={"score": result.score, "band": result.band}, confidence=None, created_by=current_user.id,
    )
    db.commit()
    return {
        "farm_id": payload.farm_id, "score": result.score, "band": result.band,
        "factors": [{"name": f.name, "score": f.score, "weight": f.weight, "explanation": f.explanation, "has_data": f.has_data} for f in result.factors],
    }
