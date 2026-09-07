from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine
from .routers import models as models_router
from .routers import equipment as equipment_router
from .routers import dashboard as dashboard_router
from .config import settings

Base.metadata.create_all(bind=engine)

app = FastAPI(title="IFC Digital Twin API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(models_router.router)
app.include_router(equipment_router.router)
app.include_router(dashboard_router.router)


@app.get("/api/status")
def status():
    return {"status": "ok"}
