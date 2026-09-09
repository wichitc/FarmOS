"""Permission catalog and default role grants.

Permissions are `module.feature.action` strings (per the platform brief's
§34 shape) stored as data in the `permissions` table, not a code enum - new
modules add rows here as they land in later phases (FR-PLT-009: master data
is shared platform config, not per-feature hardcoding). Roles mirror the
persona list in 01-VISION.md §4.
"""

PERMISSIONS: list[tuple[str, str]] = [
    ("platform.tenant.create", "Create a new tenant (platform super admin only in practice)"),
    ("platform.user.manage", "Create/update users within the tenant"),
    ("platform.role.assign", "Assign roles/scopes to users"),
    ("platform.audit.view", "View the audit trail"),
    ("platform.config.manage", "Read/write tenant configuration"),
    ("master_data.crop.view", "View crop/variety master data"),
    ("master_data.crop.manage", "Create/update crop/variety master data"),
    ("farm.view", "View farm/zone/plot/block/row hierarchy"),
    ("farm.manage", "Create/update farm/zone/plot/block/row hierarchy"),
    ("tree.view", "View tree twins and their history"),
    ("tree.manage", "Create/update/delete tree twins"),
    ("tree.event.record", "Record a tree history event (health/irrigation/treatment/harvest/...)"),
    ("season.view", "View seasons"),
    ("season.manage", "Create/update seasons"),
    ("workflow.definition.manage", "Create/update approval workflow definitions"),
    ("workflow.instance.submit", "Submit an entity for approval"),
    ("workflow.instance.approve", "Approve/reject/return a submitted workflow instance"),
    ("notification.view", "View own notifications"),
]

SYSTEM_ROLES: list[tuple[str, str]] = [
    ("tenant_admin", "Tenant Admin"),
    ("farm_owner", "Farm Owner"),
    ("farm_manager", "Farm Manager"),
    ("agronomist", "Agronomist"),
    ("field_worker", "Field Worker"),
    ("maintenance_engineer", "Maintenance Engineer"),
    ("warehouse_officer", "Warehouse / Procurement Officer"),
    ("finance", "Finance / Cost Controller"),
    ("auditor", "Auditor"),
    ("viewer", "Viewer"),
]

DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "tenant_admin": [code for code, _ in PERMISSIONS],
    "farm_owner": [
        "platform.audit.view",
        "master_data.crop.view",
        "farm.view",
        "farm.manage",
        "tree.view",
        "tree.manage",
        "season.view",
        "season.manage",
        "workflow.instance.approve",
        "notification.view",
    ],
    "farm_manager": [
        "master_data.crop.view",
        "farm.view",
        "farm.manage",
        "tree.view",
        "tree.manage",
        "tree.event.record",
        "season.view",
        "season.manage",
        "workflow.instance.submit",
        "workflow.instance.approve",
        "notification.view",
    ],
    "agronomist": [
        "master_data.crop.view",
        "farm.view",
        "tree.view",
        "tree.manage",
        "tree.event.record",
        "season.view",
        "workflow.instance.submit",
        "notification.view",
    ],
    "field_worker": [
        "farm.view",
        "tree.view",
        "tree.event.record",
        "notification.view",
    ],
    "maintenance_engineer": [
        "workflow.instance.submit",
        "notification.view",
    ],
    "warehouse_officer": [
        "workflow.instance.submit",
        "notification.view",
    ],
    "finance": [
        "workflow.instance.approve",
        "platform.audit.view",
        "notification.view",
    ],
    "auditor": ["platform.audit.view", "notification.view"],
    "viewer": [
        "master_data.crop.view",
        "farm.view",
        "tree.view",
        "season.view",
        "notification.view",
    ],
}
