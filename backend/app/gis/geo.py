"""Shared GeoJSON <-> PostGIS marshalling (Phase 5, GIS-001).

Kept in one place because both `routers/v1/farm.py` (boundary/centerline
endpoints) and `routers/v1/gis.py` (map features, export/import, measure)
need to go back and forth between the GeoJSON the API speaks and the WKB
GeoAlchemy2/PostGIS store.
"""
import json
from typing import Optional

from fastapi import HTTPException
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point, mapping, shape
from shapely.geometry.base import BaseGeometry
from sqlalchemy import text
from sqlalchemy.orm import Session

SRID = 4326


def point_from_latlng(lat: Optional[float], lng: Optional[float], *, srid: int = SRID):
    """Derives a PostGIS Point from the scalar lat/lng floats that remain the
    source of truth on Tree/Farm (Phase 4 API contract, unchanged). Returns
    None when either coordinate is missing, so callers can assign it
    directly to a nullable `location`/geometry column."""
    if lat is None or lng is None:
        return None
    return from_shape(Point(lng, lat), srid=srid)


def geojson_to_element(geojson: dict, *, srid: int = SRID):
    """Parses a GeoJSON geometry dict into a GeoAlchemy2 WKBElement ready to
    assign to a `Geometry` column. Raises HTTPException(422) on malformed
    input rather than letting a shapely error surface as a 500."""
    try:
        geom: BaseGeometry = shape(geojson)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid GeoJSON geometry: {exc}") from exc
    if not geom.is_valid:
        raise HTTPException(status_code=422, detail="Geometry is not valid (self-intersecting or malformed)")
    return from_shape(geom, srid=srid)


def element_to_geojson(geom) -> Optional[dict]:
    """Converts a stored geometry (WKBElement from a loaded ORM row) back to
    a plain GeoJSON dict, or None if the column is NULL."""
    if geom is None:
        return None
    return mapping(to_shape(geom))


def row_bearing_rad(db: Session, row_id: str) -> float:
    """Bearing (radians, `ST_Azimuth` convention: 0 = north, clockwise) of a
    Row's `centerline`, or 0.0 (north) as the fallback used before any
    centerline has been drawn - matches Phase 4's original placeholder
    direction (straight increasing latitude)."""
    result = db.execute(
        text(
            "SELECT ST_Azimuth(ST_StartPoint(centerline), ST_EndPoint(centerline)) "
            "FROM rows WHERE id = :id AND centerline IS NOT NULL"
        ),
        {"id": row_id},
    ).first()
    return result[0] if result and result[0] is not None else 0.0


def project_latlng(db: Session, lat: float, lng: float, distance_m: float, bearing_rad: float) -> tuple[float, float]:
    """Geodesic projection (FR-GIS-006): moves `distance_m` meters from
    (lat, lng) along `bearing_rad`, returning the resulting (lat, lng).
    Real meter-based math via PostGIS `ST_Project` on a geography point,
    replacing Phase 4's placeholder `lat += i * spacing_m * 1e-5`."""
    result = db.execute(
        text(
            "SELECT ST_Y(pt::geometry), ST_X(pt::geometry) FROM ("
            "  SELECT ST_Project(ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, :dist, :bearing) AS pt"
            ") t"
        ),
        {"lng": lng, "lat": lat, "dist": distance_m, "bearing": bearing_rad},
    ).first()
    return result[0], result[1]


def point_in_wkt(db: Session, boundary_wkt: str, lat: float, lng: float) -> bool:
    """True if (lat, lng) falls inside the given WKT polygon (FR-GIS-006:
    clip generated tree points to the plot boundary)."""
    result = db.execute(
        text("SELECT ST_Contains(ST_GeomFromText(:wkt, 4326), ST_SetSRID(ST_MakePoint(:lng, :lat), 4326))"),
        {"wkt": boundary_wkt, "lng": lng, "lat": lat},
    ).first()
    return bool(result[0])


def boundary_wkt_of(db: Session, table: str, row_id: str) -> Optional[str]:
    result = db.execute(text(f"SELECT ST_AsText(boundary) FROM {table} WHERE id = :id"), {"id": row_id}).first()
    return result[0] if result else None


def measure(db: Session, geojson: dict) -> dict:
    """FR-GIS-005 ad-hoc measure tool: geodesic area (Polygon) or length
    (LineString) of a not-yet-persisted GeoJSON geometry, via PostGIS
    (`ST_GeomFromGeoJSON` + geography cast) rather than a planar shapely
    calculation, which would be wrong in degrees^2/degrees for WGS84 input."""
    try:
        row = db.execute(
            text(
                "SELECT GeometryType(g), ST_Area(g::geography), ST_Length(g::geography) "
                "FROM (SELECT ST_GeomFromGeoJSON(:gj) AS g) t"
            ),
            {"gj": json.dumps(geojson)},
        ).first()
    except Exception as exc:  # invalid GeoJSON reaching PostGIS surfaces as a DB error
        db.rollback()
        raise HTTPException(status_code=422, detail=f"Invalid geometry: {exc}") from exc

    geometry_type, area_m2, length_m = row
    is_polygon = geometry_type in ("POLYGON", "MULTIPOLYGON")
    return {
        "geometry_type": geometry_type,
        "area_m2": area_m2 if is_polygon else None,
        "area_hectares": (area_m2 / 10_000) if is_polygon and area_m2 is not None else None,
        "length_m": length_m if not is_polygon else None,
    }


def area_hectares_of(db: Session, table: str, row_id: str, geom_column: str = "boundary") -> Optional[float]:
    """Geodesic area (WGS84 -> geography cast, so it's real m^2, not
    degrees^2) of a persisted polygon column, in hectares. Requires the
    geometry to already be flushed in this transaction. `table`/`geom_column`
    are internal constants (never user input), so building the identifier
    into the SQL string here does not admit injection."""
    row = db.execute(
        text(f"SELECT ST_Area({geom_column}::geography) FROM {table} WHERE id = :id"),
        {"id": row_id},
    ).first()
    if row is None or row[0] is None:
        return None
    return row[0] / 10_000
