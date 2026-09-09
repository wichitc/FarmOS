from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.deps import assert_farm_scope, get_current_user, require_permission
from ...database import get_db
from ...farm import models as farm_models
from ...foundation import models as fm
from ...foundation.audit import record_audit
from ...gis import models as gis_models
from ...gis.geo import element_to_geojson, geojson_to_element, measure
from ...gis.schemas import (
    GeoJSONFeature,
    GeoJSONFeatureCollection,
    GeoJSONGeometry,
    LayerInfo,
    MapFeatureCreate,
    MapFeatureOut,
    MapFeatureUpdate,
    MeasureOut,
    MeasureRequest,
    NearbyTreeOut,
)

router = APIRouter(prefix="/api/v1/gis", tags=["gis"])


def _get_or_404(db: Session, model, obj_id: str, label: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


def _feature_out(feature: gis_models.MapFeature) -> dict:
    return {
        "id": feature.id,
        "farm_id": feature.farm_id,
        "feature_type": feature.feature_type,
        "name": feature.name,
        "geometry": element_to_geojson(feature.geom),
        "properties": feature.properties,
    }


# ---------------------------------------------------------------------------
# Measure (FR-GIS-005) - stateless, no farm scope needed.
# ---------------------------------------------------------------------------

@router.post("/measure", response_model=MeasureOut)
def measure_geometry(
    payload: MeasureRequest,
    db: Session = Depends(get_db),
    _user: fm.User = Depends(get_current_user),
):
    return measure(db, payload.geometry.model_dump())


# ---------------------------------------------------------------------------
# Layer manager (FR-GIS-005) - per docs/12-UX-UI.md §6.2, the Farm Map page's
# left-hand layer list with a visibility toggle; this returns the catalog of
# layer types + counts that UI is built from.
# ---------------------------------------------------------------------------

@router.get("/farms/{farm_id}/layers", response_model=list[LayerInfo])
def list_layers(
    farm_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("farm.view")),
):
    farm = _get_or_404(db, farm_models.Farm, farm_id, "Farm")
    assert_farm_scope(db, user, "farm.view", farm.id)

    counts = db.execute(
        text(
            """
            SELECT 'zone', count(*) FROM zones WHERE farm_id = :fid
            UNION ALL SELECT 'plot', count(*) FROM plots p JOIN zones z ON z.id = p.zone_id WHERE z.farm_id = :fid
            UNION ALL SELECT 'block', count(*) FROM blocks b JOIN plots p ON p.id = b.plot_id JOIN zones z ON z.id = p.zone_id WHERE z.farm_id = :fid
            UNION ALL SELECT 'row', count(*) FROM rows r
                JOIN blocks b ON b.id = r.block_id JOIN plots p ON p.id = b.plot_id JOIN zones z ON z.id = p.zone_id WHERE z.farm_id = :fid
            UNION ALL SELECT 'tree', count(*) FROM trees t
                JOIN rows r ON r.id = t.row_id JOIN blocks b ON b.id = r.block_id
                JOIN plots p ON p.id = b.plot_id JOIN zones z ON z.id = p.zone_id
                WHERE z.farm_id = :fid AND t.deleted_at IS NULL
            """
        ),
        {"fid": farm_id},
    ).all()
    layer_counts = {layer: n for layer, n in counts}

    feature_counts = dict(
        db.execute(
            text("SELECT feature_type, count(*) FROM map_features WHERE farm_id = :fid GROUP BY feature_type"),
            {"fid": farm_id},
        ).all()
    )

    layers = [
        LayerInfo(layer="farm_boundary", label="Farm boundary", count=1 if farm.boundary is not None else 0),
        LayerInfo(layer="zone", label="Zones", count=layer_counts.get("zone", 0)),
        LayerInfo(layer="plot", label="Plots", count=layer_counts.get("plot", 0)),
        LayerInfo(layer="block", label="Blocks", count=layer_counts.get("block", 0)),
        LayerInfo(layer="row", label="Rows", count=layer_counts.get("row", 0)),
        LayerInfo(layer="tree", label="Trees", count=layer_counts.get("tree", 0)),
    ]
    for feature_type, count in feature_counts.items():
        layers.append(LayerInfo(layer=f"map_feature:{feature_type}", label=feature_type.replace("_", " ").title(), count=count))
    return layers


# ---------------------------------------------------------------------------
# Map features (FR-GIS-001 infrastructure layer)
# ---------------------------------------------------------------------------

@router.post("/farms/{farm_id}/features", response_model=MapFeatureOut, status_code=201)
def create_feature(
    farm_id: str,
    payload: MapFeatureCreate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("farm.manage")),
):
    farm = _get_or_404(db, farm_models.Farm, farm_id, "Farm")
    assert_farm_scope(db, current_user, "farm.manage", farm.id)

    feature = gis_models.MapFeature(
        tenant_id=current_user.tenant_id,
        farm_id=farm.id,
        feature_type=payload.feature_type,
        name=payload.name,
        geom=geojson_to_element(payload.geometry.model_dump()),
        properties=payload.properties,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(feature)
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="map_feature.create",
        entity_type="map_feature",
        entity_id=feature.id,
        new_values={"farm_id": farm.id, "feature_type": feature.feature_type, "name": feature.name},
    )
    db.commit()
    return _feature_out(feature)


@router.get("/farms/{farm_id}/features", response_model=list[MapFeatureOut])
def list_features(
    farm_id: str,
    feature_type: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("farm.view")),
):
    farm = _get_or_404(db, farm_models.Farm, farm_id, "Farm")
    assert_farm_scope(db, user, "farm.view", farm.id)

    query = db.query(gis_models.MapFeature).filter(gis_models.MapFeature.farm_id == farm_id)
    if feature_type:
        query = query.filter(gis_models.MapFeature.feature_type == feature_type)
    return [_feature_out(f) for f in query.order_by(gis_models.MapFeature.name.asc()).all()]


@router.patch("/features/{feature_id}", response_model=MapFeatureOut)
def update_feature(
    feature_id: str,
    payload: MapFeatureUpdate,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("farm.manage")),
):
    feature = _get_or_404(db, gis_models.MapFeature, feature_id, "Map feature")
    assert_farm_scope(db, current_user, "farm.manage", feature.farm_id)

    if payload.name is not None:
        feature.name = payload.name
    if payload.properties is not None:
        feature.properties = payload.properties
    if payload.geometry is not None:
        feature.geom = geojson_to_element(payload.geometry.model_dump())
    feature.updated_by = current_user.id
    db.flush()

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="map_feature.update",
        entity_type="map_feature",
        entity_id=feature.id,
    )
    db.commit()
    return _feature_out(feature)


@router.delete("/features/{feature_id}", status_code=204)
def delete_feature(
    feature_id: str,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("farm.manage")),
):
    feature = _get_or_404(db, gis_models.MapFeature, feature_id, "Map feature")
    assert_farm_scope(db, current_user, "farm.manage", feature.farm_id)

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="map_feature.delete",
        entity_type="map_feature",
        entity_id=feature.id,
    )
    db.delete(feature)
    db.commit()


# ---------------------------------------------------------------------------
# Import / export (FR-GIS-003)
# ---------------------------------------------------------------------------

@router.get("/farms/{farm_id}/export", response_model=GeoJSONFeatureCollection)
def export_farm(
    farm_id: str,
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("farm.view")),
):
    farm = _get_or_404(db, farm_models.Farm, farm_id, "Farm")
    assert_farm_scope(db, user, "farm.view", farm.id)

    features: list[GeoJSONFeature] = []

    def add(geom, layer: str, props: dict):
        geojson = element_to_geojson(geom)
        if geojson is not None:
            features.append(GeoJSONFeature(geometry=GeoJSONGeometry(**geojson), properties={**props, "layer": layer}))

    add(farm.boundary, "farm", {"id": farm.id, "name": farm.name})
    for zone in db.query(farm_models.Zone).filter(farm_models.Zone.farm_id == farm.id).all():
        add(zone.boundary, "zone", {"id": zone.id, "name": zone.name, "code": zone.code})
        for plot in db.query(farm_models.Plot).filter(farm_models.Plot.zone_id == zone.id).all():
            add(plot.boundary, "plot", {"id": plot.id, "name": plot.name, "code": plot.code})
            for block in db.query(farm_models.Block).filter(farm_models.Block.plot_id == plot.id).all():
                add(block.boundary, "block", {"id": block.id, "name": block.name, "code": block.code})
                for row in db.query(farm_models.Row).filter(farm_models.Row.block_id == block.id).all():
                    add(row.centerline, "row", {"id": row.id, "name": row.name, "code": row.code})
                    for tree in (
                        db.query(farm_models.Tree)
                        .filter(farm_models.Tree.row_id == row.id, farm_models.Tree.deleted_at.is_(None))
                        .all()
                    ):
                        add(tree.location, "tree", {"id": tree.id, "code": tree.code, "growth_stage": tree.growth_stage})

    for feature in db.query(gis_models.MapFeature).filter(gis_models.MapFeature.farm_id == farm.id).all():
        add(
            feature.geom,
            "map_feature",
            {"id": feature.id, "name": feature.name, "feature_type": feature.feature_type, **feature.properties},
        )

    return GeoJSONFeatureCollection(features=features)


@router.post("/farms/{farm_id}/import", response_model=list[MapFeatureOut], status_code=201)
def import_features(
    farm_id: str,
    payload: GeoJSONFeatureCollection,
    db: Session = Depends(get_db),
    current_user: fm.User = Depends(require_permission("farm.manage")),
):
    """Bulk-imports map features (FR-GIS-003) from an uploaded GeoJSON
    FeatureCollection. Each feature's `properties` must carry `feature_type`
    (one of `app.gis.models.MAP_FEATURE_TYPES`) and `name`. Farm/zone/plot/
    block boundaries are set individually via their own `PATCH .../boundary`
    endpoints, not through this bulk importer - keeping "which polygon is
    which hierarchy level" unambiguous."""
    farm = _get_or_404(db, farm_models.Farm, farm_id, "Farm")
    assert_farm_scope(db, current_user, "farm.manage", farm.id)

    created = []
    for i, feat in enumerate(payload.features):
        feature_type = feat.properties.get("feature_type")
        name = feat.properties.get("name")
        if not feature_type or not name:
            raise HTTPException(status_code=422, detail=f"Feature {i}: 'feature_type' and 'name' are required in properties")
        if feature_type not in gis_models.MAP_FEATURE_TYPES:
            raise HTTPException(status_code=422, detail=f"Feature {i}: unknown feature_type '{feature_type}'")

        feature = gis_models.MapFeature(
            tenant_id=current_user.tenant_id,
            farm_id=farm.id,
            feature_type=feature_type,
            name=name,
            geom=geojson_to_element(feat.geometry.model_dump()),
            properties={k: v for k, v in feat.properties.items() if k not in ("feature_type", "name")},
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        db.add(feature)
        created.append(feature)

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Import failed") from exc

    record_audit(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="map_feature.import",
        entity_type="map_feature",
        entity_id=farm.id,
        new_values={"farm_id": farm.id, "count": len(created)},
    )
    db.commit()
    return [_feature_out(f) for f in created]


# ---------------------------------------------------------------------------
# Spatial queries (FR-GIS-007)
# ---------------------------------------------------------------------------

@router.get("/trees/nearby", response_model=list[NearbyTreeOut])
def trees_nearby(
    farm_id: str,
    lat: float,
    lng: float,
    radius_m: float = Query(gt=0),
    db: Session = Depends(get_db),
    user: fm.User = Depends(require_permission("tree.view")),
):
    farm = _get_or_404(db, farm_models.Farm, farm_id, "Farm")
    assert_farm_scope(db, user, "tree.view", farm.id)

    rows = db.execute(
        text(
            """
            SELECT t.id, t.code, t.lat, t.lng,
                   ST_Distance(t.location::geography, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography) AS dist
            FROM trees t
            JOIN rows r ON r.id = t.row_id
            JOIN blocks b ON b.id = r.block_id
            JOIN plots p ON p.id = b.plot_id
            JOIN zones z ON z.id = p.zone_id
            WHERE z.farm_id = :fid
              AND t.deleted_at IS NULL
              AND t.location IS NOT NULL
              AND ST_DWithin(t.location::geography, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, :radius)
            ORDER BY dist ASC
            """
        ),
        {"fid": farm_id, "lat": lat, "lng": lng, "radius": radius_m},
    ).all()

    return [
        NearbyTreeOut(id=str(r.id), code=r.code, lat=r.lat, lng=r.lng, distance_m=r.dist)
        for r in rows
    ]
