# 10 — Integration Architecture (Phase 1)

**Document status:** Draft for internal review · Phase 1 · v0.1
**Related:** [06-ARCHITECTURE.md](06-ARCHITECTURE.md) · [07-DOMAIN-MODEL.md §4](07-DOMAIN-MODEL.md) · [04-SRS.md §8](04-SRS.md)

---

## 1. Integration styles

| Style | When used | Examples |
|---|---|---|
| Synchronous REST (OpenAPI) | Client-facing reads/writes, request/response needed immediately | Web/mobile → API Gateway → services |
| Asynchronous domain events (NATS) | Cross-context reactions where the producer doesn't need to know who consumes | `SoilMoistureLow` → Irrigation, Alerts, AI Platform |
| Device protocols (MQTT/Modbus/LoRaWAN) | Field device telemetry and commands | Sensors/pumps ↔ Edge Gateway ↔ IoT Service |
| WebSocket/SSE | Live push to an open UI session | Live telemetry on the 3D twin viewer, live dashboard updates |
| Provider-abstracted outbound calls | External services the platform depends on but must not be locked to | Weather, LLM, LINE/SMS, drone-imagery ingestion |

No context calls another context's database directly, and no client calls a service's database directly — every path in the table above is API/event/protocol, matching architecture principle #3–4.

## 2. API contract standards

- All REST endpoints are documented via OpenAPI, versioned under `/api/v1/...` (per the platform brief §41's example paths: `/api/v1/farms`, `/api/v1/twins`, `/api/v1/sensors`, `/api/v1/telemetry`, `/api/v1/cameras`, `/api/v1/vision-events`, `/api/v1/irrigation`, `/api/v1/fertigation`, `/api/v1/diseases`, `/api/v1/harvest`, `/api/v1/assets`, `/api/v1/work-orders`, `/api/v1/inventory`, `/api/v1/procurement`, `/api/v1/finance`, `/api/v1/ai`, `/api/v1/alerts`).
- Breaking changes require a new version prefix (`/api/v2/...`); v1 stays live through a documented deprecation window — no silent breaking changes to a live version.
- Every list endpoint supports pagination, filtering, sorting, and search using a consistent query-parameter convention across all services (not each service inventing its own).
- Errors use a standard envelope (`{error: {code, message, correlation_id}}`); every response carries a correlation ID propagated from the originating request, logged at every hop (supports NFR-009).
- Today's backend (`backend/app/routers/*.py`) already uses per-entity FastAPI routers with Pydantic schemas — a reasonable starting shape; the Phase 3 work is adding the `/api/v1` prefix, the standard error envelope, and pagination/filtering conventions consistently, not restructuring the router pattern itself.

## 3. Event catalog & schema governance

- Event payloads are versioned JSON schemas (`event_type`, `schema_version`, `tenant_id`, `occurred_at`, `payload`), published to a shared schema registry location in the repo (`packages/contracts/events/`) so any consumer can integrate from the schema alone, without reading producer source (INT-002).
- Events are **notifications of fact**, not commands — a consumer reacts to `IrrigationCompleted`, it does not ask the Irrigation context "please tell me when done." This keeps contexts decoupled per the context map in [07-DOMAIN-MODEL.md §2](07-DOMAIN-MODEL.md).
- At-least-once delivery is assumed; all event consumers must be idempotent (dedupe by event ID) — this mirrors the duplicate-telemetry tolerance already required of the IoT ingestion path (IOT-003).

## 4. External integration table

| External system | Direction | Protocol | Abstraction owner | Notes |
|---|---|---|---|---|
| Weather provider | Inbound (forecast) | REST/webhook | Weather Service adapter | Combined with on-farm station data per FR-WX-001; provider is swappable behind one interface |
| LLM provider (Ollama / OpenAI-compatible / enterprise endpoint) | Outbound (inference) | REST | AI Platform Service adapter | Never called directly from business-logic code (AI-003); tenant-selectable per [ADR-006](11-ADR.md) |
| LINE / SMS / Email gateway | Outbound (notification) | REST/webhook per provider | Notification Service adapter | Delivery-channel abstraction; a channel outage degrades to remaining channels, never blocks the underlying alert from being recorded |
| Drone imagery source | Inbound (upload/ingest) | File upload / object-storage drop | Drone module (Farm Operations) | Imagery lands in object storage; downstream analysis (canopy, stress detection) is a Vision AI / AI Platform consumer of the same event, not a separate pipeline |
| Corporate ERP (optional) | Outbound (posting export) | REST or scheduled file export | Finance Service adapter | Per FIN-003 — export API, not bidirectional sync, to avoid owning GL reconciliation logic |
| PLC / pump controllers | Outbound (command) | Modbus TCP/RTU via Edge Gateway | IoT Service, gated by Agent Action Gateway ([09-SECURITY-ARCHITECTURE.md §6](09-SECURITY-ARCHITECTURE.md)) | Every command is approval-gated per BR-002/BR-003 regardless of protocol |
| Web-ifc-viewer / IFC toolchain | Internal (library, not a network integration) | N/A | apps/web | Already integrated in this repo; carried forward as-is into the target frontend per [ADR-005](11-ADR.md)/[ADR-006](11-ADR.md) |

## 5. Sync vs. async decision guide

Use **synchronous REST** when: the caller needs the result to proceed (e.g. "create this work order and show its ID"), or the operation is a simple CRUD read.
Use **asynchronous events** when: multiple unrelated contexts need to react to one fact (e.g. a harvest completing affects Finance, Inventory, and the Dashboard), or the reacting work is slow/best-effort (e.g. recomputing a health score after new telemetry).
Use **WebSocket/SSE** when: a human has an open screen that should update without polling (live telemetry on the 3D twin, live dashboard tiles) — this repo's current dashboard is poll-on-open; Phase 6/16 upgrade it to push-based per this rule.
