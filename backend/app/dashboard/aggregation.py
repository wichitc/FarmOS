"""Command Center aggregation (Phase 16, FR-DASH). Pure read-only queries
over data every prior phase already built and persisted - nothing here
computes or estimates anything new; it assembles what other modules'
routers already expose one call at a time into the widget-shaped rollups
FR-DASH-001/003 ask a dashboard to present. No new tables (see
`docs/05-RTM.md` Phase 16 checklist).
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..accounting.profitability import compute_profitability
from ..ai import models as ai_models
from ..asset import models as asset_models
from ..crophealth import models as crophealth_models
from ..harvest import models as harvest_models
from ..inventory import models as inventory_models
from ..irrigation import models as irrigation_models
from ..twins import models as twin_models
from ..weather.provider import current_reading
from . import schemas as dash_schemas


def equipment_health_widget(db: Session, tenant_id: str, *, farm_id: Optional[str] = None) -> dash_schemas.EquipmentHealthWidget:
    asset_type_ids = [t.id for t in db.query(twin_models.TwinType).filter(twin_models.TwinType.category == "asset").all()]
    twins: list[twin_models.DigitalTwin] = []
    if asset_type_ids:
        query = db.query(twin_models.DigitalTwin).filter(
            twin_models.DigitalTwin.twin_type_id.in_(asset_type_ids),
            twin_models.DigitalTwin.deleted_at.is_(None),
        )
        if farm_id:
            query = query.filter(twin_models.DigitalTwin.farm_id == farm_id)
        twins = query.all()

    items: list[dash_schemas.EquipmentHealthItem] = []
    by_band = {"good": 0, "warning": 0, "critical": 0, "unassessed": 0}
    total_score = 0
    scored_count = 0

    for twin in twins:
        latest = (
            db.query(asset_models.HealthAssessment)
            .filter(asset_models.HealthAssessment.twin_id == twin.id)
            .order_by(asset_models.HealthAssessment.computed_at.desc())
            .first()
        )
        if latest:
            by_band[latest.band] = by_band.get(latest.band, 0) + 1
            total_score += latest.score
            scored_count += 1
            items.append(
                dash_schemas.EquipmentHealthItem(
                    twin_id=twin.id, display_code=twin.display_code, farm_id=twin.farm_id,
                    score=latest.score, band=latest.band, assessed_at=latest.computed_at,
                )
            )
        else:
            by_band["unassessed"] += 1
            items.append(
                dash_schemas.EquipmentHealthItem(twin_id=twin.id, display_code=twin.display_code, farm_id=twin.farm_id)
            )

    items.sort(key=lambda i: (i.score is None, i.score if i.score is not None else 0))
    average_score = round(total_score / scored_count, 1) if scored_count else 0.0

    return dash_schemas.EquipmentHealthWidget(total=len(items), average_score=average_score, by_band=by_band, equipment=items)


def inventory_widget(db: Session, tenant_id: str) -> dash_schemas.InventoryWidget:
    rows = (
        db.query(inventory_models.StockLot, inventory_models.Item)
        .join(inventory_models.Item, inventory_models.Item.id == inventory_models.StockLot.item_id)
        .filter(inventory_models.Item.min_qty.isnot(None))
        .all()
    )
    totals: dict[str, float] = {}
    items_by_id: dict[str, inventory_models.Item] = {}
    for lot, item in rows:
        totals[item.id] = totals.get(item.id, 0.0) + lot.quantity
        items_by_id[item.id] = item

    low = [
        dash_schemas.LowStockItem(item_id=item.id, code=item.code, name=item.name, on_hand=totals[item.id], min_qty=item.min_qty)
        for item in items_by_id.values()
        if totals[item.id] < item.min_qty
    ]
    low.sort(key=lambda i: i.on_hand - i.min_qty)
    return dash_schemas.InventoryWidget(low_stock_count=len(low), items=low[:5])


def agent_recommendations(db: Session, tenant_id: str, *, farm_id: Optional[str] = None, limit: int = 5) -> list[dash_schemas.AIRecommendationItem]:
    query = db.query(ai_models.AgentAction).filter(ai_models.AgentAction.status == "proposed")
    if farm_id:
        query = query.filter(ai_models.AgentAction.farm_id == farm_id)
    actions = query.order_by(ai_models.AgentAction.created_at.desc()).limit(limit).all()
    return [
        dash_schemas.AIRecommendationItem(
            agent_action_id=a.id, agent_code=a.agent_code, action_type=a.action_type,
            level=a.level, rationale=a.rationale, created_at=a.created_at,
        )
        for a in actions
    ]


def fleet_summary(db: Session, tenant_id: str) -> dash_schemas.FleetSummary:
    return dash_schemas.FleetSummary(
        generated_at=datetime.now(timezone.utc),
        equipment_health=equipment_health_widget(db, tenant_id),
        inventory=inventory_widget(db, tenant_id),
        ai_recommendations=agent_recommendations(db, tenant_id),
    )


def _weather_widget(db: Session, farm_id: str) -> dash_schemas.WeatherWidget:
    def _value(metric: str) -> Optional[float]:
        reading = current_reading(db, farm_id=farm_id, metric=metric)
        return reading.value if reading else None

    return dash_schemas.WeatherWidget(
        temperature_c=_value("temperature_c"),
        humidity_pct=_value("humidity_pct"),
        rainfall_mm=_value("rainfall_mm"),
        soil_moisture_pct=_value("soil_moisture_pct"),
    )


def _disease_risk_widget(db: Session, farm_id: str) -> dash_schemas.DiseaseRiskWidget:
    incidents = (
        db.query(crophealth_models.DiseaseIncident)
        .filter(
            crophealth_models.DiseaseIncident.farm_id == farm_id,
            crophealth_models.DiseaseIncident.status.notin_(("resolved", "false_positive")),
        )
        .all()
    )
    scores = [i.risk_score for i in incidents if i.risk_score is not None]
    return dash_schemas.DiseaseRiskWidget(
        open_incident_count=len(incidents), highest_risk_score=max(scores) if scores else None
    )


def _irrigation_status_widget(db: Session, farm_id: str) -> dash_schemas.IrrigationStatusWidget:
    since = datetime.now(timezone.utc) - timedelta(days=7)
    pending = db.query(irrigation_models.IrrigationPlan).filter(
        irrigation_models.IrrigationPlan.farm_id == farm_id, irrigation_models.IrrigationPlan.status == "pending_approval"
    ).count()
    approved = db.query(irrigation_models.IrrigationPlan).filter(
        irrigation_models.IrrigationPlan.farm_id == farm_id, irrigation_models.IrrigationPlan.status == "approved"
    ).count()
    completed_recent = db.query(irrigation_models.IrrigationEvent).filter(
        irrigation_models.IrrigationEvent.farm_id == farm_id, irrigation_models.IrrigationEvent.started_at >= since
    ).count()
    return dash_schemas.IrrigationStatusWidget(
        pending_approval_count=pending, approved_count=approved, completed_last_7_days=completed_recent
    )


def _yield_forecast_widget(db: Session, farm_id: str) -> Optional[dash_schemas.YieldForecastWidget]:
    latest = (
        db.query(harvest_models.YieldForecast)
        .filter(harvest_models.YieldForecast.farm_id == farm_id)
        .order_by(harvest_models.YieldForecast.forecast_date.desc())
        .first()
    )
    if latest is None:
        return None
    return dash_schemas.YieldForecastWidget(
        estimated_yield_kg_low=latest.estimated_yield_kg_low,
        estimated_yield_kg_high=latest.estimated_yield_kg_high,
        confidence=latest.confidence,
        forecast_date=latest.forecast_date,
    )


def _harvest_status_widget(db: Session, farm_id: str) -> dash_schemas.HarvestStatusWidget:
    since = datetime.now(timezone.utc) - timedelta(days=30)
    lots = (
        db.query(harvest_models.HarvestLot)
        .filter(harvest_models.HarvestLot.farm_id == farm_id, harvest_models.HarvestLot.harvested_at >= since)
        .all()
    )
    return dash_schemas.HarvestStatusWidget(
        lots_last_30_days=len(lots), total_kg_last_30_days=round(sum(lot.quantity_kg for lot in lots), 1)
    )


def _work_orders_widget(db: Session, farm_id: str) -> dash_schemas.WorkOrdersWidget:
    open_count = db.query(asset_models.WorkOrder).filter(
        asset_models.WorkOrder.farm_id == farm_id, asset_models.WorkOrder.status == "open"
    ).count()
    in_progress_count = db.query(asset_models.WorkOrder).filter(
        asset_models.WorkOrder.farm_id == farm_id, asset_models.WorkOrder.status == "in_progress"
    ).count()
    return dash_schemas.WorkOrdersWidget(open_count=open_count, in_progress_count=in_progress_count)


def _financial_kpi_widget(db: Session, farm_id: str) -> dash_schemas.FinancialKpiWidget:
    result = compute_profitability(db, dimensions={"farm_id": farm_id})
    return dash_schemas.FinancialKpiWidget(
        revenue=result.revenue, direct_costs=result.direct_costs, profit=result.profit, margin_pct=result.margin_pct
    )


def farm_summary(db: Session, tenant_id: str, farm_id: str) -> dash_schemas.FarmCommandCenterSummary:
    return dash_schemas.FarmCommandCenterSummary(
        generated_at=datetime.now(timezone.utc),
        farm_id=farm_id,
        equipment_health=equipment_health_widget(db, tenant_id, farm_id=farm_id),
        weather=_weather_widget(db, farm_id),
        disease_risk=_disease_risk_widget(db, farm_id),
        irrigation_status=_irrigation_status_widget(db, farm_id),
        yield_forecast=_yield_forecast_widget(db, farm_id),
        harvest_status=_harvest_status_widget(db, farm_id),
        work_orders=_work_orders_widget(db, farm_id),
        financial_kpis=_financial_kpi_widget(db, farm_id),
        ai_recommendations=agent_recommendations(db, tenant_id, farm_id=farm_id),
    )
