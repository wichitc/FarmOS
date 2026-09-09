from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class WeatherReadingCreate(BaseModel):
    farm_id: str
    metric: str
    value: float
    source: str
    observed_at: Optional[datetime] = None


class WeatherReadingOut(BaseModel):
    id: str
    farm_id: str
    metric: str
    value: float
    source: str
    observed_at: datetime
    recorded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CurrentWeatherOut(BaseModel):
    metric: str
    value: float
    source: str
    observed_at: datetime
