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
| FR-IRR / FR-FERT (Irrigation & Fertigation) | BRD §6 | Phase 8 | 🟢 implemented, manual-approval mode (see Phase 8 checklist below) | Yes (manual-approval mode) |
| FR-CCTV / VIS (Vision AI) | BRD §7, SRS §5 | Phase 9 | 🟡 data model + human-review workflow + safety constraints implemented; inference is a stub (see Phase 9 checklist below) | No |
| FR-DRONE (Drone) | BRD §8 | Phase 9 (adjacent) | ⚪ not started (C-priority, deferred — see Phase 9 checklist) | No |
| FR-HEALTH (Crop Health/Disease) | BRD §9 | Phase 10 | 🟢 implemented (see Phase 10 checklist below) | No |
| FR-YIELD / FR-HARV (Yield & Harvest) | BRD §10 | Phase 11 | 🟢 implemented (see Phase 11 checklist below) | No |
| FR-WORK (Farm Work Management) | BRD §11 | Phase 3–4 (cross-cutting) / Phase 17 (mobile) | 🟢 full Request→Plan→Assign→Accept→Execute→Evidence→Complete→Review→Close lifecycle implemented (see Phase 17 checklist below) | Partial (backend complete; FR-WORK-003's offline mobile capture is frontend/PWA work, deferred with FR-MOB) |
| FR-ASSET (Asset & Machinery) | BRD §12 | Phase 12 | 🟢 implemented as asset-category DigitalTwins (see Phase 12 checklist below) | Yes (carried from MVP-adjacent Phase 6) |
| FR-MNT / FR-PDM (Maintenance) | BRD §13 | Phase 12 | 🟢 implemented — health.py rule engine reused, full MaintenanceRequest → WorkOrder lifecycle (see Phase 12 checklist below) | Partial |
| FR-INV / FR-PROC (Inventory & Procurement) | BRD §14 | Phase 13 | 🟢 implemented (see Phase 13 checklist below) | No |
| FR-ACC / FR-PROF (Farm Accounting) | BRD §15 | Phase 14 | 🟢 implemented (see Phase 14 checklist below) | No |
| FR-SALES (Sales & Customer) | BRD §16 | Phase 14 (adjacent) | 🟢 implemented, collapsed pipeline (see Phase 14 checklist below) | No |
| FR-AIML / FR-COPILOT / FR-AGENT (AI Platform) | BRD §17, SRS §4 | Phase 15 | 🟡 Model Registry, Prediction envelope, and the L0–L4 Agent Action Gateway implemented; Copilot answers a fixed set of data-grounded question categories, no live LLM wired yet (see Phase 15 checklist below) | Partial (registry + gateway; Copilot/LLM deferred) |
| FR-ALERT (Alerts) | BRD §18 | Phase 7 (with IoT) | 🟢 implemented (ack/resolve; escalation/SLA deferred, see Phase 7 checklist) | Yes |
| FR-WX (Weather) | BRD §19 | Phase 8 (with Irrigation) | 🟢 data model + ingestion implemented; no real external provider wired (see Phase 8 checklist) | Yes |
| FR-DASH (Command Center) | BRD §20 | Phase 16 | 🟡 authenticated, tenant/farm-scoped fleet health + per-farm widget-rollup API implemented (see Phase 16 checklist below); interactive map/3D viewer and drag-and-drop widget layouts remain frontend work | Yes (minimal, backend data API only) |
| FR-MOB (Mobile/PWA) | BRD §21 | Phase 17 | ⚪ not started (frontend/PWA-only scope; see Phase 17 checklist) | No (post-MVP) |
| SEC / DATA / DEP / NFR (cross-cutting) | SRS §7,§10,§12,§11 | Phase 3 (foundation) + Phase 18 (hardening) | 🟡 SEC-001/002/003 implemented since Phase 3; SEC-007 (rate limiting + OWASP-baseline headers) implemented this phase (see Phase 18 checklist below); most of SEC-004/005/006/008, DATA-002/003, NFR-001..009, and DEP-001..005 remain infra/ops/deployment-time work, not application code (see risk R-01..R-05) | Yes (baseline security/data hygiene is MVP-blocking even if full hardening isn't) |

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

## Phase 8 completion checklist (Irrigation & Fertigation + Weather)

- [x] Water network infrastructure modeled as `DigitalTwin`s (`"water"` added to `TWIN_TYPE_CATEGORIES`, `backend/app/twins/models.py`) connected via the existing `TwinRelationship` graph (`SUPPLIED_BY`/`DRAWS_FROM`, already named in TWIN-003) — FR-IRR-001, no new tables needed per ADR-004
- [x] Approval-before-execution made structural, not configurable (FR-IRR-003/004, docs/09-SECURITY-ARCHITECTURE.md §6's hardcoded L3 floor): `provision_tenant()` (`backend/app/foundation/seed.py`) now auto-seeds an `irrigation_plan` and a `fertigation_plan` `WorkflowDefinition` for every new tenant; a plan can only reach `status="approved"` through `workflow_engine.submit`/`decide` — verified by `test_seeded_approval_workflows_exist_for_new_tenant` and the full submit→approve→execute / submit→reject→blocked lifecycle tests
- [x] `IrrigationPlan`/`IrrigationEvent` (plan-vs-actual, safety-check fields, actor-traceable) and `FertigationPlan`/`FertigationEvent` (down to tree-level granularity per FR-FERT-002) — `backend/app/irrigation/models.py`, migration `backend/alembic/versions/0008_irrigation_fertigation.py`
- [x] Fertilizer master data with N/P/K/Ca/Mg/S composition (FR-FERT-001) — `backend/app/irrigation/models.py::Fertilizer`
- [x] Rule-based recommendation engine (FR-IRR-002/FR-FERT-003), same "indicative defaults, not certified" treatment as `health.py`: `backend/app/irrigation/recommendation.py::recommend_irrigation`/`recommend_fertigation`, pure functions with unit tests, every recommendation carries an explicit `reason` string
- [x] Weather readings, source-tagged and append-only (`station` vs `forecast`) — structurally satisfies FR-WX-001's "never overwrite an observed reading with forecast data" since nothing is ever overwritten; `current_reading()` prefers `station` over `forecast` — `backend/app/weather/`
- [x] RBAC: `irrigation.plan.*`/`fertigation.plan.*`/`fertilizer.*`/`weather.*` granted per role; approval itself reuses the existing `workflow.instance.approve` permission plus a farm-scope check layered in the irrigation router on top of the workflow engine's own (farm-unaware) role check
- [x] Automated tests (`backend/tests/test_irrigation.py`): recommendation-engine unit tests (no DB), full plan lifecycle (create → submit → approve → execute → `IrrigationEvent`), reject path blocks execution, execute blocked unless approved, seeded-workflow-definitions check, fertigation tree-level granularity, weather station-preferred-over-forecast, farm-scoped ABAC
- [ ] Stakeholder review/sign-off — **pending, human step**

**Deferred, tracked explicitly (not silent gaps)**:
- **Scheduled/cron-triggered irrigation** — no scheduler infrastructure yet (same reasoning as Phase 7's alert-SLA deferral); `source="scheduled"` is already a valid enum value on both plan types so this is additive later, not a schema change
- **AI-recommended irrigation/fertigation** — `source="ai_recommended"` likewise reserved; real ET-based/ML modeling replacing `recommendation.py`'s rule-based placeholder is Phase 15 (AI Platform) work
- **Real external weather provider** — no vendor/API key decided; `WeatherProvider` protocol + `StubWeatherProvider` (`backend/app/weather/provider.py`) mark the integration point, mirroring the `NotificationSender` stub pattern from Phase 3
- **Fertilizer stock linkage (FR-FERT-001)** — `Fertilizer.stock_ref` is a free-text placeholder, not a real FK; Inventory doesn't exist until Phase 13
- **FR-IRR-004 safety limits** (max runtime, dry-run protection, pressure check, valve-confirmation, emergency stop) are recorded as a `safety_checks` jsonb bag on `IrrigationEvent` for traceability, not independently enforced by the platform — there is no real actuator/PLC integration yet for the platform to enforce them against

## Phase 9 completion checklist (CCTV & Vision AI — stub scaffold)

**Scope note**: Phase 9 is explicitly marked "not in MVP" in this table, and the actual vision pipeline (FR-CCTV-002) is priority S while only the safety constraints around it (FR-CCTV-004/005) are M. Per an explicit user decision, this phase scaffolds the data model, human-review workflow, and those safety constraints now — with a stub (no-op) inference engine rather than a real vision model, mirroring the `health.py`/`WeatherProvider` "shape now, real integration later" pattern used throughout this project.

- [x] Camera registry (FR-CCTV-001): `Camera` as a `DigitalTwin` extension row (category `"camera"`, already in `TWIN_TYPE_CATEGORIES` since Phase 6) — same shared-kernel pattern as `IotDevice` (Phase 7) — `backend/app/vision/models.py`, migration `backend/alembic/versions/0009_vision_ai.py`
- [x] Vision model catalog (FR-CCTV-002): `VisionModel` configuration rows per use case (tree-health, fruit detection, maturity, disease-symptom, intrusion, worker-safety, vehicle) — not real model artifacts or an inference runtime
- [x] `Detection` records carry every field FR-CCTV-003/VIS-001 requires: model name/version (via `model_id`), timestamp, source frame reference, confidence, detected class, bounding box, source camera, and associated tree/plot
- [x] Human-review workflow (FR-CCTV-004/VIS-002): `validation_status` (`pending`/`confirmed`/`rejected`), reviewer + timestamp + notes recorded, a detection can only be reviewed once
- [x] Hard safety constraint (FR-CCTV-005): confirming a detection has **no code path** that creates a Disease Incident or triggers any treatment — verified by inspection of `_review_detection` in `backend/app/routers/v1/vision.py`, documented as vacuously-but-genuinely satisfied since no auto-treatment path exists anywhere in the platform yet
- [x] Stub inference engine (`backend/app/vision/inference.py::StubVisionInferenceEngine`) — the `VisionInferenceEngine` protocol is the integration point a real model plugs into later; today, detections are entered directly via `POST /api/v1/vision/cameras/{id}/detections` (by a human reviewer or a test harness), the same endpoint a real engine would call
- [x] RBAC: `vision.camera.*`/`vision.model.*`/`vision.detection.*` granted per role (farm_owner/farm_manager/agronomist manage; field_worker can review detections but not manage cameras/models; viewer view-only)
- [x] Automated tests (`backend/tests/test_vision.py`): stub engine returns nothing, camera registration, vision model catalog, detection confirm/reject lifecycle (including "already reviewed" blocked), tree-linked detection, farm-scoped ABAC
- [ ] Stakeholder review/sign-off — **pending, human step**

**Deferred, tracked explicitly (not silent gaps)**:
- **Real vision inference** (any actual ML model, GPU runtime, or vendor API) — no vendor/model decided anywhere in the docs; `StubVisionInferenceEngine` is the marked integration point
- **RTSP/ONVIF stream ingestion and frame capture** — `Camera.stream_url` is stored but nothing connects to it; there is no video pipeline
- **Object-storage frame upload** (VIS-001 requires persisting the source frame) — `Detection.frame_ref` is a placeholder string field; no real MinIO upload path is wired yet (MinIO itself is already in `docker-compose.yml` per DEP-001 but unused by this phase)
- **Configurable per-camera sampling rate/retention (VIS-003)** — not built; moot without a real video pipeline to sample from
- **Disease Incident creation from confirmed detections** — deliberately left to Phase 10 (`FR-HEALTH`), which owns the full Detected→...→Resolved lifecycle and shouldn't have that design pre-empted by a stub phase
- **Drone (FR-DRONE)** — C-priority (lowest), not in MVP, zero infrastructure decided anywhere in the docs; skipped entirely this pass rather than building a placeholder with no real consumer

## Phase 10 completion checklist (Crop Health & Disease)

Not in MVP, but fully buildable with real (non-stub) logic — unlike Phase 9, nothing here needed an undecided vendor/model: the risk engine is rule-based over signals the platform already produces (Phase 8 weather, Phase 9 confirmed detections, incident history), and the approval mechanism is the same workflow engine Phase 8 already wired up.

- [x] Disease/pest master data (`Disease`) — `backend/app/crophealth/models.py`, migration `backend/alembic/versions/0010_crop_health_disease.py`
- [x] Full disease lifecycle per FR-HEALTH-001 (`detected → suspected → inspection_required → confirmed → treatment_planned → treatment_applied → monitoring → resolved`), with transitions validated against an explicit allowed-next-states map (`INCIDENT_ALLOWED_TRANSITIONS`) rather than left unconstrained
- [x] **Closes Phase 9's explicit deferral**: `DiseaseIncident.source_detection_id` links a confirmed Vision AI detection to an incident; the router enforces FR-CCTV-004's requirement that only a `validation_status="confirmed"` detection can be used (verified by `test_incident_requires_confirmed_detection`)
- [x] Treatment Plans (FR-HEALTH-003) reuse the exact approval-gated lifecycle Phase 8 introduced: `provision_tenant()` now also seeds a `treatment_plan` `WorkflowDefinition`, so a plan can only reach `approved` through `workflow_engine` — directly satisfies FR-CCTV-005's cross-reference ("an AI disease diagnosis shall never, by itself, trigger a pesticide/chemical application"), since there is still no code path anywhere in the platform from an AI detection straight to treatment execution
- [x] Approving/executing a `TreatmentPlan` syncs the linked `DiseaseIncident`'s status forward (`treatment_planned` on approval, `treatment_applied` on execution) when that's a legal transition — verified by `test_treatment_plan_full_lifecycle_syncs_incident_status`
- [x] Rule-based disease-risk engine (FR-HEALTH-002/004), same "indicative defaults" treatment as `health.py`/`app.irrigation.recommendation`: `backend/app/crophealth/risk.py::compute_disease_risk`, always returns `evidence` + `confidence` alongside the score, never a bare number. `POST /api/v1/crop-health/farms/{farm_id}/risk` wires it to real data: current weather readings (Phase 8), recent confirmed-incident counts, and recent confirmed Vision AI detection confidence (Phase 9)
- [x] RBAC: `crophealth.disease.*`/`crophealth.incident.*`/`crophealth.treatment.*` granted per role (farm_owner/farm_manager/agronomist manage; field_worker can view+manage treatment execution but not incident diagnosis/lifecycle; viewer view-only)
- [x] Automated tests (`backend/tests/test_crophealth.py`): risk-engine unit tests (no DB), disease master CRUD, incident lifecycle transition validation (valid and rejected), full treatment-plan lifecycle with incident-status sync, reject path blocks execution, seeded-workflow check, confirmed-detection-required check, risk endpoint combining real weather data, farm-scoped ABAC
- [ ] Stakeholder review/sign-off — **pending, human step**

**Deferred, tracked explicitly (not silent gaps)**:
- **`TreatmentPlan.work_task_ref`** is a free-text placeholder, not a real FK — Farm Work Management (`FR-WORK`) doesn't exist as a queryable entity yet (RTM: Phase 17), same treatment as `Fertilizer.stock_ref` for the not-yet-built Inventory module
- **Soil condition** (named in FR-HEALTH-002's signal list) is not modeled anywhere in the platform yet and isn't wired into the risk engine's inputs — there's no soil-sensor/soil-test entity to source it from
- **Real epidemiological/ML risk modeling** replacing `compute_disease_risk`'s placeholder threshold rules is Phase 15 (AI Platform) work behind the same function contract

## Phase 11 completion checklist (Yield & Harvest)

Not in MVP, but — like Phase 10 — fully buildable with real (non-stub) logic: no vendor/model decision was blocking it.

- [x] Fruit lifecycle observations (FR-YIELD-001): `FruitObservation` per tree (`flowering → pollination → fruit_set → fruit_growth → maturity → harvest`) — kept as its own log rather than overloading Phase 4's `Tree.growth_stage`, which has a different (and missing "pollination") stage set — `backend/app/harvest/models.py`, migration `backend/alembic/versions/0011_yield_harvest.py`
- [x] Yield roll-up (FR-YIELD-001's "Tree → Row → Plot → Farm → Crop → Season"): `GET /api/v1/harvest/farms/{farm_id}/yield-summary`, a live aggregation query over `HarvestLot` grouped by plot/season, not a separately maintained rollup table
- [x] Yield forecasts are always a range, never a point number (FR-YIELD-002): `estimate_yield_range` (`backend/app/harvest/estimation.py`) returns `estimated_yield_kg_low`/`_high` + `confidence` + evidence, same "indicative defaults" treatment as `health.py`/`app.irrigation.recommendation`/`app.crophealth.risk`
- [x] `HarvestLot`/`PackingLot` (FR-HARV-001, simplified — see deferral below) carry the traceability chain FR-HARV-002 requires
- [x] **Consumer-facing traceability** (FR-HARV-002): `GET /api/v1/harvest/trace/{tenant_slug}/{qr_code}` is deliberately the platform's first **public, unauthenticated** endpoint — a shopper scanning packaging isn't a logged-in platform user. `tenant_slug` plays the same role it already plays in `POST /api/v1/auth/login`; only traceability-safe fields are exposed (no user IDs, no internal notes/cost data); resolves either a Packing Lot QR (→ its Harvest Lots) or a Harvest Lot QR directly (unpacked sale)
- [x] RBAC: `harvest.observation.*`/`harvest.yield.*`/`harvest.lot.*` granted per role; the trace endpoint intentionally has no permission check at all (see above)
- [x] Automated tests (`backend/tests/test_harvest.py`): yield-estimation unit tests (no DB, including the zero-input edge case), fruit observation lifecycle, yield forecast always a range, full harvest-lot → packing-lot → public trace round trip, direct-harvest-lot-QR trace, unknown-QR and unknown-tenant 404s, yield-summary aggregation, farm-scoped ABAC
- [ ] Stakeholder review/sign-off — **pending, human step**

**Deferred, tracked explicitly (not silent gaps)**:
- **FR-HARV-001's full `Plan → Task → Batch → Lot → Receipt → Grade → Packing Lot` pipeline** is simplified to `HarvestLot` (carrying `grade` directly) + `PackingLot` — the two entities the traceability chain actually needs. Plan/Task/Batch/Receipt are Farm Work Management (`FR-WORK`) territory (Phase 17), and building them here would pre-empt that phase's own design the same way a placeholder Disease Incident table would have pre-empted Phase 10's
- **Real QR/barcode image rendering** — `qr_code` is a random opaque token (`secrets.token_urlsafe`), the value a real QR code would encode; generating the actual scannable image is a frontend/rendering concern
- **RFID support (FR-HARV-001)** — not built; no RFID hardware/reader integration decided anywhere in the docs

## Phase 12 completion checklist (Asset & Machinery + Maintenance / Predictive Maintenance)

MVP-relevant (carried from "MVP-adjacent Phase 6" per this table). Closes Risk R-02 from `05-RTM.md`'s own risk register (the `Equipment` table's tree/asset conflation) on the asset side — trees were already split out in Phase 4; this phase gives assets their proper twin-based home too, per ADR-004 and the `docs/07-DOMAIN-MODEL.md` §3.2 design that was written back in Phase 1 but not implemented until now.

- [x] **No new `Asset` table** (FR-ASSET-001): an asset is an asset-category `DigitalTwin`; manufacturer/model/serial/install-date/warranty/documents live in `TwinProperty`, condition (temperature/vibration/status) in `current_state` — exactly the shape `migrate_equipment_to_twins.py` (Phase 6) already populates, so already-migrated legacy equipment is immediately usable through this new API with no further data migration. `POST /api/v1/assets` is a convenience wrapper that creates the twin + standard properties in one call — `backend/app/asset/models.py` (just the three new entities below; no `Asset` model), `backend/app/routers/v1/asset.py`
- [x] Meter/runtime tracking (FR-ASSET-002): no new table — reuses `TwinTelemetry` (Phase 6/7) via the existing `POST /api/v1/twins/{id}/telemetry`, same as any other sensor metric
- [x] **`health.py`'s rule engine is reused, not duplicated** (FR-PDM-001's explicit instruction): refactored into `compute_health_score()` (plain parameters) with `compute_health(eq)` kept as an unchanged-behavior thin wrapper for the legacy `Equipment` endpoints (verified by `test_legacy_equipment_health_endpoint_still_works_after_refactor`); `app/asset/health_engine.py::assess_asset_health` adapts it to read from a twin's `current_state`/`TwinProperty` instead of an `Equipment` row — one engine, two callers
- [x] `HealthAssessment` (FR-PDM-001/002's Prediction + Recommendation): a versioned, audited value object (`computed_at`, `score`, `band`, `metrics`, `recommendations`, `method_id`/`method_version`) — never a mutable field on the twin, so score history is never lost
- [x] Full `MaintenanceRequest → (approval) → WorkOrder` lifecycle (FR-MNT-002): reuses the exact approval-gated pattern Phase 8/10 established — `provision_tenant()` now also seeds a `maintenance_request` `WorkflowDefinition`; a `WorkOrder` (FR-PDM-002's **Approved Action**, separate and separately-audited from the Prediction/Recommendation that led to it) can only be created by converting an `approved` request, never directly
- [x] Corrective/preventive/predictive/condition-based strategies (FR-MNT-001): `MaintenanceRequest.strategy` enum
- [x] RBAC: `asset.*`/`asset.maintenance.*` granted per role — `maintenance_engineer` (previously a role with almost no real permissions) gets full manage, matching its name
- [x] Automated tests (`backend/tests/test_asset.py`): legacy health-endpoint regression check, asset registration + property storage, health assessment via the shared engine, full request→approve→convert→work-order→complete lifecycle, reject blocks conversion, seeded-workflow check, farm-scoped ABAC (an unscoped asset alongside a farm-scoped one, matching legacy `Equipment.model_id IS NULL`'s "unscoped" convention)
- [ ] Stakeholder review/sign-off — **pending, human step**

**Deferred, tracked explicitly (not silent gaps)**:
- **Linked documents/photos (FR-ASSET-001)** — stored as a plain list of reference strings in `TwinProperty`, not real uploaded files; MinIO is still unwired (same deferral as Phase 9's Vision AI frame storage)
- **Legacy `Equipment`/`/api/equipment` cutover** — still deliberately untouched (documented since Phase 3); the new `/api/v1/assets` surface is additive, not a replacement of the live legacy endpoints the existing frontend depends on
- **Real ML anomaly/failure-probability models** replacing `health.py`'s threshold rules is Phase 15 (AI Platform) work behind the same `compute_health_score` contract, per FR-PDM-001's own instruction

## Phase 13 completion checklist (Inventory & Procurement)

Not in MVP, S-priority throughout, no vendor/tech blockers — fully buildable, same as Phases 10/11.

- [x] Item/UOM master, warehouse/bin, lot/expiry, valuation (FR-INV-001): `Item`/`Warehouse`/`StockLot` — `backend/app/inventory/models.py`, migration `backend/alembic/versions/0013_inventory_procurement.py`
- [x] receipt/issue/transfer/return/adjustment/cycle-count (FR-INV-001): one `StockMovement.movement_type` enum + `backend/app/routers/v1/inventory.py::record_movement` rather than a table per movement type — transfer is handled specially (decrements the source lot, gets-or-creates the destination lot in the target warehouse); everything else is a signed `quantity_delta` against one lot, blocked from taking it negative
- [x] Cost attribution (FR-INV-002): `StockMovement.reference_type`/`reference_id`, a generic pair (Work Order/Farm Task/Plot/Asset/Crop/Season) rather than six nullable FKs — same pattern as `Alert.entity_type`/`entity_id` (Phase 7)
- [x] Min/max reorder point wired to real alerting: dropping a lot below `Item.min_qty` raises an `Alert` via Phase 7's existing infrastructure (idempotent — one open alert per item, not one per movement) rather than a separate low-stock mechanism
- [x] Full `Purchase Request → Approval → RFQ → Vendor Comparison → PO → Receiving → Inspection → Inventory → Invoice Matching` pipeline (FR-PROC-001), collapsed to `PurchaseRequest` (approval-gated, same seeded-workflow pattern as every Phase 8/10/12 plan — `provision_tenant()` now also seeds a `purchase_request` `WorkflowDefinition`) → `PurchaseOrder` (the Approved Action, carrying receiving/inspection/invoice fields directly). A passed receipt inspection creates the `StockLot`/`StockMovement` automatically, closing the loop into real on-hand inventory
- [x] Invoice matching: a simple tolerance check (`invoice_amount` vs `unit_price × received_quantity`, configurable `tolerance_pct`), same "indicative, not certified" treatment as every other placeholder scoring/matching function in this codebase — not real 3-way-match accounting logic
- [x] `warehouse_officer` (previously a role with almost no real permissions) gets full inventory/procurement manage — matching its name, same treatment `maintenance_engineer` got in Phase 12
- [x] Automated tests (`backend/tests/test_inventory.py`): item/warehouse CRUD, receive-creates-lot-and-movement, issue decrements + blocks over-issue, transfer between warehouses, reorder-point alert, valuation, full purchase-request → approve → issue-PO → receive → stock-created → invoice-match round trip, reject blocks PO issuance, seeded-workflow check, farm-scoped ABAC
- [ ] Stakeholder review/sign-off — **pending, human step**

**Deferred, tracked explicitly (not silent gaps)**:
- **RFQ / Vendor Comparison** — FR-PROC-001 names these as pipeline stages, but they're a pre-PO negotiation process with no persistent state of their own to model; `Vendor` master data exists for the eventual comparison UI to read from
- **Reservation** (FR-INV-001) — stock reservation against a future planned consumption is not modeled; only actual movements are
- **`Farm Task` cost-attribution reference** — like every other `FR-WORK` gap so far (Phase 10/11), `reference_type="farm_task"` is accepted but has no backing table; `reference_id` is an opaque string until Phase 17

## Phase 14 completion checklist (Farm Accounting & Profitability + Sales & Customer)

Not in MVP, S-priority (FR-SALES is `C`, the lowest tier built so far) — built with real logic throughout, same as Phases 10/11/13; no vendor/tech blockers.

- [x] **Not a duplicated General Ledger** (FR-ACC-002's explicit instruction): `LedgerEntry` is a flat, single-amount posting, not double-entry debit/credit bookkeeping — the REST API itself is the "explicit integration API" the requirement calls for. `backend/app/accounting/models.py`, migration `backend/alembic/versions/0014_accounting_sales.py`
- [x] FR-ACC-001's eleven accounting dimensions (Farm/Zone/Plot/Crop/Variety/Tree/Season/Harvest Lot/Asset/Activity/Cost Center) as a `dimensions` JSONB bag (GIN-indexed) with containment-query matching, rather than eleven nullable FK columns — same generic-reference principle as `StockMovement`/`Alert`; `CostCenter` is the one dimension with no existing master table elsewhere, so it gets one here
- [x] Accrual/payment/receipt/budget/actual/variance postings (FR-ACC-002): `LedgerEntry.entry_type` enum; `Budget` stores only the budgeted side — actual and variance are always computed live from the ledger (`GET /budgets/{id}/variance`), so they can never silently drift out of sync with what was actually posted
- [x] Profitability at Tree/Row/Plot/Crop/Farm/Season level with configurable cost-allocation (FR-PROF-001): `compute_profitability()` is a real aggregation over posted ledger data (not a placeholder rule engine like earlier phases' scoring functions — there's nothing to estimate), with overhead allocation as the one configurable/indicative parameter
- [x] Profit heatmap data (FR-PROF-002): `GET /api/v1/accounting/profitability/heatmap` returns one profitability row per dimension value within a farm/season — the data a real heatmap would render; the visualization itself is a frontend concern, same deferral as every dashboard-shaped endpoint so far
- [x] FR-SALES-001's `Customer → Contract → Quotation → Sales Order → Delivery → Invoice → Payment` pipeline collapsed to `Customer` → `SalesOrder` (single-line, `status` absorbs Contract/Quotation/Delivery) → `Invoice` → `Payment` — `backend/app/sales/models.py`
- [x] **Sales-to-accounting integration**: a fully paid `Invoice` auto-posts a revenue `LedgerEntry` (dimensions carried over from the originating `SalesOrder`'s farm/season/harvest lot, `source_type="sales_invoice"`) via the same `post_ledger_entry()` helper a manual posting would use — demonstrating the "integration API" FR-ACC-002 asks for is real, not just a description
- [x] `finance` (previously a role with almost no real permissions) gets full accounting manage + sales manage — matching its name, same treatment `maintenance_engineer`/`warehouse_officer` got in Phases 12/13
- [x] Automated tests (`backend/tests/test_accounting.py`, `backend/tests/test_sales.py`): cost-center CRUD, ledger post/list/filter, profitability computation with overhead allocation, budget variance, heatmap grouping, farm-scoped ABAC; order status-transition guards (can't deliver before confirm, can't invoice before deliver), full order→invoice→partial-payment (no posting yet)→final-payment (posts exactly once) round trip, already-paid invoice rejects further payment, farm-scoped ABAC
- [ ] Stakeholder review/sign-off — **pending, human step**

**Deferred, tracked explicitly (not silent gaps)**:
- **Multi-currency** — a single implicit currency throughout; no currency field, no FX conversion
- **Contract/Quotation/Delivery as distinct entities** — collapsed into `SalesOrder.status`, same reasoning as Phase 13's RFQ/Vendor-Comparison collapse, more justified here given FR-SALES-001 is the lowest-priority (`C`) requirement built so far
- **Multi-line sales orders** — one order = one harvest lot / quantity / price, matching the proportions of `PurchaseRequest` (Phase 13) and `IrrigationPlan` (Phase 8) rather than a full multi-line order with its own line-item table
- **Automatic ledger posting from other modules' cost-bearing events** (e.g. a completed `WorkOrder`'s labor/parts, a matched procurement `Invoice`) — deliberately not wired to avoid reaching back into every prior phase's router; `POST /ledger-entries` is available for those integrations to call explicitly when a real accounting rollout needs them

## Phase 15 completion checklist (AI/ML Platform: Model Registry, Copilot, Agents)

Not in MVP (S/M-priority per BRD §17) — the Model Registry and Agent Action Gateway are built with real enforcement logic; Copilot is grounded-answer-only (no live LLM), consistent with every other "shape now, real integration later" placeholder this platform has built when no vendor/deployment decision exists yet (Vision AI inference in Phase 9, the weather provider in Phase 8).

- [x] **AI Model Registry as a shared platform capability, not per-model-type infrastructure** (ADR-008, FR-AIML-001): `AIModel`/`ModelVersion` — `backend/app/ai/models.py`, migration `backend/alembic/versions/0015_ai_platform.py`. `foundation/seed.py::provision_tenant` auto-seeds a baseline catalog (`ai/service.py::seed_baseline_catalog`) registering the four rule-engine placeholders that already existed (`health_score_rule_engine`, `disease_risk_rule_engine`, `yield_estimation_rule_engine`, `irrigation_recommendation_rule_engine`) against `implementation_ref`s pointing at their real functions — the registry isn't empty scaffolding, it documents what's actually running today
- [x] **Prediction envelope on every prediction that matters downstream** (AI-001): `Prediction` (model_version_id/entity_type+entity_id/input_ref/output/confidence/predicted_at). Retrofitted into the two existing call sites that persist a durable result row: `routers/v1/asset.py::create_health_assessment` and `routers/v1/harvest.py::create_yield_forecast`, via the one shared `ai/service.py::record_prediction()` helper (fails soft — a tenant whose catalog wasn't (re-)seeded doesn't lose its underlying feature, just the instrumentation)
- [x] **User feedback on predictions, linked to model version** (AI-005): `PredictionFeedback` + `POST /api/v1/ai/predictions/{id}/feedback`
- [x] **Agent Action Gateway — the shared L0–L4 enforcement point** (FR-AGENT-001/002, AI-004, docs/09-SECURITY-ARCHITECTURE.md §6): `backend/app/ai/agent_gateway.py`. Concrete level semantics this implementation commits to (the BRD/SRS name the five levels but don't fully spell out execution mechanics — documented in the module docstring so the interpretation is auditable): L0/L1 always allowed; L2 executes only with an explicit same-request human confirmation; L3 executes only after the same `foundation.workflow_engine` every human "Plan" entity uses reaches `approved` (a new `agent_action` entry in `_seed_mandatory_approval_workflows`); L4 executes with no per-instance human step, but only while an active `AgentPolicyGrant` exists for that `action_type` — absent one, `resolve_effective_level` downgrades L4→L3. The six sensitive action types FR-AGENT-002 names (pesticide application, pump/valve activation, procurement, financial posting, deletion, device configuration) are additionally capped at L2 unless a grant is active, enforced once in `resolve_effective_level`, not duplicated per caller
- [x] Full Observe→Analyze→Recommend→Request Approval→Execute→Verify→Record Audit Trail lifecycle as `AgentAction` state (`proposed`→`pending_approval`→`approved`/`rejected`→`executed`/`failed`) plus a `foundation.audit.record_audit` call at propose/execute — `routers/v1/ai.py`'s propose/submit/approve/reject/execute endpoints
- [x] `AgentPolicyGrant` CRUD (create/list/revoke) — the only path to L4, itself gated behind `ai.agent.policy.manage` (granted to `tenant_admin` only, same exclusivity as `workflow.definition.manage`)
- [x] **Copilot answers only from real platform data, cites source/timestamp/confidence** (FR-COPILOT-001): `ai/copilot.py::answer_question` — no LLM call backs the answer text; each supported question category (open alerts, open disease incidents, low/reorder-point stock) runs a real query and returns citations pointing at the actual rows read. An unsupported question gets an explicit "I can't answer that yet", never an invented answer. `CopilotConversation`/`CopilotMessage` persist the exchange; `POST /api/v1/ai/copilot/ask`
- [x] **LLM provider abstraction seam** (AI-003, ADR-011): `ai/llm_provider.py::LLMProvider` protocol + `StubLLMProvider` — no Ollama/OpenAI-compatible endpoint wired (no deployment target decided for this pilot yet), mirrors `weather.provider.WeatherProvider`'s treatment exactly
- [x] RBAC: `ai.model.{view,manage}`, `ai.prediction.{view,manage}`, `ai.agent.{propose,approve,execute}`, `ai.agent.policy.manage`, `ai.copilot.use` — granted per-role in `rbac_catalog.py` (registry/policy-grant management stays `tenant_admin`-only; propose/view/copilot broadly available to operational roles; approve/execute limited to `farm_owner`/`farm_manager`, matching every other approval-gated Plan entity's permission shape)
- [x] Automated tests (`backend/tests/test_ai.py`): baseline catalog seeded on provisioning; health-assessment and yield-forecast prediction retrofit recording + feedback; L1 direct execute; L2 confirm-gate (denied then allowed); sensitive action-type L4→L2 ceiling without a grant; sensitive action reaching real L4 with an active grant, then revoke; full L3 submit→approve→execute round trip; L3 reject blocks execution; farm-scoped ABAC on agent actions; Copilot grounded answer (alerts), unsupported-question fallback, and multi-turn conversation continuity
- [ ] Stakeholder review/sign-off — **pending, human step**

**Deferred, tracked explicitly (not silent gaps)**:
- **No live LLM/Copilot free-text generation** — `StubLLMProvider` never calls out to Ollama or an OpenAI-compatible endpoint; ADR-011's provider decision (which endpoint, per-tenant configuration) is a deployment-time decision this phase deliberately does not force, same as Phase 9 not picking a vision-model vendor
- **Copilot answers only three grounded question categories** (open alerts, open disease incidents, low-stock items) — not general natural-language Q&A over arbitrary platform data; extending coverage is additive (one more `_ROUTES` handler per category), not a redesign
- **No real trained ML models** — every `ModelVersion.implementation_ref` still points at a rule-based function from Phases 8/10/11/12; ADR-008's registry makes swapping one in later a data change (a new `ModelVersion` row + updated `implementation_ref`), not a schema change, but the swap itself is out of scope here
- **AI-002's staged rollout (shadow/canary) is a status value with no traffic-splitting logic** — `ModelVersion.status` accepts `shadow`/`canary`/`active`/`retired`, but nothing currently reads `shadow`/`canary` differently from `active`; there is exactly one model version per model today, so there is nothing to split traffic between yet
- **Prediction retrofit is not platform-wide** — `crophealth.py`'s disease-risk endpoint was deliberately left un-retrofitted: it's a pure, unpersisted computation gated behind a `.view` permission (no `.manage` write today), so adding a `Prediction` insert there would either require a write under a view-only permission or a permission-model change beyond this phase's scope; `irrigation/recommendation.py::recommend_irrigation` has no router call site at all yet (a pre-existing gap since Phase 8 — `IrrigationPlan.recommended_volume_liters` is caller-supplied, not server-computed), so there is nothing to retrofit there either
- **No real actuation/integration layer** — `AgentAction.result` is entirely caller-reported JSON (same "shape now" pattern as `IrrigationEvent.actual_volume_liters`); executing an L2/L3/L4 action does not itself operate any device
- **`AgentPolicyGrant` has no expiry or narrower scope** (e.g. per-farm, time-boxed) — a grant is tenant-wide per `action_type` and active until explicitly revoked; time-boxed/scoped grants are additive later, not a schema change (`granted_at`/`is_active` already support it)

## Phase 16 completion checklist (Executive Command Center)

Backend-only scope confirmed with the user before starting (mirrors the Phase 6 "backend only" and Phase 9 "scaffold with stub" clarifications): FR-DASH-001/002 (interactive map, 3D twin viewer, drag-and-drop widget layout persistence) are frontend concerns excluded by the standing backend-only decision. FR-DASH-003 (M-priority, MVP) is a data-aggregation problem this phase does solve — no new tables, no migration; every widget reads data Phases 4-15 already persist.

- [x] **Tenant-wide fleet/equipment health summary** (FR-DASH-003 exactly: stat tiles + distribution + sortable table + `twin_id` for click-to-focus-in-3D): `GET /api/v1/dashboard/fleet-summary` — `backend/app/dashboard/aggregation.py::equipment_health_widget` joins every asset-category `DigitalTwin` against its latest `HealthAssessment` (twins with none yet get an explicit `"unassessed"` band rather than being silently omitted); the authenticated, RLS-scoped, twin-model successor to the legacy unauthenticated `GET /api/dashboard/summary` (`routers/dashboard.py`, reading the pre-Phase-6 flat `Equipment` table) — that legacy endpoint is left untouched, same as every other pre-Phase-3 legacy route
- [x] **Per-farm Command Center widget rollup** (FR-DASH-001's widget list, minus the two frontend-only items): `GET /api/v1/dashboard/farms/{farm_id}/summary` — one call assembling equipment health (farm-scoped), weather (latest station/forecast reading per metric via the existing `weather.provider.current_reading`), disease risk (open incident count + highest risk score), irrigation status (pending/approved/recently-completed counts), yield forecast (latest), harvest status (lots + kg in the last 30 days), work orders (open/in-progress counts), financial KPIs (`accounting.profitability.compute_profitability` scoped to `{"farm_id": ...}`), and AI recommendations (agent actions still `status="proposed"`, i.e. awaiting a human decision)
- [x] Also-tenant-wide fleet inventory low-stock widget (`GET .../fleet-summary`'s `inventory` field) — same query shape as `ai/copilot.py`'s low-stock answer, reused here as a typed widget rather than free text
- [x] Every widget is honest about absence rather than fabricating a default: no reading ingested → `null`, not `0`; no yield forecast yet → `yield_forecast: null`, not an empty object — verified live against a brand-new tenant with zero data (both endpoints return a fully-typed, all-`null`/all-zero shape, not an error)
- [x] RBAC: one new `dashboard.view` permission, granted to every system role including `viewer`/`auditor` — a summary rollup exposes no data a role couldn't already see one call at a time through the underlying module endpoints, so broad view access mirrors real Command Center software rather than requiring every widget's own permission simultaneously
- [x] ABAC: `GET .../farms/{farm_id}/summary` narrows via the standard `assert_farm_scope`; `GET .../fleet-summary` is inherently tenant-wide (no farm filter to narrow by), matching the existing unscoped-unless-filtered convention `GET /assets` already established
- [x] Automated tests (`backend/tests/test_dashboard.py`): fleet equipment-health tiles (assessed + unassessed bands), fleet low-stock + AI-recommendation surfacing, full farm-summary aggregation across weather/disease/irrigation/yield/harvest/financials/AI-recommendations with real posted data, work-orders widget through the real maintenance-request→approve→convert lifecycle, an empty-tenant honest-null-shape check, and farm-scoped ABAC
- [ ] Stakeholder review/sign-off — **pending, human step**

**Deferred, tracked explicitly (not silent gaps)**:
- **Interactive map, 3D twin viewer, drag-and-drop configurable widget layouts** (FR-DASH-001/002) — frontend/Next.js/Cesium work, out of scope per the standing "backend only" decision (Phase 6); this phase delivers the data API such a frontend would consume, not the frontend itself
- **No per-user saved dashboard layout** (FR-DASH-002, C-priority) — there is no persistence for "which widgets, in what order" since there is no frontend yet to lay them out
- **Financial KPIs are all-time, not date-windowed** — `compute_profitability` has no built-in date range; the widget surfaces the same all-time aggregation the Phase 14 endpoint already computes, not a new "this month" rollup
- **Fleet inventory widget is tenant-wide even though `Warehouse.farm_id` is nullable-optional** (some warehouses are already farm-scoped, per Phase 13) — the per-farm summary does not additionally filter stock by that farm's warehouses; splitting inventory into a farm-scoped widget is additive later (filter `StockLot` by `Warehouse.farm_id`), not a redesign

## Phase 17 completion checklist (Farm Work Management)

Scope confirmed with the user before starting (mirrors the Phase 6/9/16 precedent of asking when the docs bundle backend-buildable and frontend-only requirements together under one phase number): FR-MOB (offline PWA shell, local storage/sync queue, photo capture, GPS tagging UI) is entirely frontend/mobile-client work, excluded by the standing backend-only decision. FR-WORK-001/002 (work task types + the full assignment/completion lifecycle) had sat "not started" since Phase 3 despite being a real, unblocked backend capability and the prerequisite data model any future mobile task-execution UI would call — that's what this phase builds.

- [x] **A single `WorkTask` entity**, not a table per work type (FR-WORK-001's ten work types as a `work_type` string column, same "generic type column over parallel tables" principle ADR-004 established) — `backend/app/work/models.py`, migration `backend/alembic/versions/0016_work_management.py`
- [x] **The full FR-WORK-002 lifecycle as status transitions**, each with its own dedicated action endpoint (`plan`/`assign`/`accept`/`reject`/`start`/`complete`/`review`/`cancel`) rather than a generic PATCH-status call — closer to `crophealth.models.DiseaseIncident`'s own lifecycle shape than to `foundation.workflow_engine`'s approval-gate pattern, and deliberately NOT routed through the workflow engine: a work task's "Supervisor Review" happens *after* the work is already done (quality/close-out), not *before* a risky action executes, so there is no approval gate to enforce here the way there is for Irrigation/Fertigation/Treatment/Maintenance/Purchase plans
- [x] **Evidence capture folded into the `complete` transition** (FR-WORK-003's photos/measurements/materials/labor) as one `evidence` JSONB field, populated by whatever calls the API today (Postman, a test, a future mobile client) — the data shape is real and stored now even though the mobile capture UI that would populate it live is deferred
- [x] **Review can send work back for rework**: `completed` → `closed` (approve) or `completed` → `in_progress` (send back), mirroring `DiseaseIncident`'s "monitoring → treatment_planned" loop-back precedent from Phase 10
- [x] **Only the assigned worker or a `work.task.manage` holder can accept/start/complete** a task (`_assert_assignee_or_manager` in `routers/v1/work.py`) — same role-match-OR-broader-permission shape `workflow_engine._require_current_step_approver` already established, applied here to task ownership instead of an approval role
- [x] Generic `source_type`/`source_id` reference pair (nullable, optional) lets a caller link a task back to whatever prompted it, but nothing auto-creates or auto-populates it from other modules' flows — same explicitly-deferred integration Phase 14 documented for automatic ledger postings, applied consistently here
- [x] RBAC: `work.task.{view,manage,execute,review}` — `farm_owner`/`farm_manager`/`agronomist` get the full set (they plan, assign, and can execute/review); `field_worker`/`maintenance_engineer`/`warehouse_officer` get `view`+`execute` (the assignees who do the work); `finance`/`auditor`/`viewer` get `view` only
- [x] Automated tests (`backend/tests/test_work.py`): full request→plan→assign→accept→start→complete→review(close) lifecycle; review send-back reopening for rework and re-completing; reject-is-terminal; only-assignee-or-manager enforcement (denied for an unrelated worker, allowed for a manager acting on the worker's behalf); assign-before-planned blocked; cancel blocks further planning; farm-scoped ABAC
- [x] **Bug found and fixed during verification**: `assign_task`/`complete_task`/`review_task` originally called `db.commit()` *before* `record_audit()` instead of after — the exact `set_tenant_context` pitfall documented in `core/deps.py` and hit for real in Phase 7 (a commit clears the transaction-scoped RLS setting, so the following audit-log insert was rejected by row-level security). Fixed by moving each `record_audit()` call before its transition's `db.commit()`, verified via the full test suite and a live end-to-end lifecycle run
- [ ] Stakeholder review/sign-off — **pending, human step**

**Deferred, tracked explicitly (not silent gaps)**:
- **FR-MOB in full** (offline PWA shell, local storage + transaction queue + sync service with conflict resolution per ADR-013, photo capture, GPS tagging, sync-status UI) — frontend/mobile-client work, out of scope per the standing "backend only" decision; this phase delivers the backend lifecycle API such a client would call, not the client itself
- **No offline sync endpoint** — FR-WORK-003's "complete tasks fully offline, syncing on reconnect" needs a batch/queue-shaped sync API (and ADR-013's field-wins conflict policy) that only makes sense once there's a real offline client driving it; the existing action endpoints are synchronous, one-transition-at-a-time calls
- **No automatic `WorkTask` creation from other modules** (an approved `IrrigationPlan`, a converted `MaintenanceRequest`, a `PurchaseOrder` receipt) — `source_type`/`source_id` make linking possible later without a schema change, but nothing wires it up yet, consistent with Phase 14's ledger-posting-integration deferral
- **No QR/barcode-scan or GPS-tagging fields on `WorkTask`** — FR-WORK-003 lists them as mobile-capture inputs; without a mobile client to produce them, adding placeholder columns now would be speculative rather than shape-now-for-a-known-contract

## Phase 18 completion checklist (Hardening: rate limiting + OWASP baseline)

Scope narrowed with the user before starting: Phase 18 as documented bundles SEC-001..008/DATA-001..004/NFR-001..009/DEP-001..005 — most of that is infra/deployment/ops work (TLS termination, Kubernetes manifests, CI vulnerability scanning, backup/DR runbooks, encryption-at-rest, environment promotion) that isn't application code this repo can meaningfully write or test. SEC-001/002/003 (auth, RBAC+ABAC, RLS tenant isolation) were already implemented since Phase 3. The user chose SEC-007 (rate limiting + OWASP-baseline headers) as this pass's concrete scope; structured logging/`/metrics` (NFR-005/009) and IoT device secret rotation (SEC-006) were offered but not chosen, and remain available follow-ups.

- [x] **Redis-backed rate limiting** (SEC-007): `backend/app/core/rate_limit.py`'s `check_rate_limit()`, wired as ASGI middleware in `main.py`. Fixed-window counter (`INCR`+`EXPIRE`) keyed by bearer token when present, else client IP, per (path, method) — coarse abuse protection, not precise traffic shaping. Tiered limits (all configurable via `Settings`): a strict `POST /api/v1/auth/login` limit (brute-force mitigation), a moderate limit on the one public unauthenticated endpoint (`GET /api/v1/harvest/trace/{tenant_slug}/{qr_code}`, Phase 11), and a generous default for everything else
- [x] **Fails open, not closed, when Redis is unreachable** (NFR-004's "degrade gracefully... when a downstream dependency is unavailable" principle, applied to this new dependency): verified live by stopping the `redis` container entirely and confirming the API kept serving `200`s rather than erroring — see the bug found below for why this mattered more than expected
- [x] **OWASP-baseline security response headers**: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Strict-Transport-Security` — a second small ASGI middleware in `main.py`, applied to every response including 429s
- [x] **Disabled via `RATE_LIMIT_ENABLED=false` for test/CI runs** — Starlette's `TestClient` gives every request the same fake client identity, so a real limiter would collapse the whole suite into one shared bucket; this is a standard env-driven `Settings` toggle (`rate_limit_enabled`), not test-specific code branching. **Going forward, run the backend test suite as `docker compose run --rm -e RATE_LIMIT_ENABLED=false backend pytest ...`** (CI should do the same)
- [x] Automated tests (`backend/tests/test_rate_limit.py`): threshold enforcement and recovery on a fresh key, the disabled-toggle never blocking, rule-selection/client-key unit tests, and security-header presence on every response — the three lifecycle tests explicitly flip `settings.rate_limit_enabled` for their own duration (against a path no other test touches) and clean up their Redis key in a `finally` block, since the rest of the suite runs with the toggle off
- [x] **Bug found and fixed during verification**: the first implementation cached a single module-level `aioredis.Redis` client for the process lifetime. That client's connection pool is bound to the asyncio event loop it was created on; reusing it from a *different* loop raises `RuntimeError: Event loop is closed`, which the fail-open `except` branch silently swallowed - live tracing (a request-by-request debug harness against `TestClient`, which recreates event loops between calls) showed this manifesting as intermittent, silent bypasses of the counter rather than an outright crash, which is worse: a rate limit that occasionally just doesn't apply, with no error surfaced anywhere. Fixed by keying the client cache on `id(asyncio.get_running_loop())` instead of a single global — one real uvicorn process still gets exactly one cached client (one loop, its whole lifetime), but anything that legitimately changes loops gets a fresh, correctly-bound one instead of a silently-broken one
- [ ] Stakeholder review/sign-off — **pending, human step**

**Deferred, tracked explicitly (not silent gaps)**:
- **Everything infra/deployment-layer in SEC/DATA/DEP/NFR**: TLS termination (SEC-004 — `Strict-Transport-Security` is set unconditionally by this phase, but actually terminating TLS is a reverse-proxy/ingress concern outside this app's code), encryption at rest (SEC-008), file-upload validation (SEC-005 — no upload endpoint exists yet in this codebase to harden), Kubernetes manifests (DEP-002), CI vulnerability scanning (DEP-003), environment promotion docs (DEP-004), backup/DR runbooks (DEP-005), TimescaleDB compression tuning (DATA-003) — none of these are code changes this pass makes; they need an actual deployment target decided first, the same reasoning already applied to the weather/LLM/vision provider seams
- **IoT device secret rotation/revocation endpoint** (SEC-006's "revocable") — offered as an option, not chosen; `IotDevice.is_active` exists and can already be toggled via the general device-update endpoint, but there is no dedicated "rotate this device's secret without deleting the device" action yet
- **Structured JSON logging + `/metrics`** (NFR-005/009) — offered as an option, not chosen; `/health`/`/ready` already exist (Phase 3) and every response already carries the correlation ID via the existing middleware, but logs are still uvicorn's default text format and there is no Prometheus-scrapeable endpoint
- **No per-endpoint rate-limit overrides beyond the three tiers** (login / public-trace / default) — every other authenticated endpoint shares the one default bucket per (token, path, method); a genuinely expensive endpoint (bulk export, say) would need its own tier if one existed today
