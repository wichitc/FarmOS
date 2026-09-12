import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .core.rate_limit import check_rate_limit
from .routers import dashboard as dashboard_router
from .routers import equipment as equipment_router
from .routers import models as models_router
from .routers.v1 import ai as ai_router_v1
from .routers.v1 import asset as asset_router_v1
from .routers.v1 import accounting as accounting_router_v1
from .routers.v1 import audit as audit_router_v1
from .routers.v1 import auth as auth_router_v1
from .routers.v1 import config as config_router_v1
from .routers.v1 import crophealth as crophealth_router_v1
from .routers.v1 import dashboard as dashboard_router_v1
from .routers.v1 import farm as farm_router_v1
from .routers.v1 import gis as gis_router_v1
from .routers.v1 import harvest as harvest_router_v1
from .routers.v1 import inventory as inventory_router_v1
from .routers.v1 import iot as iot_router_v1
from .routers.v1 import irrigation as irrigation_router_v1
from .routers.v1 import master_data as master_data_router_v1
from .routers.v1 import notifications as notifications_router_v1
from .routers.v1 import roles as roles_router_v1
from .routers.v1 import sales as sales_router_v1
from .routers.v1 import tenants as tenants_router_v1
from .routers.v1 import twins as twins_router_v1
from .routers.v1 import users as users_router_v1
from .routers.v1 import vision as vision_router_v1
from .routers.v1 import weather as weather_router_v1
from .routers.v1 import work as work_router_v1
from .routers.v1 import workflow as workflow_router_v1

# Schema is managed exclusively through Alembic migrations (backend/alembic/)
# from this phase onward, closing Risk R-03 - `Base.metadata.create_all` is
# no longer called anywhere. Run `alembic upgrade head` before starting the
# app (see backend/README or docker-compose's migrate step).

app = FastAPI(title="FruitTwin AI Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Correlation-Id"] = correlation_id
    return response


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """SEC-007: see `core/rate_limit.py`. Builds its own correlation id
    (same fallback logic as `correlation_id_middleware`) rather than
    relying on `request.state.correlation_id` having already been set -
    keeps this middleware correct regardless of the two middlewares'
    relative stack order."""
    allowed, rule, retry_after = await check_rate_limit(request)
    if not allowed:
        correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": 429,
                    "message": f"Rate limit exceeded: {rule.limit} requests per {rule.window_seconds}s",
                    "correlation_id": correlation_id,
                }
            },
            headers={"Retry-After": str(retry_after), "X-Correlation-Id": correlation_id},
        )
    return await call_next(request)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """OWASP-baseline response headers (SEC-007). TLS termination itself
    (SEC-004) is a deployment-layer concern outside this app's code -
    `Strict-Transport-Security` is set unconditionally since it is a no-op
    when a deployment happens to still be plain HTTP, but takes effect the
    moment a reverse proxy in front of it terminates TLS."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    # Standard error envelope per 10-INTEGRATION-ARCHITECTURE.md §2.
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.status_code,
                "message": exc.detail,
                "correlation_id": getattr(request.state, "correlation_id", None),
            }
        },
    )


# Legacy (pre-Phase-3) routers - unauthenticated, single implicit scope.
# Migration onto the twin model + auth/RLS is tracked for Phase 4/6 per
# 08-DATA-ARCHITECTURE.md §6 and 05-RTM.md; not silently left unaddressed.
app.include_router(models_router.router)
app.include_router(equipment_router.router)
app.include_router(dashboard_router.router)

# Platform Foundation (Phase 3) - authenticated, tenant-isolated via RLS.
app.include_router(auth_router_v1.router)
app.include_router(tenants_router_v1.router)
app.include_router(users_router_v1.router)
app.include_router(roles_router_v1.router)
app.include_router(config_router_v1.router)
app.include_router(master_data_router_v1.router)
app.include_router(farm_router_v1.router)
app.include_router(gis_router_v1.router)
app.include_router(twins_router_v1.router)
app.include_router(iot_router_v1.router)
app.include_router(irrigation_router_v1.router)
app.include_router(weather_router_v1.router)
app.include_router(vision_router_v1.router)
app.include_router(crophealth_router_v1.router)
app.include_router(harvest_router_v1.router)
app.include_router(asset_router_v1.router)
app.include_router(inventory_router_v1.router)
app.include_router(accounting_router_v1.router)
app.include_router(sales_router_v1.router)
app.include_router(workflow_router_v1.router)
app.include_router(notifications_router_v1.router)
app.include_router(audit_router_v1.router)
app.include_router(ai_router_v1.router)
app.include_router(dashboard_router_v1.router)
app.include_router(work_router_v1.router)


@app.get("/api/status")
def status():
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    return {"status": "ok"}
