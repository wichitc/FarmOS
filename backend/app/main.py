import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .routers import dashboard as dashboard_router
from .routers import equipment as equipment_router
from .routers import models as models_router
from .routers.v1 import audit as audit_router_v1
from .routers.v1 import auth as auth_router_v1
from .routers.v1 import config as config_router_v1
from .routers.v1 import farm as farm_router_v1
from .routers.v1 import gis as gis_router_v1
from .routers.v1 import master_data as master_data_router_v1
from .routers.v1 import notifications as notifications_router_v1
from .routers.v1 import roles as roles_router_v1
from .routers.v1 import tenants as tenants_router_v1
from .routers.v1 import twins as twins_router_v1
from .routers.v1 import users as users_router_v1
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
app.include_router(workflow_router_v1.router)
app.include_router(notifications_router_v1.router)
app.include_router(audit_router_v1.router)


@app.get("/api/status")
def status():
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    return {"status": "ok"}
