# 03 — Business Requirements Document (BRD)

**Document status:** Draft for internal review · Phase 0 · v0.1
**Related:** [01-VISION.md](01-VISION.md) · [02-SCOPE.md](02-SCOPE.md) · [04-SRS.md](04-SRS.md) · [05-RTM.md](05-RTM.md)

Priority key: **M**ust (MVP-blocking) · **S**hould (near-term, non-blocking) · **C**ould (later phase / nice-to-have).
Requirement IDs are stable identifiers for traceability (see [05-RTM.md](05-RTM.md)) — do not renumber; deprecate and add new IDs instead.

---

## 1. Platform Foundation — Identity, Tenant, RBAC, Workflow, Audit, Notification (`FR-PLT`)

| ID | Requirement | Pri |
|---|---|---|
| FR-PLT-001 | System shall support a `Tenant → Organization → Farm` hierarchy, with every business entity scoped to at least a tenant | M |
| FR-PLT-002 | System shall authenticate users via OAuth2/OIDC-compatible identity, MFA-ready | M |
| FR-PLT-003 | System shall enforce RBAC with the role set in [01-VISION.md §3](01-VISION.md), extensible per tenant | M |
| FR-PLT-004 | System shall support ABAC scope restriction (tenant / farm / plot) layered on top of RBAC role-permissions | M |
| FR-PLT-005 | System shall provide a generic, configurable workflow/approval engine (Draft→Submit→Review→Approve/Reject/Return/Cancel) reusable across Purchase Request, Fertilizer/Chemical Treatment Plan, Maintenance Work Order, Farm Expense, Asset Disposal | M |
| FR-PLT-006 | Approval routing shall support conditions on amount, farm, department, risk category, and item category | M |
| FR-PLT-007 | System shall record a full, append-only audit trail (actor, tenant, action, entity, entity ID, timestamp, old/new values, correlation ID) for every state-changing transaction | M |
| FR-PLT-008 | System shall deliver notifications over Web and Push at minimum, with Email/LINE/SMS as integration-ready channels | S |
| FR-PLT-009 | System shall provide a master-data service (crop, variety, disease, fertilizer, equipment-type catalogs) shared across modules rather than duplicated per module | M |
| FR-PLT-010 | System shall provide a tenant-scoped configuration service for approval thresholds, notification routing, and feature toggles | S |

## 2. Farm & Crop Domain (`FR-FARM`)

| ID | Requirement | Pri |
|---|---|---|
| FR-FARM-001 | System shall model the spatial/organizational hierarchy `Farm → Zone → Plot → Block → Row → Tree` | M |
| FR-FARM-002 | Every twin-capable object shall receive an immutable Twin ID (e.g. `FARM01-DUR-A-R03-T025`) distinct from an editable, user-facing code | M |
| FR-FARM-003 | System shall support Crop and Variety as versioned master data, decoupled from application code (§9 Crop Configuration Engine) | M |
| FR-FARM-004 | System shall support Season as a first-class entity used to scope planning, telemetry aggregation, and cost/revenue reporting | M |
| FR-FARM-005 | Each Tree twin shall record: crop, variety, planting date, estimated age, GPS, row/plot, rootstock (where applicable), height, canopy size, trunk diameter, current growth stage | M |
| FR-FARM-006 | System shall support bulk tree import (CSV/grid-spacing generation) and bulk field update | S |
| FR-FARM-007 | System shall maintain, per tree, linked history of health, irrigation, fertilization, treatment, harvest, cost, and revenue events (append-only) | M |

## 3. GIS & Spatial (`FR-GIS`)

| ID | Requirement | Pri |
|---|---|---|
| FR-GIS-001 | System shall render farm boundary, zone, plot, row, and infrastructure (roads, drains, ponds, pipes, pumps, valves, CCTV, sensors, buildings) as map layers in WGS84 | M |
| FR-GIS-002 | System shall support draw/edit of polygon, line, and point geometries with snapping | S |
| FR-GIS-003 | System shall support import of GeoJSON/KML/Shapefile farm survey data | S |
| FR-GIS-004 | System shall support satellite/drone orthophoto raster layers | S |
| FR-GIS-005 | System shall provide layer manager (visibility toggle), search, filter, measure-distance, and measure-area tools | M |
| FR-GIS-006 | System shall support bulk tree placement onto the map by spacing/grid pattern relative to a plot boundary | S |
| FR-GIS-007 | System shall perform spatial queries (e.g. "trees within 50 m of Sensor X") to support alerting and impact analysis | S |

## 4. Digital Twin & 3D (`FR-TWIN`)

*(Detailed twin data-model requirements are in [04-SRS.md §1](04-SRS.md); these are the business-facing capabilities.)*

| ID | Requirement | Pri |
|---|---|---|
| FR-TWIN-001 | System shall provide a web-based 3D orchard viewer supporting IFC (buildings/pump rooms/tanks/mechanical systems), 3D Tiles/terrain (large-scale orchard scenes), and point cloud (drone/LiDAR scans) in one hybrid scene — **building on this repo's existing IFC viewer as the IFC-rendering seed** | M |
| FR-TWIN-002 | Users shall be able to click any twin-bound object in the 3D view and see: current properties, live telemetry, alarm state, historical trend, linked CCTV, linked work orders, maintenance history, yield/cost data, and AI recommendations | M |
| FR-TWIN-003 | System shall support layer toggles for health, disease, soil moisture, irrigation, equipment, sensor, CCTV, yield, cost, revenue, profit, and alerts, each rendered with a consistent Normal/Warning/Critical/Offline/Maintenance color state | S |
| FR-TWIN-004 | System shall support click-to-place and drag-to-reposition of twin-bound objects (equipment, trees) in the 3D scene — **carrying forward this repo's existing placement/drag interaction pattern** | M |
| FR-TWIN-005 | System shall distinguish View-only and Edit modes at the user/role level, disabling placement and mutation controls in View mode — **carrying forward this repo's existing mode toggle** | M |

## 5. IoT / Sensor Platform (`FR-IOT`)

| ID | Requirement | Pri |
|---|---|---|
| FR-IOT-001 | System shall provide a device/gateway/sensor registry independent of any specific sensor vendor | M |
| FR-IOT-002 | System shall ingest telemetry via MQTT, Modbus RTU/TCP, LoRaWAN, HTTP/REST, and WebSocket, normalizing into a common telemetry schema before storage | M |
| FR-IOT-003 | System shall validate incoming telemetry (timestamp sanity, unit conversion, bad-data flagging, missing-data handling) before it reaches the digital twin or rules engine | M |
| FR-IOT-004 | System shall detect and surface sensor-offline and data-quality degradation as first-class alert conditions, not silent gaps | M |
| FR-IOT-005 | System shall provide a device simulator so irrigation/alerting/AI workflows can be developed and tested without physical hardware | M (dev/test enabler) |
| FR-IOT-006 | System shall support device calibration records tied to each sensor's history | S |

## 6. Irrigation & Fertigation (`FR-IRR`, `FR-FERT`)

| ID | Requirement | Pri |
|---|---|---|
| FR-IRR-001 | System shall model the physical water network (source, reservoir/pond/tank, pump, pipe network, zone, valve, sprinkler/drip) as connected twins | M |
| FR-IRR-002 | System shall generate irrigation recommendations from crop/variety/age/growth-stage, current soil moisture, recent and forecast rainfall, ET, humidity, temperature, and prior irrigation history | M |
| FR-IRR-003 | System shall support manual, scheduled, rule-based, and AI-recommended irrigation, with an explicit approval-before-execution mode as the default | M |
| FR-IRR-004 | Automated irrigation execution shall enforce safety limits: max runtime, dry-run protection, pressure check, valve-confirmation, emergency stop, and manual override, with every command traceable to an actor (human or agent + approval record) | M |
| FR-FERT-001 | System shall maintain a fertilizer master (composition, chemical properties, stock linkage) and generate fertigation plans from crop/variety/age/growth-stage/soil-analysis/leaf-analysis/target-yield/historical-yield/current-weather | M |
| FR-FERT-002 | System shall record Plan-vs-Actual fertigation application down to farm/plot/row/tree granularity, including N/P/K/Ca/Mg/S/micronutrient breakdown | M |
| FR-FERT-003 | Every AI fertigation recommendation shall display its reason, supporting data, confidence, and stated limitations — never a bare number | M |

## 7. CCTV & Vision AI (`FR-CCTV`)

| ID | Requirement | Pri |
|---|---|---|
| FR-CCTV-001 | System shall register cameras (RTSP/ONVIF where available) with position and field-of-view metadata | S |
| FR-CCTV-002 | Vision pipeline shall support tree-health/leaf-discoloration, fruit detection/counting/size estimation, maturity estimation, disease-symptom detection, intrusion detection, worker-safety, and vehicle detection use cases as independently deployable models | S |
| FR-CCTV-003 | Every vision prediction shall store model name, version, timestamp, source frame, confidence, detected class, bounding box, source camera, and associated tree/plot | M (once vision AI ships) |
| FR-CCTV-004 | A human-review workflow shall confirm or reject every AI disease/pest observation before it can create a Disease Incident | M |
| FR-CCTV-005 | An AI disease diagnosis shall never, by itself, trigger a pesticide/chemical application — treatment requires a human-approved Treatment Plan (see FR-HEALTH-003) | M |

## 8. Drone (`FR-DRONE`)

| ID | Requirement | Pri |
|---|---|---|
| FR-DRONE-001 | System shall support drone mission/route definition and imagery upload | C |
| FR-DRONE-002 | Drone imagery shall be usable as input to tree inventory reconciliation, missing-tree detection, canopy analysis, and stress/disease detection | C |

## 9. Crop Health & Disease (`FR-HEALTH`)

| ID | Requirement | Pri |
|---|---|---|
| FR-HEALTH-001 | System shall model disease lifecycle: Detected → Suspected → Inspection Required → Confirmed → Treatment Planned → Treatment Applied → Monitoring → Resolved | M |
| FR-HEALTH-002 | A risk engine shall combine weather, humidity, rainfall, leaf wetness, soil condition, historical outbreak data, and Vision AI observations into a disease-risk signal per plot | S |
| FR-HEALTH-003 | Treatment Plans shall require human approval before execution and shall be linked to a Farm Work task for the applying worker | M |
| FR-HEALTH-004 | Every disease/risk recommendation shall display confidence and supporting evidence | M |

## 10. Yield & Harvest (`FR-YIELD`, `FR-HARV`)

| ID | Requirement | Pri |
|---|---|---|
| FR-YIELD-001 | System shall track the fruit lifecycle (Flowering → Pollination → Fruit Set → Fruit Growth → Maturity → Harvest) with counts/estimates rolled up Tree → Row → Plot → Farm → Crop → Season | S |
| FR-YIELD-002 | Yield and harvest-date predictions shall be expressed as a range/confidence interval, never a single point number | M (once yield AI ships) |
| FR-HARV-001 | System shall support Harvest Plan → Task → Batch → Lot → Receipt → Grade → Packing Lot with QR/Barcode/RFID support | S |
| FR-HARV-002 | Consumer-facing traceability shall resolve QR → Packing Lot → Harvest Lot → Plot → Tree → Farm | S |

## 11. Farm Work Management (`FR-WORK`)

| ID | Requirement | Pri |
|---|---|---|
| FR-WORK-001 | System shall support work types: irrigation, fertilization, pruning, spraying, mowing, disease inspection, harvesting, equipment inspection, maintenance, cleaning | M |
| FR-WORK-002 | Work lifecycle: Request → Plan → Assign → Accept → Execute → Evidence → Complete → Supervisor Review → Close | M |
| FR-WORK-003 | Mobile workers shall be able to receive tasks, navigate to location, scan QR, capture photos/measurements, log materials/labor, and complete tasks fully offline, syncing on reconnect | M |

## 12. Asset & Machinery (`FR-ASSET`)

| ID | Requirement | Pri |
|---|---|---|
| FR-ASSET-001 | System shall register assets (tractor, mower, sprayer, pump, generator, tank, vehicle, drone, CCTV, sensor, valve, injector) with type, manufacturer, model, serial, install date, warranty, location, meter/runtime, condition, and linked documents/photos — **extending this repo's existing 10-type equipment catalog and position/condition model, which is a working seed** | M |
| FR-ASSET-002 | System shall support asset meter/runtime tracking usable as an input to maintenance scheduling | S |

## 13. Maintenance & Predictive Maintenance (`FR-MNT`, `FR-PDM`)

| ID | Requirement | Pri |
|---|---|---|
| FR-MNT-001 | System shall support corrective, preventive, predictive, and condition-based maintenance strategies per asset | M |
| FR-MNT-002 | System shall provide MaintenanceRequest → (approval) → WorkOrder → Inspection/parts/labor recording → MaintenanceHistory | M |
| FR-PDM-001 | System shall compute an anomaly score / failure probability / recommended action / confidence from asset condition signals (vibration, temperature, current, voltage, pressure, flow, runtime) — **this repo's `health.py` rule-based score/band/recommendation engine is the interim implementation contract; it is expected to be replaced by a real ML model behind the same output shape, not rewritten from scratch** | M |
| FR-PDM-002 | Predictive-maintenance output shall always distinguish Prediction, Recommendation, and Approved Action as separate, separately-audited states | M |

## 14. Inventory & Procurement (`FR-INV`, `FR-PROC`)

| ID | Requirement | Pri |
|---|---|---|
| FR-INV-001 | System shall manage item master, UOM, warehouse/bin, lot/expiry, receipt/issue/transfer/return/adjustment/cycle-count, reservation, min/max reorder point, and valuation for fertilizer, chemicals, spare parts, fuel, lubricant, tools, PPE, packaging | S |
| FR-INV-002 | Inventory usage shall be linkable to Work Order, Farm Task, Plot, Asset, Crop, and Season for cost attribution | S |
| FR-PROC-001 | System shall support Purchase Request → Approval → RFQ → Vendor Comparison → PO → Receiving → Inspection → Inventory → Invoice Matching | S |

## 15. Farm Accounting & Profitability (`FR-ACC`, `FR-PROF`)

| ID | Requirement | Pri |
|---|---|---|
| FR-ACC-001 | System shall post revenue and expense against accounting dimensions: Farm, Zone, Plot, Crop, Variety, Tree, Season, Harvest Lot, Asset, Activity, Cost Center | S |
| FR-ACC-002 | System shall support accrual, payment, receipt, budget, actual, and variance postings, with an explicit integration API rather than a duplicated General Ledger where a corporate ERP already owns the GL | S |
| FR-PROF-001 | System shall compute profitability (Revenue − direct labor/fertilizer/chemical/water/energy/machinery/maintenance − allocated overhead) at Tree/Row/Plot/Crop/Farm/Season level with configurable cost-allocation methods | S |
| FR-PROF-002 | Dashboard shall render a profit heatmap over the spatial hierarchy | S |

## 16. Sales & Customer (`FR-SALES`)

| ID | Requirement | Pri |
|---|---|---|
| FR-SALES-001 | System shall support Customer, Contract, Quotation, Sales Order, Delivery, Invoice, Payment records, with seasonal contracts against expected harvest allocation | C |

## 17. AI/ML Platform, Copilot, Agents (`FR-AIML`, `FR-COPILOT`, `FR-AGENT`)

| ID | Requirement | Pri |
|---|---|---|
| FR-AIML-001 | System shall maintain an AI Model Registry (model, version, training dataset, deployment, inference, prediction, metric, feedback) shared across disease/yield/harvest-date/irrigation/fertilizer/anomaly/failure/forecast models | S |
| FR-COPILOT-001 | The AI Copilot shall answer operational questions only from real platform data, never fabricated values, and shall cite source data, timestamp, and confidence where relevant | M (once copilot ships) |
| FR-AGENT-001 | Agents shall follow Observe → Analyze → Recommend → Request Approval → Execute Allowed Action → Verify → Record Audit Trail | M |
| FR-AGENT-002 | Agent actions shall be classified L0 (read-only) through L4 (automatic within approved policy); pesticide application, pump activation beyond safe threshold, procurement, financial posting, deletion, and device configuration shall never execute above L2 (prepare transaction) without an explicit, auditable policy grant | M |

## 18. Alerts & Notification (`FR-ALERT`)

| ID | Requirement | Pri |
|---|---|---|
| FR-ALERT-001 | System shall generate alerts across sensor, disease, weather, irrigation, maintenance, inventory, crop, finance, security, and workflow domains with severity Info/Low/Medium/High/Critical | M |
| FR-ALERT-002 | Alerts shall support acknowledgement, assignment, escalation, SLA timing, and resolution tracking | S |

## 19. Weather & External Data (`FR-WX`)

| ID | Requirement | Pri |
|---|---|---|
| FR-WX-001 | System shall combine external weather-provider forecast data with on-farm station measurements, tagging each reading with its source, and shall never overwrite an observed reading with forecast data | M |

## 20. Executive Command Center (`FR-DASH`)

| ID | Requirement | Pri |
|---|---|---|
| FR-DASH-001 | Dashboard shall present interactive map, 3D twin, farm health score, weather, soil moisture, disease risk, irrigation status, yield forecast, harvest forecast, equipment health, work orders, inventory, financial KPIs, and AI recommendations as configurable widgets | S |
| FR-DASH-002 | Widgets shall be drag-and-drop configurable and layouts shall be savable per user | C |
| FR-DASH-003 | A fleet/equipment health summary view (stat tiles + distribution + sortable table + click-to-focus-in-3D) shall be provided from MVP — **carrying forward this repo's existing dashboard overlay pattern as the starting UI** | M |

## 21. Mobile / PWA (`FR-MOB`)

| ID | Requirement | Pri |
|---|---|---|
| FR-MOB-001 | Mobile PWA shall support task execution, inspection, QR/barcode scan, photo capture, GPS tagging, harvest recording, material issue, and maintenance recording | M |
| FR-MOB-002 | Mobile PWA shall operate fully offline via local storage + transaction queue + sync service with conflict resolution, and shall show sync status to the user | M |

---

## 22. Cross-cutting business rules (`BR`)

| ID | Rule |
|---|---|
| BR-001 | AI/ML/rule-engine output is advisory only unless an explicit tenant policy grants execution rights; the default for every new recommendation type is advisory |
| BR-002 | Pesticide/chemical application, large irrigation actions, financial transactions, procurement, asset disposal, and critical equipment commands always require human approval (L3), regardless of AI confidence |
| BR-003 | No LLM free-text output may directly drive a physical command; every AI/agent command must pass deterministic business-rule and permission checks before execution |
| BR-004 | Telemetry, audit records, approval history, financial postings, AI predictions, and maintenance history are append-only; corrections are recorded as new entries that preserve the original, never as silent overwrites/deletes |
| BR-005 | Forecast/external data may never overwrite an on-farm observed measurement for the same timestamp/metric |
| BR-006 | Every twin-bound object carries an immutable Twin ID; user-facing display codes may change without affecting the Twin ID or breaking historical references |
| BR-007 | A tenant's users, farms, and data shall never be reachable, even accidentally, from another tenant's session or query — enforced at the data-access layer, not only the UI |
| BR-008 | Every prediction/recommendation surfaced to a user shall carry model/rule name, version, and timestamp; confidence shall be shown wherever the underlying method produces one |
