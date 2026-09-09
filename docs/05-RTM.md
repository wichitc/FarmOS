# 05 — Requirement Traceability Matrix, Risks, Assumptions, Open Decisions

**Document status:** Draft for internal review · Phase 0 · v0.1
**Related:** [01-VISION.md](01-VISION.md) · [02-SCOPE.md](02-SCOPE.md) · [03-BRD.md](03-BRD.md) · [04-SRS.md](04-SRS.md)

---

## 1. Requirement Traceability Matrix (module level)

Maps each requirement block to its target SDLC phase (per the platform brief's §52 phase plan), current codebase maturity (from [00-EXISTING-CODEBASE-ANALYSIS.md](00-EXISTING-CODEBASE-ANALYSIS.md)), and MVP status.

| Requirement block | Doc | Target phase | Current maturity | In MVP? |
|---|---|---|---|---|
| FR-PLT (Platform Foundation) | BRD §1 | Phase 3 | 🟢 implemented (see Phase 3 checklist below) | Yes |
| FR-FARM (Farm & Crop Domain) | BRD §2 | Phase 4 | 🟢 implemented (see Phase 4 checklist below) | Yes |
| FR-GIS / GIS (GIS & Spatial) | BRD §3, SRS §2 | Phase 5 | 🟢 backend implemented (see Phase 5 checklist below); map client pending frontend rewrite | Partial (basic map only) |
| FR-TWIN / TWIN (Digital Twin & 3D) | BRD §4, SRS §1 | Phase 6 | 🟡 backend Digital Twin Core implemented (see Phase 6 checklist below); IFC viewer is still the only 3D piece — Next.js/Cesium frontend work explicitly deferred | Yes |
| FR-IOT / IOT (IoT Platform) | BRD §5, SRS §3 | Phase 7 | 🟢 implemented (see Phase 7 checklist below) | Yes (simulator-driven) |
| FR-IRR / FR-FERT (Irrigation & Fertigation) | BRD §6 | Phase 8 | ⚪ not started | Yes (manual-approval mode) |
| FR-CCTV / VIS (Vision AI) | BRD §7, SRS §5 | Phase 9 | ⚪ not started | No |
| FR-DRONE (Drone) | BRD §8 | Phase 9 (adjacent) | ⚪ not started | No |
| FR-HEALTH (Crop Health/Disease) | BRD §9 | Phase 10 | ⚪ not started | No |
| FR-YIELD / FR-HARV (Yield & Harvest) | BRD §10 | Phase 11 | ⚪ not started | No |
| FR-WORK (Farm Work Management) | BRD §11 | Phase 3–4 (cross-cutting) / Phase 17 (mobile) | ⚪ not started | Partial (backlog) |
| FR-ASSET (Asset & Machinery) | BRD §12 | Phase 12 | 🟢 seed exists (Equipment table, 10 types) | Yes (carried from MVP-adjacent Phase 6) |
| FR-MNT / FR-PDM (Maintenance) | BRD §13 | Phase 12 | 🟡 rule-based health score exists, no WorkOrder | Partial |
| FR-INV / FR-PROC (Inventory & Procurement) | BRD §14 | Phase 13 | ⚪ not started | No |
| FR-ACC / FR-PROF (Farm Accounting) | BRD §15 | Phase 14 | ⚪ not started | No |
| FR-SALES (Sales & Customer) | BRD §16 | Phase 14 (adjacent) | ⚪ not started | No |
| FR-AIML / FR-COPILOT / FR-AGENT (AI Platform) | BRD §17, SRS §4 | Phase 15 | 🟡 health.py is a rule-based placeholder for the ML contract | Partial (rule-engine placeholder only) |
| FR-ALERT (Alerts) | BRD §18 | Phase 7 (with IoT) | 🟢 implemented (ack/resolve; escalation/SLA deferred, see Phase 7 checklist) | Yes |
| FR-WX (Weather) | BRD §19 | Phase 8 (with Irrigation) | ⚪ not started | Yes |
| FR-DASH (Command Center) | BRD §20 | Phase 16 | 🟡 fleet health dashboard exists, not configurable | Yes (minimal) |
| FR-MOB (Mobile/PWA) | BRD §21 | Phase 17 | ⚪ not started | No (post-MVP) |
| SEC / DATA / DEP / NFR (cross-cutting) | SRS §7,§10,§12,§11 | Phase 3 (foundation) + Phase 18 (hardening) | ⚪ mostly not started (see risk R-01..R-05) | Yes (baseline security/data hygiene is MVP-blocking even if full hardening isn't) |

## 2. Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R-01 | No authentication/authorization exists today; if Phase 3 IAM slips, later phases get built on an insecure foundation that's expensive to retrofit | Medium | High | Treat FR-PLT-002/003/004 and SEC-001..003 as hard blockers before any non-localhost deployment; do not sequence farm/crop feature work ahead of foundation IAM |
| R-02 | The `Equipment` table's tree/asset conflation (string-prefix hack) becomes entrenched if agronomy fields get bolted onto it before the Phase-6 twin remodel happens | Medium | High | Schedule the `Equipment` → `DigitalTwin`/`TwinType` split explicitly as a Phase 6 task, before Phase 9–11 (Vision AI, Health, Yield) add fields that would otherwise land on the wrong table |
| R-03 | No database migrations tool — concurrent schema work by multiple contributors on `create_all()` risks silent data loss or drift between environments | High (given current absence) | High | Adopt Alembic in the very first Phase-3 commit, before any other schema change |
| R-04 | Vision AI / disease-detection false positives, if not gated by the human-review workflow (FR-CCTV-004), could trigger unnecessary/harmful chemical treatments | Low (mitigated by design) | High | Enforce VIS-002 and BR-002/BR-003 in the platform's shared agent-governance layer (AI-004), not per-feature, so no future module can bypass the review gate by omission |
| R-05 | Edge/offline sync conflict resolution (mobile PWA, edge gateway) is architecturally hard and easy to under-scope | Medium | Medium | Design conflict resolution rules explicitly in Phase 7/17 architecture docs before implementation, with test cases for concurrent edits from field + office |
| R-06 | Multi-tenancy retrofit after farm/crop data model is built single-tenant would be a breaking migration | Medium | High | `tenant_id` on every table from the first Phase-3/4 migration, even while only one tenant exists in practice |
| R-07 | LLM-provider lock-in if a specific SDK is called directly from business logic | Low | Medium | Enforce AI-003's provider-abstraction interface from the first AI integration, reviewed in code review |
| R-08 | Scope described in the master platform brief (60+ sections) is large enough that incremental delivery could stall without a firm MVP boundary | Medium | Medium | Hold the line on the MVP boundary defined in [02-SCOPE.md §6](02-SCOPE.md); treat everything else as explicitly sequenced backlog, not "also needed for v1" |

## 3. Assumptions

| ID | Assumption | Rationale |
|---|---|---|
| A-01 | This repository (`DurianOS`) becomes `apps/web` + `services/digital-twin` (and possibly `services/ai` for the health-score placeholder) under the target monorepo layout, rather than being discarded and rebuilt from zero | The existing IFC viewer and health-score contract are working, demonstrably-useful seeds (see [00-EXISTING-CODEBASE-ANALYSIS.md §4](00-EXISTING-CODEBASE-ANALYSIS.md)) |
| A-02 | Initial deployment target is on-premise or single-region cloud for one pilot organization, not immediately multi-region SaaS | No stated requirement for immediate multi-tenant commercial launch; multi-tenancy is architected for but not the first production load |
| A-03 | Real IoT hardware (soil/weather sensors, pump controllers) is not yet procured/connected; Phase 7 IoT work proceeds against the device simulator (FR-IOT-005) until hardware arrives | No hardware inventory or vendor selection has been provided |
| A-04 | A corporate ERP for General Ledger accounting may or may not already exist for the pilot tenant; the accounting module is built as management-accounting-plus-integration-API rather than a GL replacement, per FIN-003 | Master brief explicitly directs this rather than duplicating GL functionality |
| A-05 | "Enterprise-grade" security posture (SEC-001..008) is required before production go-live but not before internal dev/demo use of Phase 3–6 | Standard staged-hardening practice; avoids gold-plating early throwaway prototypes while still tracking the requirement |
| A-06 | Thai is the primary operational language; English is the secondary/admin language | Stated in the brief and evidenced by existing Thai strings already in this repo's UI and health engine |

## 4. Open architecture decisions — resolved in Phase 1

All ten were resolved as ADRs during Phase 1; see [11-ADR.md](11-ADR.md) for full Context/Decision/Alternatives/Consequences on each.

| # | Decision needed | Resolution | ADR |
|---|---|---|---|
| 1 | Primary relational database | PostgreSQL + PostGIS | [ADR-001](11-ADR.md) |
| 2 | Time-series store | TimescaleDB | [ADR-002](11-ADR.md) |
| 3 | Event/message bus | MQTT (device layer) + NATS (internal events) | [ADR-003](11-ADR.md), [ADR-010](11-ADR.md) |
| 4 | Multi-tenancy isolation strategy | Row-level security with `tenant_id` (not schema/database-per-tenant) | [ADR-007](11-ADR.md) |
| 5 | 3D/GIS rendering split | IFC (web-ifc-viewer/Three.js) for built/mechanical structures; CesiumJS/3D Tiles for orchard/terrain; composited in one scene | [ADR-005](11-ADR.md), [ADR-006](11-ADR.md) |
| 6 | LLM provider default | Ollama (local) default for on-prem; OpenAI-compatible hosted endpoint selectable per tenant | [ADR-011](11-ADR.md) |
| 7 | Object storage | S3-compatible abstraction, MinIO for on-prem/local (see [08-DATA-ARCHITECTURE.md §1](08-DATA-ARCHITECTURE.md)) | referenced in [08-DATA-ARCHITECTURE.md](08-DATA-ARCHITECTURE.md) |
| 8 | Frontend framework migration path | Incremental strangler-fig migration to Next.js/React/TS, not a rewrite | [ADR-012](11-ADR.md) |
| 9 | Edge gateway runtime | Containerized stack on a farm-site mini-PC/gateway device; sizing (vs. k3s) deferred to Phase 7 once device counts are known | [ADR-009](11-ADR.md) |
| 10 | Mobile PWA offline conflict policy | Field-wins for task-execution fields; explicit manual merge for financial/inventory-quantity fields | [ADR-013](11-ADR.md) |

---

## Phase 0 completion checklist

- [x] Vision, business goals, stakeholders, personas, glossary — [01-VISION.md](01-VISION.md)
- [x] Scope, out-of-scope, functional modules, business capability map, MVP boundary — [02-SCOPE.md](02-SCOPE.md)
- [x] Functional requirements (21 module groups, ~120 FRs) with IDs and priority — [03-BRD.md](03-BRD.md)
- [x] Business rules (8 cross-cutting rules) — [03-BRD.md §22](03-BRD.md)
- [x] Non-functional requirements + Digital Twin / GIS / IoT / AI / Vision AI / Accounting / Security / Integration / Reporting / Data / Deployment requirement sections — [04-SRS.md](04-SRS.md)
- [x] Risks, assumptions, open architecture decisions — this document
- [x] Requirement traceability matrix (module → phase → maturity → MVP status) — this document §1
- [ ] Stakeholder review/sign-off — **pending, human step, not something this document set can self-certify**

## Phase 1 completion checklist

- [x] Context diagram — [06-ARCHITECTURE.md §2](06-ARCHITECTURE.md)
- [x] Container diagram — [06-ARCHITECTURE.md §3](06-ARCHITECTURE.md)
- [x] Component diagram (representative service) — [06-ARCHITECTURE.md §4](06-ARCHITECTURE.md)
- [x] Deployment diagram — [06-ARCHITECTURE.md §5](06-ARCHITECTURE.md)
- [x] Domain model / bounded contexts / context map / event catalog — [07-DOMAIN-MODEL.md](07-DOMAIN-MODEL.md)
- [x] Data architecture (store selection, data flow, classification/retention, conceptual ERD) — [08-DATA-ARCHITECTURE.md](08-DATA-ARCHITECTURE.md)
- [x] Security architecture (zero trust, IAM, RBAC+ABAC, multi-tenancy, network zones, AI governance gateway, audit, secrets) — [09-SECURITY-ARCHITECTURE.md](09-SECURITY-ARCHITECTURE.md)
- [x] Integration architecture (API standards, event catalog governance, external integration table) — [10-INTEGRATION-ARCHITECTURE.md](10-INTEGRATION-ARCHITECTURE.md)
- [x] 13 ADRs covering all 10 Phase-0 open decisions plus 3 additional decisions surfaced during Phase 1 (twin graph model, IFC/3D-Tiles boundary rule, frontend migration path) — [11-ADR.md](11-ADR.md)
- [ ] Stakeholder review/sign-off — **pending, human step**

No business-feature code is written against this architecture until sign-off, per the platform brief's Phase 1 gate ("No business feature coding until approved architecture documents exist").

## Phase 2 completion checklist

- [x] Design system foundations (tokens, status/band convention) — [12-UX-UI.md §1](12-UX-UI.md)
- [x] Navigation shell — [12-UX-UI.md §2](12-UX-UI.md)
- [x] Sitemap (desktop + reduced mobile PWA sitemap) — [12-UX-UI.md §3](12-UX-UI.md)
- [x] Core UI component inventory (carried-forward vs. new) — [12-UX-UI.md §4](12-UX-UI.md)
- [x] 4 key user journeys mapped to personas — [12-UX-UI.md §5](12-UX-UI.md)
- [x] Wireframe specs for all 15 pages (Dashboard, Farm Map, 3D Twin, Trees, Sensors, Cameras, Irrigation, Disease, Harvest, Assets, Maintenance, Inventory, Finance, Admin, Mobile PWA) with API source and requirement refs — [12-UX-UI.md §6](12-UX-UI.md)
- [x] Responsive behavior rules — [12-UX-UI.md §7](12-UX-UI.md)
- [x] UI states (loading/empty/error/permission-denied/offline/stale) — [12-UX-UI.md §8](12-UX-UI.md)
- [x] Accessibility & localization — [12-UX-UI.md §9](12-UX-UI.md)
- [ ] Stakeholder review/sign-off — **pending, human step**

## Phase 3 completion checklist (Platform Foundation)

- [x] Repo/dev-stack: `docker-compose.yml` (Postgres+PostGIS+TimescaleDB, Redis, MQTT, MinIO, NATS, backend), `backend/Dockerfile` — closes DEP-001
- [x] Alembic migrations replace `Base.metadata.create_all()` entirely — closes Risk R-03 (`backend/alembic/versions/0001..0003`)
- [x] Tenant/Identity: `Tenant`, `Organization`, `User` with tenant-scoped, RLS-enforced isolation — [backend/app/foundation/models.py](../backend/app/foundation/models.py), [ADR-007](11-ADR.md)
- [x] Auth: tenant-scoped login (slug+email+password), JWT access/refresh, Argon2 password hashing — `backend/app/core/security.py`, `backend/app/routers/v1/auth.py` — FR-PLT-002, SEC-001
- [x] RBAC + ABAC: `Role`/`Permission`/`RolePermission`/`UserRoleAssignment` (scope_type/scope_id), 10 system roles seeded per tenant matching the personas in [01-VISION.md §4](01-VISION.md) — FR-PLT-003/004
- [x] Audit: append-only `AuditEntry`, written in the same transaction as every state change — `backend/app/foundation/audit.py` — FR-PLT-007, BR-004
- [x] Master data: `Crop`/`Variety` (tenant-scoped, versioned) — seed of the Crop Configuration Engine — FR-FARM-003
- [x] Configuration: tenant-scoped key/value `TenantConfig` — FR-PLT-010
- [x] Workflow/approval engine: generic `WorkflowDefinition`/`WorkflowInstance`/`WorkflowStepEvent`, condition-gated multi-step approval, role-based approver enforcement — `backend/app/foundation/workflow_engine.py` — FR-PLT-005/006
- [x] Notification: in-app `Notification` + `NotificationSender` interface (Email/LINE stubbed as documented integration points, not wired) — FR-PLT-008
- [x] **Row-level tenant isolation actually verified against a real Postgres**, not assumed — `backend/tests/test_tenant_isolation.py`; caught and fixed two real bugs in the process (superuser bypassing RLS; `SET LOCAL`/`expire_on_commit` transaction-boundary interaction) — see commit history for details
- [x] 15 automated tests (auth, RBAC, audit, workflow, tenant isolation) passing against a live containerized Postgres — `backend/tests/`
- [x] Legacy `models`/`equipment`/`dashboard` endpoints left untouched and still verified working (`/api/models` smoke-tested) — tenant/twin migration explicitly deferred to Phase 4/6, not silently dropped
- [ ] Stakeholder review/sign-off — **pending, human step**

**Known follow-ups carried into Phase 4/6** (not gaps in this phase's own scope): legacy equipment/model endpoints remain unauthenticated and outside RLS until they migrate onto the `DigitalTwin` model (ADR-004); `EmailNotificationSender`/`LineNotificationSender` are interface stubs with no real provider wired; ~~ABAC farm/plot-scope enforcement has no farm/plot entities to test against yet (Phase 4)~~ — closed by Phase 4, see below.

## Phase 4 completion checklist (Farm & Crop Domain)

- [x] Spatial/organizational hierarchy `Farm → Zone → Plot → Block → Row → Tree` — `backend/app/farm/models.py`, migration `backend/alembic/versions/0004_farm_crop.py` — FR-FARM-001
- [x] Twin ID (FR-FARM-002): `Tree.id` is the immutable surrogate now, `Tree.code` the mutable human-facing code (auto-composed `{farm.code}-{species}-{block.code}-{row.code}-T{seq}`, overridable) — formal reconciliation onto `DigitalTwin.id` is a named Phase 6 task per [08-DATA-ARCHITECTURE.md §6](08-DATA-ARCHITECTURE.md), not done here
- [x] Season as a first-class entity, scoped to Farm — `backend/app/farm/models.py::Season` — FR-FARM-004
- [x] Per-tree agronomic fields (crop, variety, planting date, rootstock, height, canopy, trunk diameter, growth stage, GPS) — FR-FARM-005
- [x] Bulk tree creation: JSON bulk-create, CSV import, and grid-spacing generation — `POST /api/v1/farm/rows/{row_id}/trees/{bulk,import-csv,generate-grid}` — FR-FARM-006
- [x] Append-only per-tree event history (`TreeEvent`) as the FR-FARM-007 linkage point until Irrigation/Health/Yield/Finance land their own tables in Phases 8-14
- [x] RBAC: `farm.*`/`tree.*`/`season.*` permissions added to the catalog and granted to the relevant system roles (`farm_owner`, `farm_manager`, `agronomist`, `field_worker`, `viewer`) — `backend/app/foundation/rbac_catalog.py`
- [x] ABAC farm-scope enforcement actually wired and tested against real `Farm` rows (`assert_farm_scope` in `backend/app/core/deps.py`) — closes the Phase-3 follow-up above
- [x] Tenant RLS extended to all 8 new tables, same `tenant_isolation` policy pattern as Phase 3
- [x] Soft-delete on `Tree` (`deleted_at`) per [08-DATA-ARCHITECTURE.md §4](08-DATA-ARCHITECTURE.md)
- [x] Automated tests (`backend/tests/test_farm.py`): full hierarchy CRUD, tree code generation, bulk/CSV/grid import, soft-delete, tree events, farm-scoped ABAC (positive + negative)
- [ ] Stakeholder review/sign-off — **pending, human step**

**Known follow-ups carried into Phase 5/6**: ~~GPS is plain `lat`/`lng` floats, not PostGIS geometry — polygons, spatial queries, and geodesic grid placement are Phase 5 (GIS) work~~ — closed by Phase 5, see below; `Tree.digital_twin_id` FK onto a generic `DigitalTwin` core table is still Phase 6; list-level endpoints (`GET /farms`, `GET /trees` under a row) are tenant-wide-permission-gated only, not filtered per-farm ABAC scope — acceptable since every single-resource read/write already enforces `assert_farm_scope`, but a farm-scoped user will see 200 on a list call before individual scope checks apply if they drill into a farm they don't hold; revisit if this becomes a real multi-manager-per-tenant deployment concern.

## Phase 5 completion checklist (GIS & Spatial)

- [x] PostGIS enabled and geometry columns added to the Phase-4 hierarchy: `boundary` (Polygon) on `Farm`/`Zone`/`Plot`/`Block`, `centerline` (LineString) on `Row`, `location` (Point) on `Tree` (kept in sync with the existing `lat`/`lng` floats, which remain the public API's source of truth) — `backend/app/farm/models.py`, migration `backend/alembic/versions/0005_gis.py` — GIS-001
- [x] Draw/edit polygon/line/point via GeoJSON: `PATCH .../{farm,zone,plot,block}/boundary` and `.../rows/{row_id}/centerline` in `backend/app/routers/v1/farm.py`, all audited — FR-GIS-002, GIS-003
- [x] Infrastructure layer entity `MapFeature` (road/drain/pond/pipe/pump/valve/cctv/sensor/building/other) with full CRUD — `backend/app/gis/models.py`, `backend/app/routers/v1/gis.py` — FR-GIS-001. Same "shape now, formalize later" placeholder pattern as `TreeEvent` (Phase 4), ahead of the generic `DigitalTwin`/`TwinType` graph in Phase 6
- [x] GeoJSON import/export: `GET/POST /api/v1/gis/farms/{farm_id}/{export,import}` — FR-GIS-003 (GeoJSON only; KML/Shapefile deferred, see below)
- [x] Layer manager catalog (`GET /api/v1/gis/farms/{farm_id}/layers`, counts per layer type) and a stateless ad-hoc measure tool (`POST /api/v1/gis/measure`, area or length via real PostGIS geodesic calculation) — FR-GIS-005
- [x] Persisted boundaries auto-compute geodesic area in hectares (`ST_Area(boundary::geography)`), overwriting the Phase-4 manually-entered value — FR-GIS-005
- [x] Bulk tree placement upgraded from Phase 4's placeholder degree-offset math to real meter-spaced geodesic placement (`ST_Project`) along the row's centerline bearing (or north, if none drawn yet), clipped to the plot's boundary when one exists — `generate_tree_grid` in `backend/app/routers/v1/farm.py` — FR-GIS-006
- [x] Spatial query `GET /api/v1/gis/trees/nearby` (`ST_DWithin`/`ST_Distance` on `Tree.location`) — FR-GIS-007
- [x] RBAC: reuses the existing `farm.view`/`farm.manage` permissions and `assert_farm_scope` ABAC helper from Phase 4 — no new permissions needed
- [x] Automated tests (`backend/tests/test_gis.py`): boundary set + audited + area computed, zone/plot/block boundary and row centerline, map feature CRUD, GeoJSON export/import round-trip, ad-hoc measure (area + length), nearby-trees radius search, boundary-clipped grid generation (both the success and the "doesn't fit" 422 path)
- [ ] Stakeholder review/sign-off — **pending, human step**

**Known follow-ups carried into the frontend-rewrite phase**: the MapLibre GL map client SRS GIS-002 calls for (layer manager UI, interactive draw/edit with snapping, raster orthophoto overlay) is not built — this phase is backend-only, same precedent as Phases 3-4, since the frontend is still the legacy vanilla-JS app pending its own migration (`docs/00-EXISTING-CODEBASE-ANALYSIS.md` §4); the backend endpoints above (`/api/v1/gis/*`, `PATCH .../boundary`) are exactly what that future client will call. KML/Shapefile import (FR-GIS-003) is deferred — both need `fiona`/GDAL, a much heavier container dependency than GeoJSON's zero-extra-deps path; add if/when a real farm survey delivers one of those formats. Layer-visibility persistence (which layers a user last had toggled on) is frontend/UI state, not modeled here.

## Phase 6 (backend slice) completion checklist (Digital Twin Core)

**Scope note**: `docs/11-ADR.md` ADR-012 and ADR-005/006 scope Phase 6 as full-stack (stand up the Next.js/React/TS frontend per the strangler-fig plan, integrate CesiumJS for orchard-scale 3D). The user explicitly chose a backend-only pass for now — this checklist covers only the generic Digital Twin data model and the legacy-Equipment migration path. The frontend rewrite and CesiumJS integration remain open, tracked below, not silently dropped.

- [x] Generic model per ADR-004/TWIN-001: `TwinType`, `DigitalTwin`, `TwinRelationship`, `TwinProperty`, `TwinEvent`, `TwinTelemetry` — `backend/app/twins/models.py`, migration `backend/alembic/versions/0006_digital_twin_core.py`. `TwinProperty` (not a fixed-column `Asset` table) is what lets a new asset/tree category be added as configuration, not a schema change
- [x] Twin ID immutability (BR-006): `DigitalTwin.id` assigned once, never reassigned; `display_code` is the separate mutable, user-facing label
- [x] Temporal, directed twin relationships (`TwinRelationship.valid_from`/`valid_to`) — TWIN-003
- [x] Append-only event timeline (`TwinEvent`) and telemetry (`TwinTelemetry`, plain table for now — TimescaleDB hypertable conversion deferred to Phase 7's real ingestion volume) — TWIN-002/004
- [x] "Twin inspector" aggregate endpoint (`GET /api/v1/twins/{id}`: current state + properties + recent events + latest telemetry per metric in one shape) — directly satisfies TWIN-002's "one consistent API shape regardless of twin type"
- [x] `Tree.digital_twin_id` (nullable FK) added and wired into every tree-creation path in `backend/app/routers/v1/farm.py` (`create_tree`, `bulk_create_trees`, `import_trees_csv`, `generate_tree_grid`) via a shared `_build_tree` helper — closes the Phase 4 follow-up docs/08-DATA-ARCHITECTURE.md §6 named for this phase. Tree soft-delete and growth-stage/code updates also sync the linked twin's `deleted_at`/`status`/`current_state`/`display_code`
- [x] `backend/app/scripts/backfill_tree_twins.py` — one-off backfill for any `Tree` predating this migration
- [x] `backend/app/scripts/migrate_equipment_to_twins.py` — migrates legacy (unauthenticated) `Equipment` rows into `DigitalTwin`+`TwinProperty` per SRS TWIN-005, deliberately excluding `tree_*`-prefixed rows (superseded by Phase 4's real `Tree` entities, not duplicated)
- [x] RBAC: `twin.view`/`twin.manage`/`twin.telemetry.write` added to `backend/app/foundation/rbac_catalog.py`, granted to `farm_owner`/`farm_manager`/`agronomist`/`field_worker`/`viewer` (view-oriented) and `maintenance_engineer` (manage — its first real permissions, a natural fit for asset-category twins); farm-scoped ABAC reuses `assert_farm_scope` via a nullable `DigitalTwin.farm_id` (mirrors legacy `Equipment.model_id IS NULL` = unscoped)
- [x] Legacy `models`/`equipment`/`dashboard` endpoints left untouched and still working — cutting them over to auth/RLS would break the existing vanilla-JS frontend's one working demo with no login flow to replace it; real cutover happens with the frontend rewrite below, not attempted here
- [x] Automated tests (`backend/tests/test_twins.py`): TwinType/DigitalTwin CRUD, relationship both-directions query, property upsert (overwrite not duplicate), event append-only, telemetry + latest-per-metric, the inspector aggregate, tree-creation auto-linking a digital twin, and farm-scoped ABAC (positive + negative)
- [ ] Stakeholder review/sign-off — **pending, human step**

**Deferred, tracked explicitly (not silent gaps)**:
- `TwinCommand` and `TwinDocument` (named in TWIN-001's generic-model roster but with no dedicated `TWIN-00x` requirement of their own) — `TwinCommand` belongs with Phase 7's IoT actuation, `TwinDocument` has no consumer yet
- `TwinAlert` — alerting is Phase 7's `FR-ALERT`; a twin's "alarm state" (FR-TWIN-002) can read `TwinEvent`/`current_state` until then
- **The Next.js/React/TS frontend shell (ADR-012) and CesiumJS orchard-scale 3D integration (ADR-005/006)** — full-stack work explicitly out of scope for this pass by user decision; this is the largest remaining piece of Phase 6 as originally scoped and should be picked up as its own dedicated effort, not folded into Phase 7
- List-level `GET /api/v1/twins` (no `farm_id` filter) is tenant-wide-permission-gated only, same documented limitation as the Phase 4/5 list endpoints
- `POST /{twin_id}/relationships` only ABAC-checks the `from` twin, not the `to` twin — a minor existence-oracle gap (a user could learn a `to_twin_id` exists via a 404-vs-201 response even without visibility into its farm), not a data-exposure one

## Phase 7 completion checklist (IoT Platform + Alerts)

- [x] Device/gateway registry (FR-IOT-001): `IotDevice` as a thin extension row on top of a `DigitalTwin` (ADR-004 — a Gateway is just an `IotDevice` with `protocol='gateway'` that other devices point `gateway_id` at) — `backend/app/iot/models.py`, migration `backend/alembic/versions/0007_iot_platform.py`
- [x] Full ingestion pipeline per SRS IOT-001 (`Device → Gateway → MQTT → Ingestion service → Validation → Transformation → TimescaleDB → Rules Engine → Alert/Twin update`): `backend/app/scripts/mqtt_ingestion_worker.py` (new `iot-ingestion` docker-compose service) subscribes to `tenants/+/devices/+/telemetry` and calls the testable core in `backend/app/iot/ingestion.py::process_reading` for validate → store → twin-state update → rule evaluation → alert
- [x] `twin_telemetry` (Phase 6 placeholder) is now a real TimescaleDB hypertable with a 90-day raw-retention policy, closing that phase's explicit deferral — ADR-002
- [x] Duplicate-telemetry tolerance (IOT-003): `(twin_id, metric, recorded_at)` unique constraint + `ON CONFLICT DO NOTHING`, verified as a no-op rather than an error
- [x] Sensor-offline detection as a first-class, idempotent alert condition (FR-IOT-004): `check_offline_devices`, run periodically inside the ingestion worker
- [x] Threshold rules engine (FR-IOT-004/IOT-004), tenant/farm-configurable via `TwinType`+`metric`: `backend/app/iot/models.py::Rule`
- [x] Alerts (FR-ALERT-001): generic `entity_type`/`entity_id`, severity, open/acknowledged/resolved lifecycle with actor+timestamp per transition — `backend/app/routers/v1/iot.py`
- [x] Device simulator (FR-IOT-005, itself an MVP-blocking dev/test enabler): `backend/app/scripts/device_simulator.py`
- [x] RBAC: `iot.device.{view,manage}`/`iot.rule.{view,manage}`/`alert.{view,manage}` added and granted per role (farm_owner/farm_manager/maintenance_engineer manage; agronomist/viewer view; field_worker gets `alert.manage` for acknowledge-in-the-field)
- [x] Automated tests (`backend/tests/test_iot.py`): one-time secret reveal, happy-path ingestion updating twin state, wrong-secret rejection with no side effects, duplicate-reading no-op, rule breach → alert (and no duplicate open alert on a sustained breach) → acknowledge → resolve, offline detection + idempotency, farm-scoped ABAC on device endpoints
- [ ] Stakeholder review/sign-off — **pending, human step**

**Deferred, tracked explicitly (not silent gaps)**:
- **SEC-006 (per-device mTLS/broker ACLs)**: Mosquitto stays `allow_anonymous true` (dev default, `infrastructure/mosquitto/mosquitto.conf`); this phase's auth boundary is an application-level per-device secret (`IotDevice.hashed_secret`, checked in `process_reading`) rather than broker-enforced TLS client certs. Real broker hardening is Phase 18 per the RTM's own phase mapping for cross-cutting security work
- **FR-ALERT-002 escalation/SLA timing** — ack/assign/resolve is built; SLA timers/auto-escalation need a scheduler this repo doesn't have yet
- **Modbus/LoRaWAN/HTTP/WebSocket ingestion (FR-IOT-002)** — only the MQTT path is wired end-to-end; ADR-003 already assigns non-MQTT protocols to be bridged at the Edge Gateway (Phase 9/17 territory), not spoken directly by the core platform
- **TimescaleDB continuous aggregates** (hourly/daily telemetry rollups) — not built; no dashboard consumes them yet
- **Device calibration records (FR-IOT-006, S-priority)** — not built this pass
