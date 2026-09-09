# 01 — Product Vision

**Product:** FruitTwin AI — Enterprise Orchard Digital Twin & AI Farm Management Platform
**Document status:** Draft for internal review · Phase 0 · v0.1
**Related:** [00-EXISTING-CODEBASE-ANALYSIS.md](00-EXISTING-CODEBASE-ANALYSIS.md) · [02-SCOPE.md](02-SCOPE.md) · [03-BRD.md](03-BRD.md) · [04-SRS.md](04-SRS.md) · [05-RTM.md](05-RTM.md)

---

## 1. Vision statement

FruitTwin AI gives commercial fruit-orchard operators — from a single durian farm to a multi-farm agribusiness — one connected system that mirrors every physical thing on the farm (trees, plots, sensors, pumps, machinery, workers, harvest lots) as a living **digital twin**, layers AI on top of that twin to turn raw field data into irrigation, fertigation, disease, yield, and maintenance decisions, and closes the loop into the farm's own operations, inventory, and accounting — so that agronomic decisions and financial decisions are made from the same numbers, not reconciled after the fact.

The platform starts with seven Thai commercial fruit crops (durian, rambutan, mangosteen, longkong, lychee, maprang, mayongchid) grown from an existing IFC-based 3D digital-twin viewer prototype (this repository), and is architected — crop configuration, multi-tenancy, edge/offline operation — so that neither adding an eighth crop nor an eighth farm requires rewriting core logic.

## 2. Business goals

| Goal | Why it matters | How the platform addresses it |
|---|---|---|
| Reduce input cost per kg of fruit (water, fertilizer, chemical, labor, energy) | Input costs are the largest controllable cost in commercial orchards | Crop/growth-stage-aware irrigation & fertigation planning against live soil/weather data instead of fixed calendars |
| Reduce yield loss from late-detected disease and pest pressure | Disease outbreaks caught late cost entire plots, not single trees | Vision AI + risk-engine early detection, tied to a governed treatment workflow with human sign-off |
| Reduce unplanned machinery downtime during harvest-critical periods | A failed pump or generator during flowering/fruit-set has outsized yield impact | Condition monitoring → predictive maintenance → scheduled work orders before failure |
| Give management profitability visibility down to the plot/tree/row level, not just farm-level | Enterprise decisions (replant, re-crop, invest, divest) need unit economics, not farm totals | Cost-dimension accounting tied to the same spatial hierarchy as the agronomic data |
| Preserve full traceability from consumer-facing fruit back to the tree and treatment history | Export markets and premium buyers increasingly require chain-of-custody proof | QR/lot traceability chained through Harvest Lot → Plot → Tree → Farm, with append-only history |
| Let a farm operate normally when connectivity drops | Orchards are frequently in low-connectivity rural areas | Edge-first architecture: local MQTT/rules/inference, store-and-forward sync, offline-capable mobile PWA |
| Keep AI recommendations advisory-by-default and physical/financial actions human-approved | An AI-issued pesticide application or irrigation command that goes wrong is a safety and liability risk, not just a UX bug | Agent action levels L0–L4 (§30 of the platform brief), deterministic business-rule + permission gates in front of every physical/financial command |

## 3. Stakeholders

| Stakeholder | Interest | Influence |
|---|---|---|
| Farm Owner / Investor | ROI, plot-level profitability, risk exposure | High |
| Farm Manager | Day-to-day operations, labor allocation, target attainment | High |
| Agronomist | Crop health, agronomic rule accuracy, treatment efficacy | High |
| Field Supervisor / Worker | Task clarity, ease of mobile use, offline reliability | Medium (adoption-critical) |
| Maintenance Engineer | Equipment uptime, work order clarity, spare parts availability | Medium |
| Warehouse / Procurement Officer | Stock accuracy, reorder timing, vendor terms | Medium |
| Finance / Cost Controller | Cost allocation accuracy, budget vs actual, auditability | High |
| Tenant Admin (multi-farm org) | User/role administration, cross-farm reporting, billing | Medium |
| Platform Super Admin (SaaS operator) | Platform stability, tenant isolation, security posture | High |
| Auditor / Compliance | Traceability, audit trail completeness, AI governance evidence | Medium |
| Export Buyer / Certification Body (indirect) | Traceability proof, treatment records | Low (system must satisfy them, doesn't use the system directly) |
| Device/Sensor vendors, LLM providers, weather API providers (integration partners) | Stable, documented integration contracts | Low |

## 4. Personas

### 4.1 Somchai — Farm Owner
Owns a 200-rai durian and mangosteen operation across 2 farms. Wants a single dashboard showing farm health, forecast yield, and season-to-date profit without visiting each plot. Reviews high-value approvals (large purchases, chemical treatments, asset disposal) from his phone. Not deeply technical — needs the Command Center and mobile approvals to be legible at a glance, in Thai.

### 4.2 Nok — Farm Manager
Runs daily operations for one farm. Assigns field tasks, reviews irrigation/fertigation recommendations before they execute, escalates disease alerts to the agronomist, and is the primary user of the 3D/GIS map and work-order board. Needs fast task assignment and a clear view of what's overdue.

### 4.3 Dr. Preecha — Agronomist (consulting, multi-farm)
Reviews AI-flagged disease observations, confirms/rejects Vision AI predictions, authors treatment plans, and tunes crop/variety agronomic rules (soil moisture targets, fertilizer recipes) per farm. Needs evidence (photos, sensor trends, confidence scores) attached to every AI claim before he'll act on it — will not trust a bare AI verdict.

### 4.4 Ban — Field Worker / Harvest Crew
Uses the mobile PWA only. Receives tasks, navigates to the plot, scans a tree/lot QR code, logs harvest weight and grade, records material usage, and completes tasks — often with no signal. Needs an interface that works fully offline and syncs later, in Thai, optimized for one-handed outdoor use.

### 4.5 Wichai — Maintenance Engineer
Owns the pump house, irrigation network, and mobile machinery. Receives predictive-maintenance-triggered inspection requests, converts them into work orders, records parts consumed and labor hours, and closes out maintenance history against each asset twin.

### 4.6 Ploy — Warehouse / Procurement Officer
Manages fertilizer, chemical, spare-parts, and fuel stock across warehouses; raises purchase requests when below reorder point; receives goods against POs; issues stock against work orders and farm tasks.

### 4.7 Kanya — Finance / Cost Controller
Posts expenses and revenue against the farm/plot/crop/season cost dimensions, reconciles budget vs actual, and produces plot/tree profitability reports for ownership. Needs immutable, auditable postings and a clean integration boundary if a larger corporate ERP already owns the General Ledger.

### 4.8 Anong — Tenant Admin
Administers users, roles, and farm/organization structure for a multi-farm operator tenant. Configures crop masters, approval thresholds, and notification channels for her organization. Does not touch other tenants' data — tenant isolation must be airtight from her point of view (she should not even be able to construct a request that crosses tenants).

### 4.9 Platform Super Admin (internal/SaaS operator)
Operates the platform across all tenants: onboarding, capacity, security patching, model registry governance, incident response. Needs cross-tenant observability without cross-tenant *data* access by default.

## 5. Glossary

| Term | Definition |
|---|---|
| Twin ID | Immutable internal identifier for any physical/logical object in the digital twin graph, e.g. `FARM01-DUR-A-R03-T025`; distinct from a user-facing, editable code |
| Digital Twin | The generic entity/graph representation (state, telemetry, relationships, events) of a physical or logical object — a tree, pump, valve, camera, tank, or building |
| Plot / Block / Row / Tree | The spatial hierarchy under a Farm/Zone used to scope agronomy, IoT, and cost data: `Tenant → Organization → Farm → Zone → Plot → Block → Row → Tree` |
| Health Score | A 0–100 composite score (with a good/warning/critical band) summarizing an asset's or tree's current condition, always accompanied by contributing metrics and recommendations — never a bare number |
| Growth Stage | A crop/variety-specific phenological stage (e.g. flowering, fruit-set, maturity) driving which agronomic rules currently apply |
| Rule/Model provenance | The requirement that every AI or rule-engine output records model/rule name, version, timestamp, confidence (where applicable), and source data, so a human can audit *why* a recommendation was made |
| Agent action level (L0–L4) | Governance classification for AI/agent actions: L0 read-only, L1 recommendation, L2 prepare transaction, L3 execute after human approval, L4 automatic within pre-approved policy — high-risk actions (chemical application, large irrigation, procurement, financial posting, deletion, device configuration) may never run above L2 without an explicit, auditable policy grant |
| Twin Graph | The relationship layer connecting twins (e.g. `Tree LOCATED_IN Plot`, `Valve SUPPLIED_BY Pump`) used for impact analysis and navigation |
| Harvest Lot / Packing Lot | Traceability units linking harvested fruit back through plot/tree/farm to a consumer-facing QR code |
| RPO / RTO | Recovery Point/Time Objective — maximum tolerable data loss / downtime in a disaster-recovery scenario |
