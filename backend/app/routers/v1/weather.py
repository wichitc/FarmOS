from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ...ai import agent_gateway
from ...core.deps import assert_farm_scope, require_permission
from ...database import get_db
from ...farm import models as farm_models
from ...foundation import models as fm
from ...weather import models as weather_models
from ...weather import schemas as weather_schemas
from ...weather.provider import current_reading
from ...weather.risk import classify_weather_risk

router = APIRouter(prefix="/api/v1/weather", tags=["weather"])


def _get_or_404(db: Session, model, obj_id: str, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


def _correlation_id(request: Request) -> str:
    return request.headers.get("x-correlation-id", "")


@router.post("/readings", response_model=weather_schemas.WeatherReadingOut, status_code=201)
def ingest_reading(
    payload: weather_schemas.WeatherReadingCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("weather.ingest")),
):
    farm = _get_or_404(db, farm_models.Farm, payload.farm_id, "Farm")
    assert_farm_scope(db, current_user, "weather.ingest", farm.id)

    if payload.source not in weather_models.WEATHER_SOURCES:
        raise HTTPException(status_code=422, detail=f"Unknown source '{payload.source}'")

    reading = weather_models.WeatherReading(
        tenant_id=current_user.tenant_id,
        farm_id=farm.id,
        metric=payload.metric,
        value=payload.value,
        source=payload.source,
        observed_at=payload.observed_at or datetime.now(timezone.utc),
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(reading)
    db.flush()

    band = classify_weather_risk(payload.metric, payload.value)
    if band is not None:
        # Weather Agent's Observe->Analyze record (master-prompt
        # integration, Phase 32 - same shape as the Irrigation/
        # Fertilizer/Disease/Yield wirings). Keyed off the same
        # warning/anomaly bands `ai/farm_score.py`'s weather factor
        # already classifies against (now shared via `weather/risk.py`
        # rather than duplicated) - only a reading actually landing in
        # one of those bands generates an alert, not every reading. L1
        # ("advisory") since flagging risky weather isn't itself a risky
        # action; any resulting irrigation/treatment decision stays a
        # separate, unrelated plan a human or another agent creates.
        agent_action = agent_gateway.propose_action(
            db, tenant_id=current_user.tenant_id, actor=current_user,
            agent_code="weather", action_type="weather_risk_alert", requested_level="L1",
            entity_type="weather_reading", entity_id=reading.id, farm_id=farm.id,
            rationale=f"{payload.metric}={payload.value} is in the {band} range.",
            input_context={"metric": payload.metric, "value": payload.value, "band": band},
            correlation_id=_correlation_id(request),
        )
        agent_gateway.execute_action(
            db, action=agent_action, actor=current_user,
            result={"weather_reading_id": reading.id, "band": band},
            correlation_id=_correlation_id(request),
        )

    db.commit()
    return reading


@router.get("/readings", response_model=list[weather_schemas.WeatherReadingOut])
def list_readings(
    farm_id: str,
    metric: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    limit: int = Query(default=100, le=1000),
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("weather.view")),
):
    assert_farm_scope(db, user, "weather.view", farm_id)
    query = db.query(weather_models.WeatherReading).filter(weather_models.WeatherReading.farm_id == farm_id)
    if metric:
        query = query.filter(weather_models.WeatherReading.metric == metric)
    if source:
        query = query.filter(weather_models.WeatherReading.source == source)
    return query.order_by(weather_models.WeatherReading.observed_at.desc()).limit(limit).all()


@router.get("/current", response_model=weather_schemas.CurrentWeatherOut)
def get_current(
    farm_id: str,
    metric: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("weather.view")),
):
    assert_farm_scope(db, user, "weather.view", farm_id)
    reading = current_reading(db, farm_id=farm_id, metric=metric)
    if reading is None:
        raise HTTPException(status_code=404, detail=f"No reading for metric '{metric}' on this farm")
    return weather_schemas.CurrentWeatherOut(
        metric=reading.metric, value=reading.value, source=reading.source, observed_at=reading.observed_at
    )
