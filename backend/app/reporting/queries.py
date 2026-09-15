"""Reporting API (RPT-001): every report here is a real aggregation over
data other phases already persist - none of this is placeholder/rule-
engine scoring, there is nothing to estimate. Mirrors the query style
`app.dashboard.aggregation` already established for Phase 16's Command
Center widgets; this module produces report *rows* (flat, CSV/PDF-
exportable) instead of dashboard widgets, with explicit date/season
range filtering per RPT-002.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..accounting import models as acct_models
from ..asset import models as asset_models
from ..crophealth import models as crophealth_models
from ..dashboard.aggregation import equipment_health_widget
from ..harvest import models as harvest_models
from ..inventory import models as inventory_models
from ..irrigation import models as irrigation_models
from ..work import models as work_models
from . import schemas as rpt_schemas


def _in_range(column, date_from: Optional[date], date_to: Optional[date]):
    clauses = []
    if date_from:
        clauses.append(column >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc))
    if date_to:
        clauses.append(column < datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc))
    return clauses


def farm_health_report(db: Session, *, tenant_id: str, farm_id: str, filters: rpt_schemas.ReportFilter) -> rpt_schemas.FarmHealthRow:
    incident_query = db.query(crophealth_models.DiseaseIncident).filter(
        crophealth_models.DiseaseIncident.farm_id == farm_id,
        crophealth_models.DiseaseIncident.status.notin_(("resolved", "false_positive")),
    )
    if filters.plot_id:
        incident_query = incident_query.filter(crophealth_models.DiseaseIncident.plot_id == filters.plot_id)
    for clause in _in_range(crophealth_models.DiseaseIncident.created_at, filters.date_from, filters.date_to):
        incident_query = incident_query.filter(clause)
    incidents = incident_query.all()
    scores = [i.risk_score for i in incidents if i.risk_score is not None]

    equipment = equipment_health_widget(db, tenant_id, farm_id=farm_id)

    return rpt_schemas.FarmHealthRow(
        farm_id=farm_id,
        open_disease_incidents=len(incidents),
        highest_disease_risk_score=max(scores) if scores else None,
        equipment_count=equipment.total,
        equipment_average_score=equipment.average_score if equipment.total else None,
        equipment_critical_count=equipment.by_band.get("critical", 0),
    )


def irrigation_fertigation_usage_report(
    db: Session, *, farm_id: str, filters: rpt_schemas.ReportFilter
) -> list[rpt_schemas.IrrigationFertigationUsageRow]:
    irr_query = db.query(
        irrigation_models.IrrigationEvent.plot_id,
        func.count(irrigation_models.IrrigationEvent.id),
        func.coalesce(func.sum(irrigation_models.IrrigationEvent.actual_volume_liters), 0.0),
    ).filter(irrigation_models.IrrigationEvent.farm_id == farm_id)
    if filters.plot_id:
        irr_query = irr_query.filter(irrigation_models.IrrigationEvent.plot_id == filters.plot_id)
    for clause in _in_range(irrigation_models.IrrigationEvent.started_at, filters.date_from, filters.date_to):
        irr_query = irr_query.filter(clause)
    irrigation_by_plot = {
        row[0]: {"events": row[1], "liters": row[2]} for row in irr_query.group_by(irrigation_models.IrrigationEvent.plot_id).all()
    }

    fert_query = db.query(
        irrigation_models.FertigationEvent.plot_id,
        func.count(irrigation_models.FertigationEvent.id),
        func.coalesce(func.sum(irrigation_models.FertigationEvent.actual_quantity_kg), 0.0),
    ).filter(irrigation_models.FertigationEvent.farm_id == farm_id)
    if filters.plot_id:
        fert_query = fert_query.filter(irrigation_models.FertigationEvent.plot_id == filters.plot_id)
    for clause in _in_range(irrigation_models.FertigationEvent.applied_at, filters.date_from, filters.date_to):
        fert_query = fert_query.filter(clause)
    fertigation_by_plot = {
        row[0]: {"events": row[1], "kg": row[2]} for row in fert_query.group_by(irrigation_models.FertigationEvent.plot_id).all()
    }

    plot_ids = set(irrigation_by_plot) | set(fertigation_by_plot)
    rows = []
    for plot_id in plot_ids:
        irr = irrigation_by_plot.get(plot_id, {"events": 0, "liters": 0.0})
        fert = fertigation_by_plot.get(plot_id, {"events": 0, "kg": 0.0})
        rows.append(
            rpt_schemas.IrrigationFertigationUsageRow(
                plot_id=plot_id,
                irrigation_events=irr["events"],
                total_irrigation_liters=irr["liters"],
                fertigation_events=fert["events"],
                total_fertigation_kg=fert["kg"],
            )
        )
    return rows


def work_completion_report(db: Session, *, farm_id: str, filters: rpt_schemas.ReportFilter) -> list[rpt_schemas.WorkCompletionRow]:
    query = db.query(work_models.WorkTask).filter(work_models.WorkTask.farm_id == farm_id)
    if filters.plot_id:
        query = query.filter(work_models.WorkTask.plot_id == filters.plot_id)
    for clause in _in_range(work_models.WorkTask.created_at, filters.date_from, filters.date_to):
        query = query.filter(clause)

    by_type: dict[str, dict[str, int]] = {}
    for task in query.all():
        bucket = by_type.setdefault(task.work_type, {"requested": 0, "closed": 0, "cancelled_or_rejected": 0})
        bucket["requested"] += 1
        if task.status == "closed":
            bucket["closed"] += 1
        elif task.status in ("cancelled", "rejected"):
            bucket["cancelled_or_rejected"] += 1

    return [
        rpt_schemas.WorkCompletionRow(
            work_type=work_type,
            requested=counts["requested"],
            closed=counts["closed"],
            cancelled_or_rejected=counts["cancelled_or_rejected"],
            completion_rate_pct=round(counts["closed"] / counts["requested"] * 100, 1) if counts["requested"] else 0.0,
        )
        for work_type, counts in sorted(by_type.items())
    ]


def disease_trend_report(db: Session, *, farm_id: str, filters: rpt_schemas.ReportFilter) -> list[rpt_schemas.DiseaseTrendRow]:
    """Trended by the ISO week an incident was *created* - a cohort view,
    not a point-in-time-accurate one: `DiseaseIncident` has no
    `confirmed_at`/`resolved_at` timestamp, only a current `status`, so
    "confirmed"/"resolved" counts here reflect each cohort's status *as of
    now*, not the week that transition actually happened."""
    query = db.query(crophealth_models.DiseaseIncident).filter(crophealth_models.DiseaseIncident.farm_id == farm_id)
    if filters.plot_id:
        query = query.filter(crophealth_models.DiseaseIncident.plot_id == filters.plot_id)
    for clause in _in_range(crophealth_models.DiseaseIncident.created_at, filters.date_from, filters.date_to):
        query = query.filter(clause)

    by_week: dict[str, dict[str, int]] = {}
    for incident in query.all():
        iso = incident.created_at.isocalendar()
        period = f"{iso[0]}-W{iso[1]:02d}"
        bucket = by_week.setdefault(period, {"new": 0, "confirmed": 0, "resolved": 0})
        bucket["new"] += 1
        if incident.status == "confirmed":
            bucket["confirmed"] += 1
        elif incident.status == "resolved":
            bucket["resolved"] += 1

    return [
        rpt_schemas.DiseaseTrendRow(period=period, new_incidents=c["new"], confirmed_incidents=c["confirmed"], resolved_incidents=c["resolved"])
        for period, c in sorted(by_week.items())
    ]


def yield_harvest_report(db: Session, *, farm_id: str, filters: rpt_schemas.ReportFilter) -> list[rpt_schemas.YieldHarvestRow]:
    forecast_query = db.query(harvest_models.YieldForecast).filter(harvest_models.YieldForecast.farm_id == farm_id)
    if filters.plot_id:
        forecast_query = forecast_query.filter(harvest_models.YieldForecast.plot_id == filters.plot_id)
    if filters.season_id:
        forecast_query = forecast_query.filter(harvest_models.YieldForecast.season_id == filters.season_id)
    for clause in _in_range(harvest_models.YieldForecast.forecast_date, filters.date_from, filters.date_to):
        forecast_query = forecast_query.filter(clause)

    forecasts_by_plot: dict[Optional[str], dict] = {}
    for f in forecast_query.all():
        bucket = forecasts_by_plot.setdefault(f.plot_id, {"count": 0, "low": 0.0, "high": 0.0})
        bucket["count"] += 1
        bucket["low"] += f.estimated_yield_kg_low
        bucket["high"] += f.estimated_yield_kg_high

    lot_query = db.query(harvest_models.HarvestLot).filter(harvest_models.HarvestLot.farm_id == farm_id)
    if filters.plot_id:
        lot_query = lot_query.filter(harvest_models.HarvestLot.plot_id == filters.plot_id)
    if filters.season_id:
        lot_query = lot_query.filter(harvest_models.HarvestLot.season_id == filters.season_id)
    for clause in _in_range(harvest_models.HarvestLot.harvested_at, filters.date_from, filters.date_to):
        lot_query = lot_query.filter(clause)

    actual_by_plot: dict[Optional[str], float] = {}
    for lot in lot_query.all():
        actual_by_plot[lot.plot_id] = actual_by_plot.get(lot.plot_id, 0.0) + lot.quantity_kg

    plot_ids = set(forecasts_by_plot) | set(actual_by_plot)
    rows = []
    for plot_id in plot_ids:
        forecast = forecasts_by_plot.get(plot_id, {"count": 0, "low": 0.0, "high": 0.0})
        actual = actual_by_plot.get(plot_id, 0.0)
        midpoint = (forecast["low"] + forecast["high"]) / 2
        rows.append(
            rpt_schemas.YieldHarvestRow(
                plot_id=plot_id,
                forecast_count=forecast["count"],
                estimated_yield_kg_low=round(forecast["low"], 1),
                estimated_yield_kg_high=round(forecast["high"], 1),
                actual_harvest_kg=round(actual, 1),
                variance_kg=round(actual - midpoint, 1),
            )
        )
    return rows


def maintenance_report(db: Session, *, farm_id: str, filters: rpt_schemas.ReportFilter) -> list[rpt_schemas.MaintenanceRow]:
    request_query = db.query(asset_models.MaintenanceRequest).filter(asset_models.MaintenanceRequest.farm_id == farm_id)
    for clause in _in_range(asset_models.MaintenanceRequest.created_at, filters.date_from, filters.date_to):
        request_query = request_query.filter(clause)
    requests = request_query.all()

    total_requests = len(requests)
    pm_requests = sum(1 for r in requests if r.strategy in ("preventive", "predictive"))
    pm_compliance_pct = round(pm_requests / total_requests * 100, 1) if total_requests else 0.0

    requests_by_strategy: dict[str, list] = {}
    for r in requests:
        requests_by_strategy.setdefault(r.strategy, []).append(r.id)

    rows = []
    for strategy, request_ids in sorted(requests_by_strategy.items()):
        work_orders = (
            db.query(asset_models.WorkOrder)
            .filter(asset_models.WorkOrder.request_id.in_(request_ids), asset_models.WorkOrder.status == "completed")
            .all()
        )
        labor_hours = [w.labor_hours for w in work_orders if w.labor_hours is not None]
        rows.append(
            rpt_schemas.MaintenanceRow(
                strategy=strategy,
                request_count=len(request_ids),
                work_orders_completed=len(work_orders),
                average_labor_hours=round(sum(labor_hours) / len(labor_hours), 2) if labor_hours else None,
                pm_compliance_pct=pm_compliance_pct,
            )
        )
    return rows


def inventory_report(db: Session, *, farm_id: str, filters: rpt_schemas.ReportFilter) -> list[rpt_schemas.InventoryRow]:
    """Farm-scoped via `Warehouse.farm_id` - the farm-scoped inventory
    split the Phase 16 Command Center checklist deferred (a fleet-wide-
    only inventory widget) is implemented here instead, for reporting."""
    warehouse_ids = [w.id for w in db.query(inventory_models.Warehouse).filter(inventory_models.Warehouse.farm_id == farm_id).all()]
    if not warehouse_ids:
        return []

    lots = db.query(inventory_models.StockLot).filter(inventory_models.StockLot.warehouse_id.in_(warehouse_ids)).all()
    items_by_id = {item.id: item for item in db.query(inventory_models.Item).all()}

    on_hand_by_item: dict[str, float] = {}
    lots_by_item: dict[str, list] = {}
    for lot in lots:
        on_hand_by_item[lot.item_id] = on_hand_by_item.get(lot.item_id, 0.0) + lot.quantity
        lots_by_item.setdefault(lot.item_id, []).append(lot)

    lot_ids = [lot.id for lot in lots]
    movements = []
    if lot_ids:
        movement_query = db.query(inventory_models.StockMovement).filter(inventory_models.StockMovement.lot_id.in_(lot_ids))
        for clause in _in_range(inventory_models.StockMovement.created_at, filters.date_from, filters.date_to):
            movement_query = movement_query.filter(clause)
        movements = movement_query.all()

    lot_to_item = {lot.id: lot.item_id for lot in lots}
    received_by_item: dict[str, float] = {}
    issued_by_item: dict[str, float] = {}
    for m in movements:
        item_id = lot_to_item.get(m.lot_id)
        if item_id is None:
            continue
        if m.movement_type == "receipt":
            received_by_item[item_id] = received_by_item.get(item_id, 0.0) + m.quantity_delta
        elif m.movement_type == "issue":
            issued_by_item[item_id] = issued_by_item.get(item_id, 0.0) + abs(m.quantity_delta)

    soon = datetime.now(timezone.utc).date() + timedelta(days=30)
    rows = []
    for item_id, on_hand in on_hand_by_item.items():
        item = items_by_id.get(item_id)
        if item is None:
            continue
        expiring = sum(1 for lot in lots_by_item.get(item_id, []) if lot.expiry_date and lot.expiry_date <= soon)
        rows.append(
            rpt_schemas.InventoryRow(
                item_code=item.code,
                item_name=item.name,
                on_hand_qty=round(on_hand, 2),
                received_qty=round(received_by_item.get(item_id, 0.0), 2),
                issued_qty=round(issued_by_item.get(item_id, 0.0), 2),
                lots_expiring_within_30_days=expiring,
            )
        )
    return sorted(rows, key=lambda r: r.item_code)


def financial_report(db: Session, *, farm_id: str, filters: rpt_schemas.ReportFilter) -> list[rpt_schemas.FinancialRow]:
    dimensions = {"farm_id": farm_id}
    if filters.plot_id:
        dimensions["plot_id"] = filters.plot_id
    if filters.season_id:
        dimensions["season_id"] = filters.season_id

    rows = []
    for direction in ("revenue", "expense"):
        ledger_query = db.query(func.coalesce(func.sum(acct_models.LedgerEntry.amount), 0.0)).filter(
            acct_models.LedgerEntry.direction == direction, acct_models.LedgerEntry.dimensions.contains(dimensions)
        )
        for clause in _in_range(acct_models.LedgerEntry.posted_at, filters.date_from, filters.date_to):
            ledger_query = ledger_query.filter(clause)
        actual = ledger_query.scalar()

        budget_query = db.query(acct_models.Budget).filter(
            acct_models.Budget.direction == direction, acct_models.Budget.dimensions.contains(dimensions)
        )
        if filters.date_from:
            budget_query = budget_query.filter(acct_models.Budget.period_end >= filters.date_from)
        if filters.date_to:
            budget_query = budget_query.filter(acct_models.Budget.period_start <= filters.date_to)
        budgets = budget_query.all()
        budgeted = sum(b.amount for b in budgets) if budgets else None

        rows.append(
            rpt_schemas.FinancialRow(
                direction=direction,
                actual_amount=round(actual, 2),
                budgeted_amount=round(budgeted, 2) if budgeted is not None else None,
                variance=round(actual - budgeted, 2) if budgeted is not None else None,
            )
        )
    return rows
