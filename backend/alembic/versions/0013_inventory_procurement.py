"""Inventory & Procurement (Phase 13, FR-INV / FR-PROC): item/warehouse/
vendor master data, stock lots + append-only movements, purchase requests
+ orders - same tenant-scoped + RLS pattern as prior migrations.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

TENANT_SCOPED_TABLES = [
    "inventory_items",
    "warehouses",
    "vendors",
    "stock_lots",
    "stock_movements",
    "purchase_requests",
    "purchase_orders",
]


def _standard_columns():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_by", postgresql.UUID(as_uuid=False), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "inventory_items",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("uom", sa.String(length=20), nullable=False),
        sa.Column("min_qty", sa.Float, nullable=True),
        sa.Column("max_qty", sa.Float, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *_standard_columns(),
        sa.UniqueConstraint("tenant_id", "code", name="uq_inventory_items_tenant_code"),
    )

    op.create_table(
        "warehouses",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id"), nullable=True, index=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        *_standard_columns(),
        sa.UniqueConstraint("tenant_id", "code", name="uq_warehouses_tenant_code"),
    )

    op.create_table(
        "vendors",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("contact_info", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *_standard_columns(),
        sa.UniqueConstraint("tenant_id", "code", name="uq_vendors_tenant_code"),
    )

    op.create_table(
        "stock_lots",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("inventory_items.id"), nullable=False, index=True),
        sa.Column("warehouse_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("warehouses.id"), nullable=False, index=True),
        sa.Column("lot_code", sa.String(length=100), nullable=False),
        sa.Column("quantity", sa.Float, nullable=False, server_default="0"),
        sa.Column("unit_cost", sa.Float, nullable=True),
        sa.Column("expiry_date", sa.Date, nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        *_standard_columns(),
    )

    op.create_table(
        "stock_movements",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("lot_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("stock_lots.id"), nullable=False, index=True),
        sa.Column("movement_type", sa.String(length=20), nullable=False, index=True),
        sa.Column("quantity_delta", sa.Float, nullable=False),
        sa.Column("reference_type", sa.String(length=30), nullable=True),
        sa.Column("reference_id", sa.String(length=100), nullable=True),
        sa.Column("from_warehouse_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("warehouses.id"), nullable=True),
        sa.Column("to_warehouse_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("warehouses.id"), nullable=True),
        sa.Column("performed_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        *_standard_columns(),
    )

    op.create_table(
        "purchase_requests",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("inventory_items.id"), nullable=False, index=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id"), nullable=True, index=True),
        sa.Column("quantity", sa.Float, nullable=False),
        sa.Column("needed_by", sa.Date, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("workflow_instance_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("workflow_instances.id"), nullable=True),
        sa.Column("requested_by", postgresql.UUID(as_uuid=False), nullable=True),
        *_standard_columns(),
    )

    op.create_table(
        "purchase_orders",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("request_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("purchase_requests.id"), nullable=False, index=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("vendors.id"), nullable=False, index=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("inventory_items.id"), nullable=False, index=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id"), nullable=True, index=True),
        sa.Column("po_number", sa.String(length=30), nullable=False),
        sa.Column("quantity", sa.Float, nullable=False),
        sa.Column("unit_price", sa.Float, nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="issued"),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_quantity", sa.Float, nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("inspection_status", sa.String(length=20), nullable=True),
        sa.Column("inspection_notes", sa.Text, nullable=True),
        sa.Column("warehouse_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("warehouses.id"), nullable=True),
        sa.Column("resulting_lot_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("stock_lots.id"), nullable=True),
        sa.Column("invoice_number", sa.String(length=50), nullable=True),
        sa.Column("invoice_amount", sa.Float, nullable=True),
        sa.Column("invoice_matched", sa.Boolean, nullable=True),
        *_standard_columns(),
    )

    for table in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
            """
        )


def downgrade() -> None:
    for table in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.drop_table("purchase_orders")
    op.drop_table("purchase_requests")
    op.drop_table("stock_movements")
    op.drop_table("stock_lots")
    op.drop_table("vendors")
    op.drop_table("warehouses")
    op.drop_table("inventory_items")
