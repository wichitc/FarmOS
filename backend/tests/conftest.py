import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.foundation.seed import provision_tenant
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def raw_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


def unique_slug(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class TenantFixture:
    """Holds plain values captured before commit, deliberately not the live
    ORM objects - once `raw_db` commits, its session's RLS transaction
    context is gone (set_config(..., is_local=true) is transaction-scoped),
    so a later lazy-load through that same session would be correctly denied
    by RLS. Real request handlers never hit this because they set tenant
    context fresh on every request; only a long-lived test-setup session can,
    which is exactly what this fixture avoids by not keeping ORM references
    around after commit."""

    def __init__(self, tenant_id: str, tenant_slug: str, admin_user_id: str, admin_email: str, admin_password: str):
        self.tenant_id = tenant_id
        self.tenant_slug = tenant_slug
        self.admin_user_id = admin_user_id
        self.admin_email = admin_email
        self.admin_password = admin_password

    def login(self, client: TestClient, email: str, password: str) -> str:
        res = client.post(
            "/api/v1/auth/login",
            json={"tenant_slug": self.tenant_slug, "email": email, "password": password},
        )
        assert res.status_code == 200, res.text
        return res.json()["access_token"]

    def admin_token(self, client: TestClient) -> str:
        return self.login(client, self.admin_email, self.admin_password)

    def auth_headers(self, client: TestClient) -> dict:
        return {"Authorization": f"Bearer {self.admin_token(client)}"}


def provision_test_tenant(raw_db: Session, prefix: str) -> TenantFixture:
    slug = unique_slug(prefix)
    password = "correct-horse-battery-staple"
    tenant, admin_user = provision_tenant(
        raw_db,
        slug=slug,
        name=f"{prefix.title()} Orchards {slug}",
        admin_email=f"admin+{slug}@example.com",
        admin_password=password,
        admin_full_name=f"{prefix.title()} Admin",
    )
    fixture = TenantFixture(tenant.id, tenant.slug, admin_user.id, admin_user.email, password)
    raw_db.commit()
    return fixture


@pytest.fixture
def tenant(raw_db: Session) -> TenantFixture:
    return provision_test_tenant(raw_db, "acme")
