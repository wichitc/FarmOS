# 02 — Project Scope

**Document status:** Draft for internal review · Phase 0 · v0.1
**Related:** [01-VISION.md](01-VISION.md) · [03-BRD.md](03-BRD.md) · [04-SRS.md](04-SRS.md) · [05-RTM.md](05-RTM.md)

---

## 1. Crop scope

**In scope at launch (configurable, not hardcoded — §9 Crop Configuration Engine):**
Durian, Rambutan, Mangosteen, Longkong, Lychee, Maprang, Mayongchid.

Variety-level configuration (e.g. Monthong/Chanee/Kanyao durian) is in scope from day one — the crop master must support Crop → Variety from the first release, not be retrofitted.

Adding an 8th+ crop must require only: a new `Crop`/`Variety` configuration record, a `TreeType` 3D representation, and versioned agronomic rule sets — **no core application code change**. This constraint is itself a Phase-1 architecture acceptance criterion, not just a Phase-0 aspiration.

## 2. Deployment-model scope

All five target deployment models are in architectural scope from Phase 1 (multi-tenant schema, edge sync design), but are **realized incrementally**:

| Deployment model | Phase realized |
|---|---|
| Single orchard (this repo's current use case) | Already partially realized; hardened in Phase 3–4 |
| Multi-farm organization | Phase 4 (Farm/Zone/Plot hierarchy) + Phase 3 (tenant/org model) |
| Agricultural enterprise (multi-org under one legal entity) | Phase 3 (tenant hierarchy) |
| Multi-tenant SaaS | Phase 3 (tenant isolation) — full SaaS billing/self-serve onboarding is a later, explicitly out-of-scope-for-v1 concern (see §4) |
| On-prem / Cloud / Hybrid Cloud+Edge | Architectural principle from Phase 1 onward (no cloud-provider lock-in); edge sync implemented Phase 7 (IoT) and Phase 17 (Mobile/PWA) |

## 3. Functional modules in scope

Grouped by delivery phase (see [05-RTM.md](05-RTM.md) for the full requirement-to-phase mapping):

| Category | Modules | Target phase(s) |
|---|---|---|
| Platform Foundation | Identity/IAM, Tenant/Org, RBAC+ABAC, Audit Trail, Master Data, Configuration, Workflow/Approval Engine, Notification | 3 |
| Farm & Crop Domain | Farm/Zone/Plot/Block/Row/Tree hierarchy, Crop/Variety master, Season | 4 |
| GIS & Spatial | Farm map, GIS layers, spatial query, drone imagery reference | 5 |
| Digital Twin & 3D | Twin Core (generic twin/graph), 3D viewer (IFC + 3D Tiles + point cloud), object-to-twin binding | 6 |
| IoT | Device registry, sensors, gateway, MQTT ingestion, TimescaleDB, rules engine, device alerts, simulator | 7 |
| Irrigation & Fertigation | Water network model, irrigation planning/execution, fertigation planning/execution, safety interlocks | 8 |
| Vision AI & CCTV | Camera registry, vision pipeline, event/observation review workflow, model registry | 9 |
| Crop Health / Disease | Disease master, incident lifecycle, treatment plans, risk engine | 10 |
| Yield & Harvest | Fruit lifecycle tracking, yield prediction, harvest planning/execution, traceability (QR/lot) | 11 |
| Asset & Maintenance | Asset registry, corrective/preventive/predictive maintenance, work orders | 12 |
| Inventory & Procurement | Warehouse/stock, purchase request→PO→receiving workflow | 13 |
| Financial Management | Cost/expense/revenue posting by farm dimension, budget vs actual, tree/plot profitability | 14 |
| AI Copilot & Agents | Model registry, conversational copilot (RAG over real platform data), governed agent orchestration (L0–L4) | 15 |
| Executive Dashboard | Configurable command center (map + 3D twin + KPIs + AI recommendations) | 16 |
| Mobile / PWA | Offline-capable field worker app | 17 |
| Cross-cutting hardening | Security, performance, DR, offline/edge testing | 18 |

## 4. Business capability map

```
Platform Services        Farm Operations           Intelligence              Enterprise Back-Office
├─ Identity/IAM          ├─ Farm/Crop Domain        ├─ Digital Twin Core      ├─ Inventory & Warehouse
├─ Tenant/Org            ├─ GIS/Spatial             ├─ 3D/GIS Viewer          ├─ Procurement
├─ Workflow/Approval     ├─ Irrigation/Fertigation  ├─ IoT Platform           ├─ Farm Accounting
├─ Notification/Alert    ├─ Crop Health/Disease     ├─ Vision AI              ├─ Tree/Plot Profitability
├─ Audit                 ├─ Yield/Harvest           ├─ AI/ML Model Registry   ├─ Sales & Customer
├─ Master Data           ├─ Asset & Maintenance     ├─ AI Copilot             └─ (Integration boundary to
├─ Document              ├─ Farm Work Management    └─ Agentic AI Orchestration    a corporate ERP where one
└─ Configuration         └─ Mobile/PWA Field App                                    already exists — §25)

                          Executive Command Center (cross-cutting, consumes all of the above)
```

## 5. Out of scope (v1 platform)

Explicitly excluded from the initial platform build — either because the master brief marks them "future-ready" rather than required, or because they introduce disproportionate risk/cost for the initial commercial-orchard use case:

| Item | Rationale |
|---|---|
| Full general-ledger / statutory financial accounting | §25 explicitly directs a management-accounting layer with an *integration API* to a corporate ERP's GL where one exists, not a GL replacement |
| Payment gateway / online payment processing | Not in the master brief's functional scope; sales/invoicing is in scope, payment *execution* is not |
| Public marketplace, exporter, or packing-house multi-party platform | §27 marks these "future-ready," not v1 deliverables |
| Native (App Store/Play Store) mobile builds | §39 specifies Mobile/PWA; native app wrapping is a later decision, not a v1 requirement |
| Drone flight-control / autopilot firmware | §15 scopes drone *mission management and imagery ingestion*, not building flight-control software — integration with existing drone platforms only |
| PLC/SCADA vendor-specific configuration tooling | Platform integrates via Modbus/MQTT; it does not replace a PLC vendor's own engineering tools |
| Automatic (unapproved) execution of chemical treatment, large irrigation, procurement, financial posting, asset disposal, or device configuration by AI agents | §60/§59 mandates human approval (L3) for these regardless of model confidence — full L4 autonomy for these categories is explicitly out of scope for v1 and requires a deliberate future policy decision, not a default |
| Non-Thai/English localization | §2 scopes Thai + English only |
| Multi-cloud active-active geo-redundancy | On-prem/cloud/hybrid is in scope; active-active multi-region DR is a maturity level beyond v1 (see NFR/DR targets in [04-SRS.md](04-SRS.md)) |
| Self-serve SaaS billing/subscription management | Multi-tenant *data* isolation is in scope; commercial SaaS billing tooling is not part of the platform's functional modules |

## 6. MVP boundary

The smallest end-to-end slice that proves the platform's core thesis (twin + IoT + AI recommendation + human approval + cost impact, closing the loop described in the brief's §55 sample scenario) is:

**Phase 3 (Foundation) → Phase 4 (Farm/Crop) → Phase 6 (Digital Twin/3D, building on this repo's IFC viewer) → Phase 7 (IoT, with a simulator standing in for real hardware) → Phase 8 (Irrigation, manual-approval mode only) → Phase 16 (a minimal Command Center).**

Vision AI, full financial management, procurement, and agentic autonomy are valuable but are **not** required to prove the core thesis and are sequenced after the MVP per the phase plan in [05-RTM.md](05-RTM.md).
