"""Prometheus-compatible metrics (NFR-009). `prometheus_client` is the
standard library for this rather than a hand-rolled counter registry.
Path labels use the matched route's *template* (e.g.
"/api/v1/farm/farms/{farm_id}"), not the raw URL, to keep cardinality
bounded - a raw path would mint a new label value per UUID ever requested.
"""
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)
REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds", "HTTP request duration in seconds", ["method", "path"]
)

__all__ = ["REQUEST_COUNT", "REQUEST_DURATION_SECONDS", "CONTENT_TYPE_LATEST", "generate_latest"]
