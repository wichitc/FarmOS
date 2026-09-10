from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from . import models as acct_models


def post_ledger_entry(
    db: Session,
    *,
    tenant_id: str,
    entry_type: str,
    direction: str,
    amount: float,
    dimensions: dict,
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    notes: Optional[str] = None,
    posted_by: Optional[str] = None,
) -> acct_models.LedgerEntry:
    """Shared by `routers/v1/accounting.py` (direct/manual postings) and
    `routers/v1/sales.py` (auto-posted revenue on invoice payment) so both
    paths write the exact same shape - the integration API FR-ACC-002
    calls for is this function's callers, not a separate code path."""
    entry = acct_models.LedgerEntry(
        tenant_id=tenant_id,
        entry_type=entry_type,
        direction=direction,
        amount=amount,
        dimensions=dimensions,
        source_type=source_type,
        source_id=source_id,
        posted_at=datetime.now(timezone.utc),
        notes=notes,
        posted_by=posted_by,
        created_by=posted_by,
        updated_by=posted_by,
    )
    db.add(entry)
    db.flush()
    return entry
