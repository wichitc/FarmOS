"""GIS & Spatial (Phase 5, FR-GIS) - see docs/03-BRD.md §3, docs/04-SRS.md §2.

`MapFeature` is the infrastructure layer FR-GIS-001 calls for (roads,
drains, ponds, pipes, pumps, valves, CCTV, sensors, buildings) as generic
point/line/polygon map layers. This is a placeholder ahead of the generic
`DigitalTwin`/`TwinType` graph Phase 6 introduces - same "shape now,
formalize later" pattern as `TreeEvent` (Phase 4) and `health.py`'s rule
engine. Farm/Zone/Plot/Block/Row/Tree boundary geometry columns live on
their existing Phase-4 tables (`app.farm.models`), added via migration
0005 rather than here, since they're properties of entities that already
exist.
"""
from geoalchemy2 import Geometry
from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..foundation.models import TenantScopedMixin, gen_uuid


def _uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)

MAP_FEATURE_TYPES = (
    "road",
    "drain",
    "pond",
    "pipe",
    "pump",
    "valve",
    "cctv",
    "sensor",
    "building",
    "other",
)


class MapFeature(TenantScopedMixin, Base):
    __tablename__ = "map_features"

    id: Mapped[str] = _uuid_pk()
    farm_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id", ondelete="CASCADE"), index=True)
    feature_type: Mapped[str] = mapped_column(String(30), index=True)
    name: Mapped[str] = mapped_column(String(255))
    geom = mapped_column(Geometry(geometry_type="GEOMETRY", srid=4326), nullable=False)
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)
