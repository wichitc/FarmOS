# 06 — Enterprise Architecture (Phase 1)

**Document status:** Draft for internal review · Phase 1 · v0.1
**Related:** [02-SCOPE.md](02-SCOPE.md) · [03-BRD.md](03-BRD.md) · [04-SRS.md](04-SRS.md) · [07-DOMAIN-MODEL.md](07-DOMAIN-MODEL.md) · [08-DATA-ARCHITECTURE.md](08-DATA-ARCHITECTURE.md) · [09-SECURITY-ARCHITECTURE.md](09-SECURITY-ARCHITECTURE.md) · [10-INTEGRATION-ARCHITECTURE.md](10-INTEGRATION-ARCHITECTURE.md) · [11-ADR.md](11-ADR.md)

No business-feature coding proceeds on top of this document until it — and its companion architecture documents — have been reviewed. This document uses the C4 model (Context → Container → Component → Code) for the structural views, per [02-SCOPE.md](02-SCOPE.md) and the requirements in [03-BRD.md](03-BRD.md)/[04-SRS.md](04-SRS.md).

---

## 1. Architecture principles

These constrain every decision below and every later phase; they are not aspirational.

1. **Domain-Driven Design** — bounded contexts (see [07-DOMAIN-MODEL.md](07-DOMAIN-MODEL.md)) own their own data; no context reaches directly into another's tables.
2. **Modular monolith first, microservice-ready boundaries** — Phase 3–9 ship as a small number of deployable services grouped by bounded-context cohesion (not one service per entity), each internally structured so it *could* be split later without a rewrite (Clean Architecture layering inside each service — see §4).
3. **API-first** — every capability is reachable via a documented OpenAPI contract before a UI consumes it (INT-001).
4. **Event-driven where state changes matter to other contexts** — synchronous REST for request/response, published domain events for cross-context reactions (INT-002).
5. **Configuration-driven business logic** — crop rules, thresholds, approval limits are tenant-configurable data, not code (FR-PLT-010, FR-FARM-003).
6. **Multi-tenant from the first schema** — every table carries `tenant_id`; isolation enforced at the data-access layer (SEC-003), decided in [ADR-007](11-ADR.md).
7. **Offline-capable edge** — field devices and mobile workers function disconnected and reconcile later (NFR-006); this is a first-class architectural concern, not a mobile-team afterthought.
8. **Zero Trust** — every request is authenticated and authorized server-side regardless of network origin (SEC-002); no implicit trust from being "inside" the network.
9. **RBAC + ABAC** — role grants a capability, scope (tenant/farm/plot) constrains where it applies (FR-PLT-004).
10. **Auditability by construction** — the audit trail is a platform service every write path calls through, not a per-feature afterthought (FR-PLT-007, BR-004).
11. **Observability by construction** — every service ships `/health`, `/ready`, `/metrics`, and structured logs from day one (NFR-005/009), not bolted on before go-live.
12. **i18n from the data model up** — user-facing strings (crop names, disease names, UI copy) are resolved through a localization layer for Thai/English, not hardcoded in either language (NFR-007).
13. **No cloud-provider lock-in** — infrastructure primitives (object storage, container runtime, secrets) are abstracted behind interfaces satisfiable by on-prem, any major cloud, or hybrid (per [02-SCOPE.md §2](02-SCOPE.md)).

## 2. C4 Level 1 — System Context

```mermaid
flowchart TB
    Owner["Farm Owner"]
    Manager["Farm Manager"]
    Agronomist["Agronomist"]
    Worker["Field Worker\n(mobile PWA)"]
    MaintEng["Maintenance Engineer"]
    WarehouseOfficer["Warehouse / Procurement"]
    Finance["Finance / Cost Controller"]
    TenantAdmin["Tenant Admin"]

    subgraph FT["FruitTwin AI Platform"]
        SYS["Orchard Digital Twin &\nAI Farm Management Platform"]
    end

    Weather["Weather Provider API"]
    LLM["LLM Provider\n(Ollama / OpenAI-compatible)"]
    Msg["LINE / SMS / Email Gateway"]
    Drone["Drone Imagery Source"]
    Sensors["Field Sensors / Weather Stations\n(via Edge Gateway + MQTT/Modbus)"]
    Cameras["CCTV / Vision Cameras"]
    Machinery["Pumps / Valves / PLC\n(via Edge Gateway)"]
    ERP["Corporate ERP\n(optional, GL integration)"]

    Owner -->|"web + mobile"| SYS
    Manager -->|"web + mobile"| SYS
    Agronomist -->|"web"| SYS
    Worker -->|"mobile PWA, often offline"| SYS
    MaintEng -->|"web + mobile"| SYS
    WarehouseOfficer -->|"web"| SYS
    Finance -->|"web"| SYS
    TenantAdmin -->|"web"| SYS

    SYS -->|"forecast fetch"| Weather
    SYS -->|"inference calls"| LLM
    SYS -->|"notifications"| Msg
    SYS -->|"imagery ingest"| Drone
    Sensors -->|"telemetry"| SYS
    Cameras -->|"RTSP / frames"| SYS
    SYS -->|"commands, approval-gated"| Machinery
    SYS <-->|"posting export"| ERP
```

## 3. C4 Level 2 — Container Diagram

```mermaid
flowchart TB
    subgraph Client["Client Tier"]
        WEB["apps/web\nNext.js/React/TS\n(carries forward this repo's\nIFC-viewer interaction model)"]
        PWA["apps/mobile-pwa\nOffline-first PWA"]
    end

    GW["API Gateway / BFF\n(authn, rate limit, request routing)"]

    subgraph Core["Core Platform Services (modular monolith, bounded-context aligned)"]
        IDN["Identity & Tenant Service\n(IAM, RBAC/ABAC, Audit, Workflow, Notification)"]
        FARM["Farm & Crop Service\n(hierarchy, crop/variety master, season)"]
        TWIN["Digital Twin Service\n(twin core, graph, IFC/3D binding —\nevolves this repo's backend/app)"]
        GIS["GIS Service\n(PostGIS spatial queries, layers)"]
        IOTSVC["IoT Service\n(device registry, rules engine)"]
        AGRI["Farm Operations Service\n(irrigation, fertigation, crop health,\nyield/harvest, farm work)"]
        ASSET["Asset & Maintenance Service\n(evolves this repo's Equipment/health.py)"]
        SUPPLY["Inventory & Procurement Service"]
        FIN["Finance Service\n(cost/revenue/profitability)"]
        AI["AI Platform Service\n(model registry, copilot, agent orchestration)"]
        VISIONSVC["Vision AI Service\n(camera ingest, inference, review workflow)"]
    end

    subgraph Edge["Edge Tier (per farm site)"]
        EDGEGW["Edge Gateway\nlocal MQTT broker, local rules,\nlocal inference, store-and-forward"]
    end

    subgraph Data["Data Tier"]
        PG[("PostgreSQL + PostGIS\ntransactional + spatial")]
        TS[("TimescaleDB\ntelemetry")]
        REDIS[("Redis\ncache/session")]
        OBJ[("S3-compatible / MinIO\nfiles, IFC models, images")]
        BUS(["Event Bus\nNATS"])
        VEC[("Vector store\nRAG copilot, optional")]
    end

    WEB --> GW
    PWA -->|"sync when online"| GW
    GW --> IDN & FARM & TWIN & GIS & IOTSVC & AGRI & ASSET & SUPPLY & FIN & AI & VISIONSVC

    IDN & FARM & TWIN & GIS & AGRI & ASSET & SUPPLY & FIN --> PG
    IOTSVC --> TS
    TWIN --> OBJ
    VISIONSVC --> OBJ
    AI --> VEC
    IDN --> REDIS

    IOTSVC & AGRI & ASSET & VISIONSVC & AI -.->|publish/subscribe domain events| BUS

    EDGEGW <-->|"MQTT / Modbus, TLS"| IOTSVC
    EDGEGW <-->|"RTSP / frame upload"| VISIONSVC
    Sensors2["Sensors / Pumps / Valves"] --> EDGEGW
    Cameras2["Cameras"] --> EDGEGW
```

**Mapping to today's code:** `Digital Twin Service` and `Asset & Maintenance Service` are where this repo's existing FastAPI backend (`backend/app/`) and frontend (`src/`) land — see [00-EXISTING-CODEBASE-ANALYSIS.md §4](00-EXISTING-CODEBASE-ANALYSIS.md). Every other container in this diagram is new build.

## 4. C4 Level 3 — Component view (representative: Digital Twin Service)

Every core service follows the same Clean-Architecture layering; the Digital Twin Service is shown as the representative example since it's the one with existing code to evolve.

```mermaid
flowchart LR
    subgraph API["API Layer"]
        REST["REST routers\n(twins, telemetry, relationships,\nIFC upload/serve)"]
        WS["WebSocket/SSE\n(live telemetry, twin state push)"]
    end
    subgraph App["Application Layer"]
        CMD["Command handlers\n(CreateTwin, PlaceTwin, UpdateState,\nRecordTelemetry)"]
        QRY["Query handlers\n(GetTwin, GetGraph, GetHistory)"]
    end
    subgraph Domain["Domain Layer"]
        ENT["Entities: DigitalTwin, TwinType,\nTwinRelationship, TwinTelemetry, TwinEvent"]
        RULES["Domain rules: twin-ID immutability,\nrelationship validity, state transitions"]
    end
    subgraph Infra["Infrastructure Layer"]
        REPO["Repositories\n(SQLAlchemy / PostGIS)"]
        FILESTORE["IFC/model file store\n(object storage adapter)"]
        EVTPUB["Event publisher"]
    end

    REST --> CMD & QRY
    WS --> QRY
    CMD --> ENT
    CMD --> RULES
    QRY --> REPO
    CMD --> REPO
    CMD --> EVTPUB
    REST --> FILESTORE
```

This layering is the **direct refactor target** for `backend/app/main.py` + `routers/*.py` + `models.py` + `health.py`, which today mix API, application, and data-access concerns in each router file. The Phase 3–6 implementation task is to introduce the Application/Domain layers, not to throw away the working router/model logic.

## 5. C4 Level 3 — Deployment Architecture

```mermaid
flowchart TB
    subgraph CloudRegion["Cloud / On-Prem Region"]
        subgraph K8s["Kubernetes cluster (or docker-compose for small/on-prem)"]
            SVCPODS["Core service pods\n(one deployment per container from §3)"]
            GWPOD["API Gateway pod"]
        end
        PGCLUSTER[("PostgreSQL/PostGIS\nprimary + replica")]
        TSCLUSTER[("TimescaleDB")]
        REDISNODE[("Redis")]
        OBJSTORE[("Object storage")]
        BUSNODE(["NATS cluster"])
        OBS["Observability stack\nPrometheus + Grafana + OTel collector"]
    end

    subgraph FarmSite["Farm Site (Edge)"]
        GATEWAY["Edge Gateway device\n(mini-PC / industrial gateway)\nlocal MQTT + local rules + local inference"]
        LOCALCACHE[("Local SQLite/embedded store\nstore-and-forward queue")]
        GATEWAY --> LOCALCACHE
    end

    subgraph UserDevices["User Devices"]
        BROWSER["Desktop browser (Command Center, 3D Twin)"]
        MOBILE["Mobile PWA (field workers)"]
    end

    BROWSER -->|HTTPS| GWPOD
    MOBILE -->|HTTPS, intermittent| GWPOD
    GWPOD --> SVCPODS
    SVCPODS --> PGCLUSTER & TSCLUSTER & REDISNODE & OBJSTORE & BUSNODE
    SVCPODS -.-> OBS

    GATEWAY <-->|"VPN / TLS, tolerant of drops"| GWPOD
```

Small/single-orchard deployments (this repo's current use case) run the same container images via `docker-compose` on a single on-prem host instead of Kubernetes — DEP-002.

## 6. Bounded-context-to-container mapping

See [07-DOMAIN-MODEL.md](07-DOMAIN-MODEL.md) for the full bounded-context list; each maps 1:1 or many:1 onto the containers in §3 (e.g. Irrigation, Fertigation, Crop Health, Yield/Harvest, and Farm Work contexts all live in the single "Farm Operations Service" container initially — they are split into separate services only if/when independent scaling or team ownership requires it, per principle #2).
