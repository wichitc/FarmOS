from sqlalchemy.orm import Session

from ..core.deps import set_tenant_context
from ..core.security import hash_password
from . import models as fm
from .rbac_catalog import DEFAULT_ROLE_PERMISSIONS, PERMISSIONS, SYSTEM_ROLES


def ensure_permission_catalog(db: Session) -> dict[str, fm.Permission]:
    """Idempotently ensures every known permission code exists. Global, run
    once regardless of how many tenants exist."""
    existing = {p.code: p for p in db.query(fm.Permission).all()}
    for code, description in PERMISSIONS:
        if code not in existing:
            perm = fm.Permission(code=code, description=description)
            db.add(perm)
            existing[code] = perm
    db.flush()
    return existing


def provision_tenant(
    db: Session,
    *,
    slug: str,
    name: str,
    admin_email: str,
    admin_password: str,
    admin_full_name: str,
) -> tuple[fm.Tenant, fm.User]:
    """Creates a tenant with the system role catalog seeded and one
    tenant_admin user, per FR-PLT-001/003 and the persona set in
    01-VISION.md §4. Idempotent on slug (raises if it already exists - the
    caller/route decides how to surface that)."""
    permissions = ensure_permission_catalog(db)

    tenant = fm.Tenant(slug=slug, name=name)
    db.add(tenant)
    db.flush()

    # Tenant itself carries no tenant_id (it's the RLS-exempt hierarchy root -
    # 09-SECURITY-ARCHITECTURE.md §4), but every row below does. Point this
    # transaction's RLS context at the tenant being provisioned so those
    # inserts pass their WITH CHECK policy even when the caller (a platform
    # super admin) belongs to a different tenant.
    set_tenant_context(db, tenant.id)

    roles_by_code: dict[str, fm.Role] = {}
    for code, role_name in SYSTEM_ROLES:
        role = fm.Role(tenant_id=tenant.id, code=code, name=role_name, is_system=True)
        db.add(role)
        db.flush()
        for perm_code in DEFAULT_ROLE_PERMISSIONS.get(code, []):
            db.add(
                fm.RolePermission(
                    tenant_id=tenant.id, role_id=role.id, permission_id=permissions[perm_code].id
                )
            )
        roles_by_code[code] = role

    admin_user = fm.User(
        tenant_id=tenant.id,
        email=admin_email,
        hashed_password=hash_password(admin_password),
        full_name=admin_full_name,
    )
    db.add(admin_user)
    db.flush()

    db.add(
        fm.UserRoleAssignment(
            tenant_id=tenant.id,
            user_id=admin_user.id,
            role_id=roles_by_code["tenant_admin"].id,
            scope_type="tenant",
        )
    )
    db.flush()
    return tenant, admin_user
