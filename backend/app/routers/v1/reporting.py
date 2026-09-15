from datetime import date
from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.deps import assert_farm_scope, require_permission
from ...database import get_db
from ...farm import models as farm_models
from ...foundation import models as fm
from ...reporting import export as rpt_export
from ...reporting import queries as rpt_queries
from ...reporting import schemas as rpt_schemas

router = APIRouter(prefix="/api/v1/reports", tags=["reporting"])


def _get_or_404(db: Session, model, obj_id: str, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


def _filters(
    plot_id: Optional[str] = Query(default=None),
    season_id: Optional[str] = Query(default=None),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
) -> rpt_schemas.ReportFilter:
    return rpt_schemas.ReportFilter(plot_id=plot_id, season_id=season_id, date_from=date_from, date_to=date_to)


def _respond(report_name: str, data: Union[BaseModel, list[BaseModel]], fmt: str):
    rows = data if isinstance(data, list) else [data]
    if fmt == "json":
        return JSONResponse(content=[r.model_dump(mode="json") for r in rows] if isinstance(data, list) else data.model_dump(mode="json"))
    if fmt == "csv":
        return Response(
            content=rpt_export.rows_to_csv(rows),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{report_name}.csv"'},
        )
    if fmt == "pdf":
        return Response(
            content=rpt_export.rows_to_pdf(report_name, rows),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{report_name}.pdf"'},
        )
    raise HTTPException(status_code=422, detail=f"Unknown format '{fmt}' - use json, csv, or pdf")


def _require_farm_scope(db: Session, user: fm.User, farm_id: str) -> farm_models.Farm:
    farm = _get_or_404(db, farm_models.Farm, farm_id, "Farm")
    assert_farm_scope(db, user, "reporting.view", farm.id)
    return farm


@router.get("/farms/{farm_id}/health")
def farm_health_report(
    farm_id: str,
    format: str = Query(default="json"),
    filters: rpt_schemas.ReportFilter = Depends(_filters),
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("reporting.view")),
):
    _require_farm_scope(db, current_user, farm_id)
    row = rpt_queries.farm_health_report(db, tenant_id=current_user.tenant_id, farm_id=farm_id, filters=filters)
    return _respond("farm_health", row, format)


@router.get("/farms/{farm_id}/irrigation-fertigation-usage")
def irrigation_fertigation_usage_report(
    farm_id: str,
    format: str = Query(default="json"),
    filters: rpt_schemas.ReportFilter = Depends(_filters),
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("reporting.view")),
):
    _require_farm_scope(db, current_user, farm_id)
    rows = rpt_queries.irrigation_fertigation_usage_report(db, farm_id=farm_id, filters=filters)
    return _respond("irrigation_fertigation_usage", rows, format)


@router.get("/farms/{farm_id}/work-completion")
def work_completion_report(
    farm_id: str,
    format: str = Query(default="json"),
    filters: rpt_schemas.ReportFilter = Depends(_filters),
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("reporting.view")),
):
    _require_farm_scope(db, current_user, farm_id)
    rows = rpt_queries.work_completion_report(db, farm_id=farm_id, filters=filters)
    return _respond("work_completion", rows, format)


@router.get("/farms/{farm_id}/disease-trend")
def disease_trend_report(
    farm_id: str,
    format: str = Query(default="json"),
    filters: rpt_schemas.ReportFilter = Depends(_filters),
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("reporting.view")),
):
    _require_farm_scope(db, current_user, farm_id)
    rows = rpt_queries.disease_trend_report(db, farm_id=farm_id, filters=filters)
    return _respond("disease_trend", rows, format)


@router.get("/farms/{farm_id}/yield-harvest")
def yield_harvest_report(
    farm_id: str,
    format: str = Query(default="json"),
    filters: rpt_schemas.ReportFilter = Depends(_filters),
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("reporting.view")),
):
    _require_farm_scope(db, current_user, farm_id)
    rows = rpt_queries.yield_harvest_report(db, farm_id=farm_id, filters=filters)
    return _respond("yield_harvest", rows, format)


@router.get("/farms/{farm_id}/maintenance")
def maintenance_report(
    farm_id: str,
    format: str = Query(default="json"),
    filters: rpt_schemas.ReportFilter = Depends(_filters),
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("reporting.view")),
):
    _require_farm_scope(db, current_user, farm_id)
    rows = rpt_queries.maintenance_report(db, farm_id=farm_id, filters=filters)
    return _respond("maintenance", rows, format)


@router.get("/farms/{farm_id}/inventory")
def inventory_report(
    farm_id: str,
    format: str = Query(default="json"),
    filters: rpt_schemas.ReportFilter = Depends(_filters),
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("reporting.view")),
):
    _require_farm_scope(db, current_user, farm_id)
    rows = rpt_queries.inventory_report(db, farm_id=farm_id, filters=filters)
    return _respond("inventory", rows, format)


@router.get("/farms/{farm_id}/financial")
def financial_report(
    farm_id: str,
    format: str = Query(default="json"),
    filters: rpt_schemas.ReportFilter = Depends(_filters),
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("reporting.view")),
):
    _require_farm_scope(db, current_user, farm_id)
    rows = rpt_queries.financial_report(db, farm_id=farm_id, filters=filters)
    return _respond("financial", rows, format)
