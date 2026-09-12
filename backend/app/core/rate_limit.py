"""Rate limiting (Phase 18, SEC-007): basic abuse protection via a
Redis-backed fixed-window counter (INCR + EXPIRE) - simpler than a token
bucket or sliding-window log, and precise enough for coarse abuse
mitigation (brute-force login attempts, scraping the one public
unauthenticated endpoint) rather than exact traffic shaping.

If Redis itself is unreachable, requests are allowed through rather than
the API failing closed - the same "degrade gracefully, not fail closed,
when a downstream dependency is unavailable" principle NFR-004 states for
the AI service/external weather API, applied here: rate limiting is
defense-in-depth, not a feature core farm-operations traffic should go
down over.

Disabled entirely via `RATE_LIMIT_ENABLED=false` for test/CI runs -
Starlette's `TestClient` gives every request the same fake client host
("testclient"), so a real IP-keyed limiter would collapse the whole test
suite into one bucket and start rejecting requests well before the suite
finishes. This is a standard env-driven settings toggle, not test-specific
code branching - see `docs/05-RTM.md`'s Phase 18 checklist for the
`docker compose run` invocation this requires.
"""
import asyncio
from dataclasses import dataclass

import redis.asyncio as aioredis
from starlette.requests import Request

from ..config import settings

# Keyed by event loop id, not a single module-level client: an
# `aioredis.Redis` connection pool is bound to the event loop it was
# created on, and reusing it from a *different* loop raises "Event loop is
# closed" (silently swallowed by the fail-open except below, which made
# this look like sporadic double-counting until traced live). One stable
# uvicorn process has exactly one loop for its lifetime, so this is just a
# single cached client in production; it only creates more than one when
# something (a test harness recreating loops per call) actually changes
# loops underneath it.
_redis_clients: dict[int, aioredis.Redis] = {}


def _get_client() -> aioredis.Redis:
    loop_id = id(asyncio.get_running_loop())
    client = _redis_clients.get(loop_id)
    if client is None:
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        _redis_clients[loop_id] = client
    return client


@dataclass
class RateLimitRule:
    limit: int
    window_seconds: int = 60


def _rule_for(path: str, method: str) -> RateLimitRule:
    if path == "/api/v1/auth/login" and method == "POST":
        return RateLimitRule(limit=settings.rate_limit_login_per_minute)
    if path.startswith("/api/v1/harvest/trace/"):
        return RateLimitRule(limit=settings.rate_limit_public_per_minute)
    return RateLimitRule(limit=settings.rate_limit_default_per_minute)


def _client_key(request: Request) -> str:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        # Coarse per-token bucket (not decoded/verified - this is abuse
        # protection, not authorization) so one shared NAT/proxy IP can't
        # exhaust the budget for every distinct authenticated user behind it.
        return f"token:{auth_header[7:][:64]}"
    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


async def check_rate_limit(request: Request) -> tuple[bool, RateLimitRule, int]:
    """Returns (allowed, rule, retry_after_seconds)."""
    if not settings.rate_limit_enabled:
        return True, RateLimitRule(limit=0), 0

    rule = _rule_for(request.url.path, request.method)
    key = f"ratelimit:{_client_key(request)}:{request.url.path}:{request.method}"
    try:
        client = _get_client()
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, rule.window_seconds)
        if count > rule.limit:
            ttl = await client.ttl(key)
            return False, rule, max(ttl, 1)
        return True, rule, 0
    except Exception:
        # Redis unavailable - fail open (NFR-004).
        return True, rule, 0
