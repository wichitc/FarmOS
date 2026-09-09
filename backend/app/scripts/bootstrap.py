"""Bootstraps the very first tenant + platform super admin.

Run once per deployment, out-of-band from the API (there is deliberately no
open "create the first tenant" HTTP endpoint - that would be an
unauthenticated privilege-escalation hole). Every subsequent tenant is
provisioned by this bootstrap admin via POST /api/v1/tenants.

Usage: python -m app.scripts.bootstrap <slug> <org-name> <admin-email> <admin-password> <admin-name>
"""
import sys

from ..database import SessionLocal
from ..foundation.seed import provision_tenant


def main() -> None:
    if len(sys.argv) != 6:
        print(__doc__)
        raise SystemExit(1)
    slug, name, admin_email, admin_password, admin_full_name = sys.argv[1:]

    db = SessionLocal()
    try:
        tenant, admin_user = provision_tenant(
            db,
            slug=slug,
            name=name,
            admin_email=admin_email,
            admin_password=admin_password,
            admin_full_name=admin_full_name,
        )
        admin_user.is_platform_super_admin = True
        db.commit()
        print(f"Provisioned tenant '{tenant.slug}' ({tenant.id}) with super admin {admin_user.email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
