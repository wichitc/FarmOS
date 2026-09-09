"""External weather provider integration point (FR-WX-001).

No vendor/API key has been chosen yet, so there is nothing real to wire up -
this mirrors `app.foundation.notifications`'s `NotificationSender` stub
pattern from Phase 3: a `Protocol` real providers implement later, and a
stub that's honest about doing nothing rather than faking data.
"""
from typing import Protocol

from sqlalchemy.orm import Session

from . import models as weather_models


class WeatherProvider(Protocol):
    def fetch_forecast(self, *, farm_id: str, lat: float, lng: float) -> list[dict]:
        """Returns a list of {"metric": str, "value": float, "forecast_for": datetime} dicts."""
        ...


class StubWeatherProvider:
    """No real forecast source configured - returns nothing rather than
    fabricating data. Swap in a real implementation once a provider/API key
    is chosen; callers only depend on the `WeatherProvider` shape above."""

    def fetch_forecast(self, *, farm_id: str, lat: float, lng: float) -> list[dict]:
        return []


default_provider: WeatherProvider = StubWeatherProvider()


def current_reading(db: Session, *, farm_id: str, metric: str) -> weather_models.WeatherReading | None:
    """Best-available reading for a farm+metric (FR-WX-001): a `station`
    reading is preferred over a `forecast` one whenever both exist, since an
    observation always outranks a prediction of the same thing."""
    station = (
        db.query(weather_models.WeatherReading)
        .filter(
            weather_models.WeatherReading.farm_id == farm_id,
            weather_models.WeatherReading.metric == metric,
            weather_models.WeatherReading.source == "station",
        )
        .order_by(weather_models.WeatherReading.observed_at.desc())
        .first()
    )
    if station is not None:
        return station
    return (
        db.query(weather_models.WeatherReading)
        .filter(
            weather_models.WeatherReading.farm_id == farm_id,
            weather_models.WeatherReading.metric == metric,
            weather_models.WeatherReading.source == "forecast",
        )
        .order_by(weather_models.WeatherReading.observed_at.asc())
        .first()
    )
