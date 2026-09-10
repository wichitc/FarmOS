"""Farm Accounting & Profitability (Phase 14, FR-ACC / FR-PROF) - see
docs/03-BRD.md §15.

FR-ACC-002 explicitly wants "an explicit integration API rather than a
duplicated General Ledger where a corporate ERP already owns the GL" - so
`LedgerEntry` is a flat, single-amount posting (a real amount + direction),
not double-entry debit/credit bookkeeping with a chart of accounts. This
whole REST API *is* the integration point an ERP would call or pull from.

FR-ACC-001's eleven accounting dimensions (Farm, Zone, Plot, Crop, Variety,
Tree, Season, Harvest Lot, Asset, Activity, Cost Center) are a `dimensions`
JSONB bag on each posting rather than eleven nullable FK columns - same
"generic reference over parallel columns" principle as
`StockMovement.reference_type`/`reference_id` (Phase 13) and
`Alert.entity_type`/`entity_id` (Phase 7), just wider since a single
posting can legitimately carry several dimensions at once (e.g. a harvest
sale is tagged with farm + plot + season + harvest lot together).
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..foundation.models import TenantScopedMixin, gen_uuid

ENTRY_TYPES = ("accrual", "payment", "receipt", "budget", "actual", "variance")
ENTRY_DIRECTIONS = ("revenue", "expense")


def _uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)


class CostCenter(TenantScopedMixin, Base):
    __tablename__ = "cost_centers"

    id: Mapped[str] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class LedgerEntry(TenantScopedMixin, Base):
    """Append-only (BR-004-style: no update/delete route exposed).
    `source_type`/`source_id` traces what generated the posting (e.g. a
    Sales `Invoice` payment, or a manual entry) - same generic-reference
    pattern as `dimensions`, one level up."""

    __tablename__ = "ledger_entries"

    id: Mapped[str] = _uuid_pk()
    entry_type: Mapped[str] = mapped_column(String(20))
    direction: Mapped[str] = mapped_column(String(10))
    amount: Mapped[float] = mapped_column(Float)
    dimensions: Mapped[dict] = mapped_column(JSONB, default=dict)
    source_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    posted_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)


class Budget(TenantScopedMixin, Base):
    """FR-ACC-002's budget side - `actual` is never stored here, it's
    computed on read by aggregating `LedgerEntry` rows whose `dimensions`
    matches (see `app.accounting.profitability`), so a budget can never
    silently drift out of sync with what was actually posted."""

    __tablename__ = "budgets"

    id: Mapped[str] = _uuid_pk()
    direction: Mapped[str] = mapped_column(String(10))
    amount: Mapped[float] = mapped_column(Float)
    dimensions: Mapped[dict] = mapped_column(JSONB, default=dict)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
