"""Non-superuser application role, so RLS (0002) actually applies at runtime.

PostgreSQL never enforces row-level security against a superuser, regardless
of FORCE ROW LEVEL SECURITY - this was caught by
tests/test_tenant_isolation.py failing against the superuser connection the
app used before this migration. Migrations continue to run as the superuser
(DDL); the running application connects as `durianos_app` instead (see
app/config.py's `app_database_url` / docker-compose.yml).

Revision ID: 0003
Revises: 0002
Create Date: 2026-01-03 00:00:00
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

APP_ROLE = "durianos_app"


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_ROLE}';
            END IF;
        END$$;
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {APP_ROLE}")
