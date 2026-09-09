"""Weather & External Data (Phase 8, FR-WX) - see docs/03-BRD.md §19.

`WeatherReading` is append-only and source-tagged (`station` vs `forecast`)
rather than a single mutable cell - this structurally satisfies FR-WX-001
("never overwrite an observed reading with forecast data"): there is
nothing to overwrite, both are kept, and `app.weather.provider` prefers
`station` over `forecast` when both exist for the same metric.
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..foundation.models import TenantScopedMixin, gen_uuid

WEATHER_SOURCES = ("station", "forecast")


def _uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)


class WeatherReading(TenantScopedMixin, Base):
    __tablename__ = "weather_readings"

    id: Mapped[str] = _uuid_pk()
    farm_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), index=True)
    metric: Mapped[str] = mapped_column(String(50), index=True)
    value: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(20), index=True)
    # For a `station` reading this is when it was measured; for a `forecast`
    # reading it's the time being forecast (which may be in the future).
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
