# 11 — Architecture Decision Records (Phase 1)

**Document status:** Draft for internal review · Phase 1 · v0.1
**Related:** [06-ARCHITECTURE.md](06-ARCHITECTURE.md) · [05-RTM.md §4](05-RTM.md) (open decisions this set resolves)

Format: Context → Decision → Alternatives considered → Consequences. Once accepted, an ADR is not edited to reflect a later reversal — a new ADR supersedes it and says so explicitly.

---

## ADR-001: PostgreSQL + PostGIS as the primary transactional/spatial store

**Context:** The platform needs ACID transactional storage for financial, approval, and twin-graph data, plus spatial queries over farm/plot/tree geometry. This repo's backend already uses PostgreSQL.
**Decision:** PostgreSQL + PostGIS extension for all transactional and spatial data, across all bounded contexts.
**Alternatives considered:** MySQL/MariaDB (weaker native spatial support); a dedicated spatial DB alongside a separate RDBMS (extra operational surface, cross-store joins for common "assets in this plot" queries).
**Consequences:** One relational engine to operate/back up/tune; spatial and transactional data can be queried and transacted together; RLS-based multi-tenancy (ADR-007) depends on Postgres's native RLS feature.

## ADR-002: TimescaleDB for telemetry

**Context:** Sensor/telemetry data is high-volume, append-only, time-ordered, and must sustain millions of records/day (NFR-002) without degrading interactive query performance.
**Decision:** TimescaleDB (a PostgreSQL extension) for `TwinTelemetry` and all raw device telemetry, using hypertables partitioned by time and continuous aggregates for rollups.
**Alternatives considered:** InfluxDB (separate query language/operational stack, would break the "one relational engine" simplicity of ADR-001); a plain partitioned Postgres table (would require reimplementing what TimescaleDB provides natively — continuous aggregates, compression policies, retention policies).
**Consequences:** Telemetry stays queryable via SQL alongside relational twin data (can join telemetry to twin metadata without cross-database federation); retention/downsampling (per [08-DATA-ARCHITECTURE.md §3](08-DATA-ARCHITECTURE.md)) is a TimescaleDB policy, not application code.

## ADR-003: MQTT as the device-telemetry protocol, with Modbus/LoRaWAN bridged at the edge

**Context:** Field devices vary widely (soil sensors, weather stations, pump controllers, legacy Modbus equipment). The platform needs one canonical ingestion protocol at the cloud/core boundary.
**Decision:** MQTT (TLS, per-device auth) is the protocol the IoT Service accepts. Modbus RTU/TCP and LoRaWAN devices are bridged to MQTT **at the Edge Gateway**, not by the core platform speaking every device protocol directly.
**Alternatives considered:** Core platform speaking Modbus/LoRaWAN directly (couples the cloud service to field-protocol quirks and requires it to be reachable on those protocols, which don't tolerate WAN latency/drops well); CoAP (less mature tooling/ecosystem support than MQTT for this use case).
**Consequences:** The Edge Gateway becomes the required component for any non-MQTT-native device (confirms its place in [06-ARCHITECTURE.md §5](06-ARCHITECTURE.md)); the core IoT Service has one ingestion contract to secure and scale (SEC-006, IOT-002).

## ADR-004: Generic Digital Twin graph model over per-object-type tables

**Context:** The platform must represent trees, pumps, valves, tanks, cameras, sensors, buildings, and future object types without a schema migration per new type.
**Decision:** A generic `DigitalTwin`/`TwinType`/`TwinProperty`/`TwinRelationship` model ([07-DOMAIN-MODEL.md §3.1](07-DOMAIN-MODEL.md)), where type-specific fields live in a `TwinProperty` extension mechanism (JSONB with a `TwinType`-defined schema) rather than new base tables per type.
**Alternatives considered:** Class-Table Inheritance (a table per twin type — reintroduces the "new type needs a migration" problem this decision exists to avoid); single flat table with many nullable columns for all possible fields (this repo's current `equipment` table, already identified as unsustainable — [00-EXISTING-CODEBASE-ANALYSIS.md §5](00-EXISTING-CODEBASE-ANALYSIS.md), Risk R-02).
**Consequences:** Adding a new twin type (e.g. a new equipment category, or crop #8) is a configuration change (new `TwinType` + property schema), not a code/migration change — directly satisfies the crop-extensibility constraint in [02-SCOPE.md §1](02-SCOPE.md). Query patterns over JSONB properties need appropriate GIN indexing; this is an accepted, well-understood Postgres trade-off.

## ADR-005: Three.js + web-ifc-viewer for IFC/mechanical scenes; CesiumJS + 3D Tiles for orchard-scale terrain, composited per scene

**Context:** The platform needs both building/mechanical-room-scale IFC rendering (already working in this repo) and orchard/terrain-scale rendering (hundreds of thousands of trees, drone-derived terrain/point clouds) — a single engine tuned for one scale performs poorly at the other.
**Decision:** Keep `web-ifc-viewer`/Three.js (already integrated and working in this repo) for IFC-sourced building/mechanical content; add CesiumJS for terrain/3D-Tiles/point-cloud orchard content; composite both into one user-facing 3D scene per [ADR-006](11-ADR.md)'s hybrid-spatial-model boundary rule.
**Alternatives considered:** Cesium alone for everything (loses this repo's working, IFC-native property-inspection/spatial-tree UX, which would need to be rebuilt on IFC-to-3D-Tiles conversion); Three.js alone for everything (no native 3D Tiles/terrain streaming support at orchard scale without substantial custom engineering Cesium already provides).
**Consequences:** Two rendering engines must be kept in sync (camera state, selection state) in the composited viewer — a genuine integration cost, accepted because it preserves the working IFC viewer rather than discarding it. This is a concrete Phase 6 engineering task, not a Phase 1 detail to hand-wave.

## ADR-006: Hybrid spatial model — explicit IFC-vs-3D-Tiles boundary rule

**Context:** §8 of the platform brief calls for "a hybrid spatial model rather than forcing all objects into IFC" but doesn't state the boundary rule.
**Decision:** IFC represents **built, mechanical, and utility structures** (buildings, pump rooms, warehouses, tanks, mechanical/utility systems) — objects with an engineering/BIM origin. 3D Tiles/terrain/point cloud represents **the orchard/terrain itself** (ground, canopy-scale tree placement, large-scale drone-derived surfaces). A `DigitalTwin`'s `model_ref` ([07-DOMAIN-MODEL.md §3.1](07-DOMAIN-MODEL.md)) points to whichever representation is appropriate for that twin's `TwinType`; the two are composited in one Three.js/Cesium scene (ADR-005) rather than one universal format being forced onto everything.
**Alternatives considered:** Convert all IFC content to 3D Tiles (loses IFC's rich property-set/spatial-structure semantics that the existing property inspector and spatial tree already depend on); force orchard/terrain into IFC (IFC is not designed for terrain-scale, tens-of-thousands-of-instance content and tooling support is poor).
**Consequences:** Any new twin type must be classified at design time as "IFC-sourced" or "GIS/3D-Tiles-sourced" — this classification becomes part of the `TwinType` configuration record.

## ADR-007: Row-level security (RLS) with `tenant_id`, not schema- or database-per-tenant

**Context:** Multi-tenant isolation (SEC-003, BR-007, Risk R-06) must be architecturally guaranteed, not just application-code discipline, while keeping operational complexity manageable for a platform that starts with one pilot tenant and grows.
**Decision:** Every table carries `tenant_id`; PostgreSQL RLS policies enforce `tenant_id = current_setting('app.current_tenant_id')` on every query, set per-request by the service layer from the verified JWT's tenant claim (detailed in [09-SECURITY-ARCHITECTURE.md §4](09-SECURITY-ARCHITECTURE.md)).
**Alternatives considered:** Schema-per-tenant (operationally heavy at scale — migrations must run per-schema, connection pooling gets awkward with hundreds of tenants); database-per-tenant (strongest isolation but the heaviest operational cost, and cross-tenant platform-level reporting for the Super Admin becomes a federation problem) — either could be revisited for a specific high-security enterprise tenant later, but is not the v1 default.
**Consequences:** Single database to operate/migrate/back up; isolation is enforced even against an application bug that forgets a tenant filter; requires discipline that *every* connection sets the session tenant variable — this is centralized in one shared data-access layer (not per-service reimplementation) specifically to make that discipline structural rather than convention-based.

## ADR-008: AI Model Registry as a shared platform capability, not per-model-type infrastructure

**Context:** The platform will host many model types (disease detection, yield forecast, harvest-date prediction, irrigation demand, fertilizer recommendation, machine anomaly/failure, price/revenue/profit forecast) that each currently would otherwise reinvent versioning/deployment/metric-tracking.
**Decision:** One AI Model Registry service (`AIModel`, `AIModelVersion`, `Deployment`, `Prediction`, `ModelMetric`, `Feedback` — [03-BRD.md §17](03-BRD.md)) used by every model-producing context; this repo's `health.py` rule-based scorer is registered as `model_type=rule_engine, version=v0` in this registry from Phase 3, so its later replacement by a real ML model is a new registered version behind the same `HealthAssessment` output contract ([07-DOMAIN-MODEL.md §3.2](07-DOMAIN-MODEL.md)), not a rewritten integration.
**Alternatives considered:** Each AI-producing context building its own versioning/tracking (duplicated effort, inconsistent provenance metadata, breaks AI-001's platform-wide guarantee that every prediction carries model/version/confidence).
**Consequences:** Any new model type onboards by registering against the shared contract rather than building new infrastructure; model governance/audit (§59 of the platform brief) has one place to look, not N places.

## ADR-009: Edge architecture — Edge Gateway as the trust and protocol boundary at each farm site

**Context:** Farms are frequently low-connectivity; field devices often can't authenticate/encrypt themselves; the platform must operate offline-first at the edge (NFR-006).
**Decision:** Each farm site runs an Edge Gateway (containerized stack on a local mini-PC/industrial gateway device) that: bridges device protocols to MQTT (ADR-003), runs local rules and local inference for latency/offline-critical decisions (e.g. a safety cutoff should not wait on a WAN round-trip), and store-and-forwards to the core platform over an outbound-only TLS tunnel.
**Alternatives considered:** No edge tier, devices/PLCs connect directly to the cloud (fails immediately under the stated low-connectivity constraint, and exposes field devices' often-weak native security directly to the internet); a heavier edge Kubernetes deployment (k3s) per site (viable for larger farms, oversized for a single-orchard pilot — sizing deferred to Phase 7 once real device counts are known, per Open Decision #9 in [05-RTM.md §4](05-RTM.md)).
**Consequences:** The Edge Gateway is a required deliverable of Phase 7 (IoT), not optional; its local-rules capability means some safety-critical logic (irrigation max-runtime cutoff, FR-IRR-004) must be **duplicated** at the edge (fast, offline-safe) and at the core (authoritative, audited) — an accepted consistency trade-off in favor of physical safety over architectural purity.

## ADR-010: Event bus — NATS over Kafka

**Context:** The platform needs an internal pub/sub backbone for domain events ([07-DOMAIN-MODEL.md §4](07-DOMAIN-MODEL.md)) at modular-monolith scale, not (yet) the multi-petabyte streaming scale Kafka is built for.
**Decision:** NATS (with JetStream for at-least-once persistence where an event must survive a consumer outage).
**Alternatives considered:** Kafka (higher operational complexity — ZooKeeper/KRaft, partition management — unjustified at the platform's current scale target; can be revisited if a future context needs Kafka-specific stream-processing capabilities).
**Consequences:** Lighter operational footprint matching the modular-monolith starting point (principle #2); if a future bounded context genuinely needs Kafka-scale stream processing, that's a new ADR superseding this one for that specific integration, not a wholesale platform migration.

## ADR-011: LLM provider abstraction with Ollama as the default local/on-prem provider

**Context:** AI-003 requires provider-interchangeability; the platform must serve both on-prem/air-gapped pilot deployments and cloud tenants who may prefer a hosted model.
**Decision:** One internal `LLMProvider` interface; **Ollama (local)** is the default for on-prem/single-orchard deployments (no external dependency, no per-token cost, works offline-adjacent); an **OpenAI-compatible hosted endpoint** is selectable per tenant for cloud deployments wanting higher-capability models. Neither is hardcoded into Copilot/Agent business logic.
**Alternatives considered:** Hardcoding one commercial provider (violates AI-003 and creates dependency risk for on-prem/air-gapped pilot customers who are a stated target deployment model in [02-SCOPE.md §2](02-SCOPE.md)).
**Consequences:** Prompt/response handling must stay within the lowest-common-denominator capability the interface guarantees (e.g. not assuming a specific provider's function-calling format without a translation layer).

## ADR-012: Frontend migration path — incremental strangler-fig, not a rewrite

**Context:** This repo's existing frontend (vanilla JS/Vite, `src/main.js` ~1650 lines) has working, validated interaction logic (IFC loading, spatial tree, property inspector, raycasted placement/drag, health dashboard) that the target stack (Next.js/React/TypeScript) should not discard, per [00-EXISTING-CODEBASE-ANALYSIS.md §4](00-EXISTING-CODEBASE-ANALYSIS.md).
**Decision:** Migrate incrementally (strangler fig): stand up the Next.js/React/TS shell in Phase 6, port one interaction surface at a time (3D viewer container → property panel → placement/drag → dashboard) into typed React components, keeping the existing app functionally live in `apps/web` throughout rather than a big-bang rewrite gated behind one release.
**Alternatives considered:** Full rewrite from a blank Next.js app (higher risk of silently regressing working, non-trivial interaction logic — the raycasting/drag/placement code in particular has no test coverage today, so a rewrite would be re-deriving untested behavior from memory rather than from a spec).
**Consequences:** Both a legacy and a migrating-to-React code path coexist temporarily during Phase 6 — this is accepted, bounded, migration-tracked technical debt, not permanent; Phase 6's exit criteria include "no vanilla-JS interaction code remains uncovered by the React migration."

## ADR-013: Mobile PWA offline conflict resolution — field-wins with explicit merge UI for financial/inventory fields

**Context:** FR-MOB-002/NFR-006 require offline operation with sync-on-reconnect; concurrent edits (a field worker completing a task offline while a supervisor edits the same task online) need a defined resolution policy, not an implicit one.
**Decision:** Default policy is **field-wins** for task-execution fields (completion status, photos, measurements, harvest quantities) — the field worker's on-the-ground record is authoritative for what physically happened. Financial and inventory-quantity fields instead **queue for explicit manual merge** (surfaced to a supervisor) rather than auto-resolving, since a silent auto-resolution of a stock quantity or cost figure is a data-integrity risk BR-004 exists to prevent.
**Alternatives considered:** Last-write-wins globally (risks a supervisor's office edit silently overwriting a field worker's ground-truth harvest record, or the reverse for financial figures where the office record should generally be authoritative — the risk profile differs by field category, which a single global policy can't express).
**Consequences:** The sync engine needs a per-field-category conflict-resolution table, not one global rule — a concrete Phase 17 design input rather than a detail left to be improvised during mobile implementation.
