from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class GeoJSONGeometry(BaseModel):
    """A bare GeoJSON geometry object, e.g. {"type": "Polygon", "coordinates": [...]}."""

    type: str
    coordinates: Any


class MapFeatureCreate(BaseModel):
    feature_type: str
    name: str
    geometry: GeoJSONGeometry
    properties: dict = {}


class MapFeatureUpdate(BaseModel):
    name: Optional[str] = None
    geometry: Optional[GeoJSONGeometry] = None
    properties: Optional[dict] = None


class MapFeatureOut(BaseModel):
    id: str
    farm_id: str
    feature_type: str
    name: str
    geometry: Optional[dict] = None
    properties: dict

    model_config = ConfigDict(from_attributes=True)


class BoundaryOut(BaseModel):
    id: str
    boundary: Optional[dict] = None
    area_hectares: Optional[float] = None


class CenterlineOut(BaseModel):
    id: str
    centerline: Optional[dict] = None


class MeasureRequest(BaseModel):
    geometry: GeoJSONGeometry


class MeasureOut(BaseModel):
    geometry_type: str
    area_m2: Optional[float] = None
    area_hectares: Optional[float] = None
    length_m: Optional[float] = None


class NearbyTreeOut(BaseModel):
    id: str
    code: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    distance_m: float


class LayerInfo(BaseModel):
    layer: str
    label: str
    count: int


class GeoJSONFeature(BaseModel):
    type: str = "Feature"
    geometry: GeoJSONGeometry
    properties: dict = {}


class GeoJSONFeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: list[GeoJSONFeature]
