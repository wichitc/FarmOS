"""Farm & Crop Domain (Phase 4, FR-FARM) - see docs/07-DOMAIN-MODEL.md §3.3.

Spatial/organizational hierarchy Farm -> Zone -> Plot -> Block -> Row -> Tree
(FR-FARM-001). `Crop`/`Variety` already exist as Phase-3 master data
(`app.foundation.models`) - this module owns the entities that reference them.

Twin ID (FR-FARM-002): only `Tree` is a twin-capable object here (Farm/Zone/
Plot/Block/Row are organizational containers, not twins - see the ERD in
docs/08-DATA-ARCHITECTURE.md §5). `Tree.id` is the immutable Twin ID surrogate
for now; `Tree.code` is the mutable, human-facing code. Phase 6 formally
reconciles this with a `digital_twin_id` FK onto the generic `DigitalTwin`
core table (docs/08-DATA-ARCHITECTURE.md §6) - deliberately not built here.
"""
from datetime import date, datetime
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ..foundation.models import TenantScopedMixin, gen_uuid


def _uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)

TREE_GROWTH_STAGES = (
    "seedling",
    "vegetative",
    "flowering",
    "fruit_set",
    "fruit_growth",
    "maturity",
    "harvested",
    "dormant",
)


class Farm(TenantScopedMixin, Base):
    __tablename__ = "farms"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_farms_tenant_code"),)

    id: Mapped[str] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(255))
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    area_hectares: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    boundary = mapped_column(Geometry(geometry_type="POLYGON", srid=4326), nullable=True)

    zones: Mapped[list["Zone"]] = relationship(back_populates="farm", cascade="all, delete-orphan")
    seasons: Mapped[list["Season"]] = relationship(back_populates="farm", cascade="all, delete-orphan")


class Zone(TenantScopedMixin, Base):
    __tablename__ = "zones"
    __table_args__ = (UniqueConstraint("farm_id", "code", name="uq_zones_farm_code"),)

    id: Mapped[str] = _uuid_pk()
    farm_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(255))
    boundary = mapped_column(Geometry(geometry_type="POLYGON", srid=4326), nullable=True)

    farm: Mapped["Farm"] = relationship(back_populates="zones")
    plots: Mapped[list["Plot"]] = relationship(back_populates="zone", cascade="all, delete-orphan")


class Plot(TenantScopedMixin, Base):
    __tablename__ = "plots"
    __table_args__ = (UniqueConstraint("zone_id", "code", name="uq_plots_zone_code"),)

    id: Mapped[str] = _uuid_pk()
    zone_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("zones.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(255))
    area_hectares: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    boundary = mapped_column(Geometry(geometry_type="POLYGON", srid=4326), nullable=True)

    zone: Mapped["Zone"] = relationship(back_populates="plots")
    blocks: Mapped[list["Block"]] = relationship(back_populates="plot", cascade="all, delete-orphan")


class Block(TenantScopedMixin, Base):
    __tablename__ = "blocks"
    __table_args__ = (UniqueConstraint("plot_id", "code", name="uq_blocks_plot_code"),)

    id: Mapped[str] = _uuid_pk()
    plot_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("plots.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(255))
    area_hectares: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    boundary = mapped_column(Geometry(geometry_type="POLYGON", srid=4326), nullable=True)

    plot: Mapped["Plot"] = relationship(back_populates="blocks")
    rows_: Mapped[list["Row"]] = relationship(back_populates="block", cascade="all, delete-orphan")


class Row(TenantScopedMixin, Base):
    __tablename__ = "rows"
    __table_args__ = (UniqueConstraint("block_id", "code", name="uq_rows_block_code"),)

    id: Mapped[str] = _uuid_pk()
    block_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("blocks.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(255))
    spacing_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    centerline = mapped_column(Geometry(geometry_type="LINESTRING", srid=4326), nullable=True)

    block: Mapped["Block"] = relationship(back_populates="rows_")
    trees: Mapped[list["Tree"]] = relationship(back_populates="row", cascade="all, delete-orphan")


class Tree(TenantScopedMixin, Base):
    """FR-FARM-005. Soft-delete (`deleted_at`) per docs/08-DATA-ARCHITECTURE.md
    §4 - "Tree" is named there as an entity where recoverability matters."""

    __tablename__ = "trees"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_trees_tenant_code"),)

    id: Mapped[str] = _uuid_pk()
    row_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("rows.id", ondelete="CASCADE"), index=True)
    crop_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("crops.id"), index=True)
    variety_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("varieties.id"), nullable=True)
    digital_twin_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("digital_twins.id"), nullable=True
    )
    code: Mapped[str] = mapped_column(String(100))
    planting_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    rootstock: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    height_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    canopy_diameter_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    trunk_diameter_cm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    growth_stage: Mapped[str] = mapped_column(String(20), default="seedling")
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    row: Mapped["Row"] = relationship(back_populates="trees")
    events: Mapped[list["TreeEvent"]] = relationship(back_populates="tree", cascade="all, delete-orphan")


class Season(TenantScopedMixin, Base):
    __tablename__ = "seasons"
    __table_args__ = (UniqueConstraint("farm_id", "name", name="uq_seasons_farm_name"),)

    id: Mapped[str] = _uuid_pk()
    farm_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    farm: Mapped["Farm"] = relationship(back_populates="seasons")


class TreeEvent(Base):
    """Append-only linkage point for FR-FARM-007 ("linked history of health,
    irrigation, fertilization, treatment, harvest, cost, and revenue events").
    Dedicated tables for each of those land with their own phases (8-14);
    until then this is where that history is recorded, same append-only shape
    as `AuditEntry`/`WorkflowStepEvent` (no updated_at, no update/delete route).
    """

    __tablename__ = "tree_events"

    id: Mapped[str] = _uuid_pk()
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    tree_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("trees.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tree: Mapped["Tree"] = relationship(back_populates="events")
