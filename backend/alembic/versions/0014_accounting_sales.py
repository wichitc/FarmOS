"""Farm Accounting & Profitability (Phase 14, FR-ACC / FR-PROF) + Sales &
Customer (FR-SALES): cost centers, a flat ledger + budgets, customers/
sales orders/invoices/payments - same tenant-scoped + RLS pattern as prior
migrations.

Revision ID: 0014
Revises: 0013
Create Date: 2026-12-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

TENANT_SCOPED_TABLES = [
    "cost_centers",
    "ledger_entries",
    "budgets",
    "customers",
    "sales_orders",
    "sales_invoices",
    "sales_payments",
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
        "cost_centers",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *_standard_columns(),
    )

    op.create_table(
        "ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("entry_type", sa.String(length=20), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False, index=True),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("dimensions", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("source_type", sa.String(length=50), nullable=True),
        sa.Column("source_id", sa.String(length=100), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("posted_by", postgresql.UUID(as_uuid=False), nullable=True),
        *_standard_columns(),
    )
    # GIN index for the JSONB containment (`@>`) queries `compute_profitability`
    # and the ledger list/filter endpoints run against `dimensions`.
    op.execute("CREATE INDEX ix_ledger_entries_dimensions_gin ON ledger_entries USING GIN (dimensions)")

    op.create_table(
        "budgets",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("dimensions", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        *_standard_columns(),
    )

    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("contact_info", postgresql.JSONB, nullable=False, server_default="{}"),
        *_standard_columns(),
    )

    op.create_table(
        "sales_orders",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("farm_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("farms.id"), nullable=True, index=True),
        sa.Column("season_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("seasons.id"), nullable=True),
        sa.Column("harvest_lot_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("harvest_lots.id"), nullable=True),
        sa.Column("quantity_kg", sa.Float, nullable=False),
        sa.Column("unit_price", sa.Float, nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("order_date", sa.Date, nullable=False),
        *_standard_columns(),
    )

    op.create_table(
        "sales_invoices",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("sales_orders.id"), nullable=False, index=True),
        sa.Column("invoice_number", sa.String(length=30), nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_date", sa.Date, nullable=True),
        sa.Column("is_paid", sa.Boolean, nullable=False, server_default=sa.false()),
        *_standard_columns(),
    )

    op.create_table(
        "sales_payments",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("sales_invoices.id"), nullable=False, index=True),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("method", sa.String(length=50), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
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
    op.drop_table("sales_payments")
    op.drop_table("sales_invoices")
    op.drop_table("sales_orders")
    op.drop_table("customers")
    op.drop_table("budgets")
    op.drop_table("ledger_entries")
    op.drop_table("cost_centers")
