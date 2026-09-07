from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models as db_models
from ..health import compute_health
from ..schemas import DashboardSummary, DashboardEquipmentItem

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(db: Session = Depends(get_db)):
    equipment = (
        db.query(db_models.Equipment)
        .filter(~db_models.Equipment.type.like("tree_%"))
        .order_by(db_models.Equipment.name.asc())
        .all()
    )
    model_names = {m.id: m.name for m in db.query(db_models.ModelRecord).all()}

    items: list[DashboardEquipmentItem] = []
    by_band = {"good": 0, "warning": 0, "critical": 0}
    total_score = 0

    for eq in equipment:
        health = compute_health(eq)
        by_band[health.band] = by_band.get(health.band, 0) + 1
        total_score += health.score
        items.append(
            DashboardEquipmentItem(
                id=eq.id,
                type=eq.type,
                name=eq.name,
                model_id=eq.model_id,
                model_name=model_names.get(eq.model_id) if eq.model_id else None,
                score=health.score,
                band=health.band,
                summary=health.summary,
            )
        )

    average_score = round(total_score / len(equipment), 1) if equipment else 0.0

    return DashboardSummary(
        generated_at=datetime.now(timezone.utc),
        total=len(equipment),
        average_score=average_score,
        by_band=by_band,
        equipment=items,
    )
