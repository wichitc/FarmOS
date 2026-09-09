from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...core.deps import assert_farm_scope, require_permission
from ...database import get_db
from ...farm import models as farm_models
from ...foundation import models as fm
from ...weather import models as weather_models
from ...weather import schemas as weather_schemas
from ...weather.provider import current_reading

router = APIRouter(prefix="/api/v1/weather", tags=["weather"])


def _get_or_404(db: Session, model, obj_id: str, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


@router.post("/readings", response_model=weather_schemas.WeatherReadingOut, status_code=201)
def ingest_reading(
    payload: weather_schemas.WeatherReadingCreate,
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
