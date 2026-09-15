"""NFR-005/009 follow-on to Phase 18: structured JSON logging with
correlation ids, and a Prometheus-compatible /metrics endpoint.
"""
import json
import logging

from app.config import settings
from app.core import rate_limit as rate_limit_module
from app.core.logging import JSONFormatter, correlation_id_var


def test_json_formatter_produces_valid_json_with_correlation_id():
    token = correlation_id_var.set("unit-test-corr")
    try:
        record = logging.LogRecord(
            name="test.logger", level=logging.INFO, pathname=__file__, lineno=1,
            msg="hello %s", args=("world",), exc_info=None,
        )
        payload = json.loads(JSONFormatter().format(record))
    finally:
        correlation_id_var.reset(token)

    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.logger"
    assert payload["correlation_id"] == "unit-test-corr"
    assert "timestamp" in payload


def test_json_formatter_omits_correlation_id_when_unset():
    record = logging.LogRecord(
        name="test.logger", level=logging.WARNING, pathname=__file__, lineno=1,
        msg="no request in flight", args=(), exc_info=None,
    )
    payload = json.loads(JSONFormatter().format(record))
    assert "correlation_id" not in payload


class _CollectingHandler(logging.Handler):
    """Captures formatted output directly via the real `JSONFormatter`,
    bypassing stdout/stderr capture entirely - pytest's own capture
    fixtures (capsys/capfd) disagree with `configure_logging()`'s
    `StreamHandler` about which stream/fd is "live" at any given moment
    (it binds to `sys.stderr` once, at `app.main` import time, before any
    per-test capture layer exists), which made this flaky to prove through
    process-output capture even though the feature itself works - visible
    directly in pytest's own end-of-test "Captured log call" section
    during development of this test. Attaching a handler is what the
    logging module itself is meant to be inspected through."""

    def __init__(self):
        super().__init__()
        self.setFormatter(JSONFormatter())
        self.formatted: list[str] = []

    def emit(self, record):
        self.formatted.append(self.format(record))


def test_correlation_id_appears_in_structured_log_output_for_a_real_request(client):
    """Proves the contextvar is actually wired through
    `correlation_id_middleware`, not just unit-testable in isolation:
    forces the rate limiter's fail-open path (an unreachable Redis) so it
    logs a real warning mid-request, then checks the formatted output
    (produced while the request's context was still active) carries the
    correlation id sent in on the request header."""
    original_enabled = settings.rate_limit_enabled
    original_redis_url = settings.redis_url
    settings.rate_limit_enabled = True
    settings.redis_url = "redis://127.0.0.1:1/0"  # nothing listens on port 1 - fails fast
    rate_limit_module._redis_clients.clear()

    handler = _CollectingHandler()
    rl_logger = logging.getLogger("app.rate_limit")
    rl_logger.addHandler(handler)
    try:
        res = client.get("/api/status", headers={"X-Correlation-Id": "test-corr-observability"})
        assert res.status_code == 200
        assert handler.formatted, "expected the rate limiter's fail-open warning to be logged"
        payload = json.loads(handler.formatted[-1])
        assert payload["level"] == "WARNING"
        assert payload["correlation_id"] == "test-corr-observability"
    finally:
        rl_logger.removeHandler(handler)
        settings.rate_limit_enabled = original_enabled
        settings.redis_url = original_redis_url
        rate_limit_module._redis_clients.clear()


def test_metrics_endpoint_exposes_prometheus_format(client):
    client.get("/api/status")
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "text/plain" in res.headers["content-type"]
    body = res.text
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body
    assert 'method="GET"' in body


def test_metrics_endpoint_is_not_counted_by_itself(client):
    client.get("/metrics")
    res = client.get("/metrics")
    body = res.text
    assert 'path="/metrics"' not in body
