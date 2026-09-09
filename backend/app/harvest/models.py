"""Yield & Harvest (Phase 11, FR-YIELD / FR-HARV) - see docs/03-BRD.md §10.

FR-HARV-001's full `Harvest Plan -> Task -> Batch -> Lot -> Receipt ->
Grade -> Packing Lot` pipeline is simplified to the two entities that
actually carry the traceability chain FR-HARV-002 requires
(`HarvestLot`/`PackingLot`) - Plan/Task/Batch/Receipt are Farm Work
Management (`FR-WORK`) territory, which doesn't exist as a queryable
entity yet (same deferral as `TreatmentPlan.work_task_ref` in Phase 10);
`grade` lives directly on `HarvestLot` rather than a separate stage.

Fruit lifecycle stages are tracked as their own observation log
(`FruitObservation`), not by reusing `farm.models.Tree.growth_stage`
(Phase 4) - FR-YIELD-001's stage list (Flowering -> Pollination -> Fruit
Set -> Fruit Growth -> Maturity -> Harvest) includes "Pollination", which
`TREE_GROWTH_STAGES` doesn't, and modifying that Phase-4 enum would touch
already-shipped tree state.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..foundation.models import TenantScopedMixin, gen_uuid

FRUIT_STAGES = ("flowering", "pollination", "fruit_set", "fruit_growth", "maturity", "harvest")


def _uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)


class FruitObservation(TenantScopedMixin, Base):
    __tablename__ = "fruit_observations"

    id: Mapped[str] = _uuid_pk()
    tree_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("trees.id"), index=True)
    stage: Mapped[str] = mapped_column(String(20))
    estimated_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)


class YieldForecast(TenantScopedMixin, Base):
    """FR-YIELD-002: always a range, never a single point number -
    `estimated_yield_kg_low`/`_high`, not one field."""

    __tablename__ = "yield_forecasts"

    id: Mapped[str] = _uuid_pk()
    farm_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), index=True)
    plot_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("plots.id"), nullable=True)
    tree_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("trees.id"), nullable=True)
    season_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("seasons.id"), nullable=True)
    estimated_yield_kg_low: Mapped[float] = mapped_column(Float)
    estimated_yield_kg_high: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    basis: Mapped[dict] = mapped_column(JSONB, default=dict)
    forecast_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class HarvestLot(TenantScopedMixin, Base):
    __tablename__ = "harvest_lots"
    __table_args__ = (UniqueConstraint("tenant_id", "qr_code", name="uq_harvest_lots_tenant_qr"),)

    id: Mapped[str] = _uuid_pk()
    farm_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), index=True)
    plot_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("plots.id"), nullable=True)
    tree_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("trees.id"), nullable=True)
    season_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("seasons.id"), nullable=True)
    qr_code: Mapped[str] = mapped_column(String(64))
    harvested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    quantity_kg: Mapped[float] = mapped_column(Float)
    grade: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    harvested_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class PackingLot(TenantScopedMixin, Base):
    __tablename__ = "packing_lots"
    __table_args__ = (UniqueConstraint("tenant_id", "qr_code", name="uq_packing_lots_tenant_qr"),)

    id: Mapped[str] = _uuid_pk()
    farm_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("farms.id"), index=True)
    qr_code: Mapped[str] = mapped_column(String(64))
    packed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    packed_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class PackingLotItem(TenantScopedMixin, Base):
    """Many-to-many join: a Packing Lot typically aggregates multiple
    Harvest Lots (FR-HARV-002's traceability chain step)."""

    __tablename__ = "packing_lot_items"

    id: Mapped[str] = _uuid_pk()
    packing_lot_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("packing_lots.id", ondelete="CASCADE"), index=True)
    harvest_lot_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("harvest_lots.id"), index=True)
    quantity_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
