# Backend — dev workflow (Phase 3: Platform Foundation)

## Running the stack

From the repo root:

```bash
docker compose up -d
```

This starts PostgreSQL+TimescaleDB+PostGIS, Redis, MQTT (Mosquitto), MinIO, NATS, and the backend (which runs `alembic upgrade head` automatically before starting uvicorn with `--reload`). The API is at `http://localhost:8000`; `PLAN_ARC.ifc`-style legacy endpoints are unchanged, and the new foundation endpoints are under `/api/v1/*`.

## Two database roles, on purpose

`DATABASE_URL` (superuser, used only by Alembic for DDL) and `APP_DATABASE_URL` (the `durianos_app` role the running application actually connects as) are deliberately different. PostgreSQL never enforces row-level security against a superuser, even with `FORCE ROW LEVEL SECURITY` — if the app ever connects as the migration/owner role, every tenant-isolation guarantee in `alembic/versions/0002_platform_foundation.py` silently stops applying. See `alembic/versions/0003_app_role.py` and `app/config.py`.

## Bootstrapping the first tenant

There is no open "create the first tenant" API endpoint (that would be an unauthenticated privilege-escalation hole). Run once per deployment:

```bash
docker compose exec backend python -m app.scripts.bootstrap <slug> "<org name>" <admin-email> <admin-password> "<admin name>"
```

Every subsequent tenant is provisioned by that bootstrap super admin via `POST /api/v1/tenants`.

## Running tests

Tests hit a real PostgreSQL (RLS/tenant-isolation can't be meaningfully tested against SQLite or mocks):

```bash
docker compose run --rm backend pytest
```

`tests/test_tenant_isolation.py` is the one that actually proves cross-tenant data isolation — if it's ever green against a superuser DB connection, that's a false pass, not a real one (see the note above).

## Migrations

```bash
docker compose run --rm backend alembic revision -m "..." --autogenerate
docker compose run --rm backend alembic upgrade head
```

`Base.metadata.create_all()` is not used anywhere from Phase 3 onward — every schema change goes through Alembic (closes Risk R-03 in `docs/05-RTM.md`).
