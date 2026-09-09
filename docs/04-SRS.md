# 04 — Software Requirements Specification (SRS)

**Document status:** Draft for internal review · Phase 0 · v0.1
**Related:** [01-VISION.md](01-VISION.md) · [02-SCOPE.md](02-SCOPE.md) · [03-BRD.md](03-BRD.md) · [05-RTM.md](05-RTM.md)

Priority key: **M**ust · **S**hould · **C**ould.

---

## 1. Digital Twin Requirements (`TWIN`)

| ID | Requirement | Pri |
|---|---|---|
| TWIN-001 | The twin data model shall be generic (`DigitalTwin`, `TwinType`, `TwinProperty`, `TwinRelationship`, `TwinState`, `TwinTelemetry`, `TwinEvent`, `TwinCommand`, `TwinDocument`, `TwinLocation`, `TwinModelReference`, `TwinAlert`) — no twin-kind-specific tables for tree vs. pump vs. camera; kind-specific fields live in `TwinProperty`/typed extensions, not new base tables | M |
| TWIN-002 | Every twin shall expose current state, historical state (queryable time range), and an event timeline via one consistent API shape regardless of twin type | M |
| TWIN-003 | `TwinRelationship` shall support directed, typed edges (e.g. `LOCATED_IN`, `MONITORED_BY`, `OBSERVED_BY`, `IRRIGATED_BY`, `SUPPLIED_BY`, `DRAWS_FROM`, `PRODUCED`, `MAINTAINED_BY`) enabling graph traversal for impact analysis (e.g. "which trees are affected if this pump fails") | M |
| TWIN-004 | `TwinTelemetry` shall be append-only and partition/compress at scale (see DATA-003) | M |
| TWIN-005 | This repository's existing `Equipment` table (position + condition snapshot) is the migration source for the initial `DigitalTwin`/`TwinProperty` population for asset twins; the tree-vs-equipment string-prefix hack must be resolved into distinct `TwinType`s before agronomic fields are added (see [00-EXISTING-CODEBASE-ANALYSIS.md §5](00-EXISTING-CODEBASE-ANALYSIS.md)) | M |

## 2. GIS Requirements (`GIS`)

| ID | Requirement | Pri |
|---|---|---|
| GIS-001 | All spatial data shall be stored and queried via PostGIS, in WGS84, with reprojection support for local coordinate systems used in farm surveys | M |
| GIS-002 | The map client shall use a vector-tile renderer (MapLibre GL) for 2D layers and support raster overlay (orthophoto) | M |
| GIS-003 | Spatial edits (draw/move/delete geometry) shall be audited the same as any other twin mutation (BR-004) | M |

## 3. IoT Requirements (`IOT`)

| ID | Requirement | Pri |
|---|---|---|
| IOT-001 | Ingestion path shall be: Device → Gateway → MQTT → Ingestion service → Validation → Transformation → TimescaleDB → Rules Engine → Alert/Twin update, with each stage independently observable | M |
| IOT-002 | The MQTT broker and device connections shall support authenticated, encrypted (TLS) device sessions; no device shall publish telemetry without an authenticated identity | M |
| IOT-003 | Ingestion shall tolerate and flag duplicate telemetry (same device/metric/timestamp) without corrupting aggregates | M |
| IOT-004 | The rules engine shall be tenant/farm-configurable (thresholds per crop/device-type) rather than globally hardcoded | S |
| IOT-005 | A device simulator shall be able to impersonate any supported protocol (MQTT/Modbus/LoRaWAN/HTTP) for development and load testing | M |

## 4. AI Requirements (`AI`)

| ID | Requirement | Pri |
|---|---|---|
| AI-001 | Every model prediction/recommendation surfaced anywhere in the platform shall record model name, version, timestamp, input data reference, and confidence (where the method produces one) — enforced at the API contract level (a `Prediction` envelope), not left to each caller | M |
| AI-002 | Model deployment shall be versioned and support staged rollout (shadow/canary) before a new model version drives recommendations shown to end users | S |
| AI-003 | The LLM layer shall be provider-interchangeable (local via Ollama, OpenAI-compatible API, or a configurable enterprise endpoint) behind one internal interface — no application code shall hardcode a specific provider's SDK | M |
| AI-004 | Agent action-level enforcement (L0–L4, BR-002/BR-003) shall be implemented as a shared platform capability, not duplicated per agent | M |
| AI-005 | User feedback on a prediction (accepted/rejected/corrected) shall be captured and linked to the model version, forming the basis for future retraining evaluation | S |

## 5. Vision AI Requirements (`VIS`)

| ID | Requirement | Pri |
|---|---|---|
| VIS-001 | The vision pipeline shall persist the source frame/image for every stored detection, not only the extracted metadata, so a human reviewer can verify the original evidence | M |
| VIS-002 | Detections shall carry a human validation status (`pending` / `confirmed` / `rejected`) and unconfirmed detections shall not, by themselves, advance a Disease Incident past "Suspected" (ties to FR-CCTV-004/FR-CCTV-005) | M |
| VIS-003 | Frame sampling rate and retention period shall be configurable per camera/use-case to bound storage cost | S |

## 6. Farm Accounting Requirements (`FIN`)

| ID | Requirement | Pri |
|---|---|---|
| FIN-001 | Every accounting posting shall carry the full dimension set (Farm/Zone/Plot/Crop/Variety/Tree/Season/Harvest Lot/Asset/Activity/Cost Center) even when several are null, so reporting never needs a schema migration to add a missing dimension later | M |
| FIN-002 | Financial postings shall be immutable once posted; corrections are reversing entries, never edits (BR-004) | M |
| FIN-003 | Where a tenant already operates a corporate ERP for the General Ledger, the platform shall expose an integration API (posting export) rather than requiring migration off that ERP | S |

## 7. Security Requirements (`SEC`)

| ID | Requirement | Pri |
|---|---|---|
| SEC-001 | Authentication via OAuth2/OIDC; passwords (where used) hashed with a modern algorithm (e.g. Argon2/bcrypt); MFA-ready from the identity design, even if not enforced in v1 | M |
| SEC-002 | Every API endpoint shall enforce RBAC+ABAC scope checks server-side; UI-level hiding of controls is not a substitute for server-side authorization | M |
| SEC-003 | Tenant data isolation shall be enforced at the data-access layer (e.g. row-level security or a mandatory tenant-scoped query layer), not solely by application-level filtering that a bug could bypass | M |
| SEC-004 | All API traffic shall use TLS; secrets (DB credentials, API keys, JWT signing keys) shall be sourced from environment/secret management, never committed to source control | M |
| SEC-005 | File uploads (IFC models, images, documents) shall be validated by content, size-limited, and stored outside the web root with randomized storage names | M |
| SEC-006 | Device (IoT) authentication shall be per-device, revocable, and distinct from user authentication | M |
| SEC-007 | The platform shall apply rate limiting on public-facing APIs and standard OWASP-Top-10 mitigations (injection, XSS, CSRF where applicable) | M |
| SEC-008 | Encryption at rest shall be applied to the database and object storage where the deployment target supports it (cloud-managed encryption acceptable; on-prem requires disk-level encryption) | S |

## 8. Integration Requirements (`INT`)

| ID | Requirement | Pri |
|---|---|---|
| INT-001 | All inter-service and external integration shall be API-first (OpenAPI-documented REST) or event-driven (documented event schema); no direct cross-service database access | M |
| INT-002 | Event schemas (e.g. `SensorReadingReceived`, `SoilMoistureLow`, `DiseaseRiskDetected`, `IrrigationCompleted`, `WorkOrderClosed`) shall be versioned and published centrally so downstream consumers do not need source access to integrate | S |
| INT-003 | Weather, LLM, and messaging (LINE/SMS) integrations shall be provider-abstracted so a provider swap does not touch business logic | M |

## 9. Reporting Requirements (`RPT`)

| ID | Requirement | Pri |
|---|---|---|
| RPT-001 | Reporting shall be served from real operational data via API, never from static/dummy chart data, matching the report catalog in the platform brief §37 (farm/plot/tree health, irrigation/fertilizer usage, work completion, disease trend, soil trend, yield, maintenance downtime/PM-compliance/cost, inventory balance/usage/expiry, expense/revenue/profitability/budget-vs-actual by farm and plot) | S |
| RPT-002 | Reports shall support export (at minimum CSV/PDF) and date/season range filtering | S |

## 10. Data Requirements (`DATA`)

| ID | Requirement | Pri |
|---|---|---|
| DATA-001 | Standard fields (`id` UUID, `tenant_id`, `created_at`, `created_by`, `updated_at`, `updated_by`, plus soft-delete or version fields where business-justified) shall be applied consistently across entities | M |
| DATA-002 | Soft deletion shall be used only where a business requirement justifies recoverability; otherwise hard-delete with audit-trail preservation is preferred to avoid "soft-deleted but still counted" bugs | M |
| DATA-003 | Time-series data (telemetry) shall use partitioning/compression (TimescaleDB hypertables) sized for the stated NFR targets (see §11) | M |
| DATA-004 | Every migration shall be applied via a tracked migration tool (Alembic); no direct `create_all`/manual schema edits in any environment beyond local dev — **this repo currently lacks Alembic entirely and must adopt it before further schema changes (see [00-EXISTING-CODEBASE-ANALYSIS.md §5](00-EXISTING-CODEBASE-ANALYSIS.md))** | M |

## 11. Non-Functional Requirements (`NFR`)

### 11.1 Performance & Scale

| ID | Requirement | Pri |
|---|---|---|
| NFR-001 | API P95 response time ≤ 500 ms for interactive read endpoints under nominal load | M |
| NFR-002 | Telemetry ingestion pipeline shall sustain the target design scale: ≥100 farms/tenant, ≥100,000 trees, ≥10,000 devices, and millions of telemetry records/day, without redesign | M |
| NFR-003 | 3D viewer shall maintain interactive frame rates for orchard-scale scenes (tens of thousands of tree instances) via level-of-detail/instancing, not one draw call per tree | S |

### 11.2 Availability & Resilience

| ID | Requirement | Pri |
|---|---|---|
| NFR-004 | Core farm-operations services shall degrade gracefully, not fail closed, when a downstream dependency (AI service, external weather API) is unavailable — **this repo's existing localStorage fallback when the backend is unreachable is a validated pattern for this principle at the UI layer** | M |
| NFR-005 | System health shall be observable via `/health`, `/ready`, `/metrics` endpoints on every service | M |

### 11.3 Offline / Edge

| ID | Requirement | Pri |
|---|---|---|
| NFR-006 | Field-facing components (mobile PWA, edge gateway) shall operate on local cache/rules when disconnected from the core platform and reconcile via store-and-forward sync on reconnect | M |

### 11.4 Usability & Localization

| ID | Requirement | Pri |
|---|---|---|
| NFR-007 | UI shall support Thai and English, switchable per user; operational/farm-worker-facing text defaults to Thai given the primary user base — **this repo's existing Thai-language health/dashboard strings validate this direction and should be extended, not replaced** | M |
| NFR-008 | UI shall define explicit loading, empty, error, permission-denied, offline, and stale-data states for every data-bound view — no view may silently show nothing or stale data without indicating so | M |

### 11.5 Observability

| ID | Requirement | Pri |
|---|---|---|
| NFR-009 | Services shall emit structured logs with correlation/trace IDs and expose metrics compatible with OpenTelemetry/Prometheus | S |

## 12. Deployment Requirements (`DEP`)

| ID | Requirement | Pri |
|---|---|---|
| DEP-001 | All services shall be containerized (Docker) with a docker-compose definition covering the full local dev stack (Postgres+PostGIS, TimescaleDB, Redis, MQTT broker, MinIO, backend services, web) — **currently absent from this repo and required before Phase 3 work lands** | M |
| DEP-002 | Production topology shall be Kubernetes-ready without being Kubernetes-only (docker-compose remains viable for small/on-prem single-farm deployments) | S |
| DEP-003 | CI shall run tests, build images, and run a vulnerability scan on every merge to main; production secrets shall never be present in the repository | M |
| DEP-004 | Environments DEV/TEST/UAT/PRODUCTION shall be config-isolated (no shared credentials/data) with documented promotion between them | S |
| DEP-005 | Backup/DR: define RPO/RTO/retention per data class (see [05-RTM.md](05-RTM.md) for initial targets) and document the recovery procedure before go-live | M |
