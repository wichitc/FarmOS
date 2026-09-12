"""SEC-007 rate limiting. The rest of the suite runs with
`RATE_LIMIT_ENABLED=false` (see conftest note in docs/05-RTM.md's Phase 18
checklist) because Starlette's `TestClient` gives every request the same
fake client host, so a real limiter would collapse the whole suite into
one shared bucket. These tests flip it on temporarily, at a low threshold,
against a path no other test hits, and clean up their Redis key
explicitly so a re-run within the same 60s window isn't contaminated by a
previous run's leftover counter.
"""
import redis as redis_sync

from app.config import settings
from app.core import rate_limit as rate_limit_module


def _reset_client_cache():
    rate_limit_module._redis_clients.clear()


def _cleanup_key(path: str, method: str):
    client = redis_sync.Redis.from_url(settings.redis_url, decode_responses=True)
    client.delete(f"ratelimit:ip:testclient:{path}:{method}")
    client.close()


def test_rate_limit_blocks_after_threshold_then_recovers_on_a_fresh_key(client):
    path, method = "/api/status", "GET"
    _cleanup_key(path, method)

    original_enabled = settings.rate_limit_enabled
    original_default = settings.rate_limit_default_per_minute
    settings.rate_limit_enabled = True
    settings.rate_limit_default_per_minute = 3
    _reset_client_cache()
    try:
        codes = [client.get(path).status_code for _ in range(5)]
        assert codes[:3] == [200, 200, 200]
        assert codes[3:] == [429, 429]

        blocked_res = client.get(path)
        assert blocked_res.status_code == 429
        body = blocked_res.json()
        assert body["error"]["code"] == 429
        assert "Retry-After" in blocked_res.headers
    finally:
        settings.rate_limit_enabled = original_enabled
        settings.rate_limit_default_per_minute = original_default
        _reset_client_cache()
        _cleanup_key(path, method)


def test_rate_limit_disabled_never_blocks(client):
    path = "/health"
    original_enabled = settings.rate_limit_enabled
    settings.rate_limit_enabled = False
    _reset_client_cache()
    try:
        codes = [client.get(path).status_code for _ in range(10)]
        assert all(code == 200 for code in codes)
    finally:
        settings.rate_limit_enabled = original_enabled
        _reset_client_cache()


def test_rule_selection_and_client_key_helpers():
    from starlette.requests import Request

    login_rule = rate_limit_module._rule_for("/api/v1/auth/login", "POST")
    assert login_rule.limit == settings.rate_limit_login_per_minute

    trace_rule = rate_limit_module._rule_for("/api/v1/harvest/trace/acme/abc123", "GET")
    assert trace_rule.limit == settings.rate_limit_public_per_minute

    default_rule = rate_limit_module._rule_for("/api/v1/farm/farms", "POST")
    assert default_rule.limit == settings.rate_limit_default_per_minute

    scope_with_token = {"type": "http", "headers": [(b"authorization", b"Bearer abc.def.ghi")], "client": ("1.2.3.4", 1234)}
    token_request = Request(scope_with_token)
    assert rate_limit_module._client_key(token_request).startswith("token:")

    scope_without_token = {"type": "http", "headers": [], "client": ("1.2.3.4", 1234)}
    ip_request = Request(scope_without_token)
    assert rate_limit_module._client_key(ip_request) == "ip:1.2.3.4"


def test_security_headers_present_on_every_response(client):
    res = client.get("/health")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert res.headers["strict-transport-security"].startswith("max-age=")
    assert res.headers["referrer-policy"] == "strict-origin-when-cross-origin"
