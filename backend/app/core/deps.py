from typing import Callable, Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from ..foundation import models as fm
from .security import InvalidTokenError, decode_token


def set_tenant_context(db: Session, tenant_id: str) -> None:
    """Scopes every subsequent query on this session/transaction to one tenant.

    Uses set_config(..., is_local=true) rather than `SET LOCAL app.x = :tid`
    because SET LOCAL is a DDL-like statement that cannot take a bound
    parameter (Postgres would try to parse the placeholder as SQL); the
    set_config() function is a normal function call and can. is_local=true
    still scopes it to the current transaction, not the pooled connection.
    Every tenant-scoped table's RLS policy reads this variable (see
    backend/alembic/versions/0002_platform_foundation.py).
    """
    db.execute(text("SELECT set_config('app.current_tenant_id', :tid, true)"), {"tid": tenant_id})


def _extract_bearer(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    return authorization.split(" ", 1)[1].strip()


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> fm.User:
    token = _extract_bearer(authorization)
    try:
        payload = decode_token(token, "access")
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid access token: {exc}") from exc

    set_tenant_context(db, payload["tenant_id"])
    user = db.get(fm.User, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid or inactive user")
    return user


def user_has_permission(
    db: Session,
    user: fm.User,
    permission_code: str,
    scope_type: Optional[str] = None,
    scope_id: Optional[str] = None,
) -> bool:
    """RBAC (role -> permission) + ABAC (assignment scope) check per FR-PLT-003/004.

    A platform super admin bypasses this (they administer the platform, not
    one tenant's business data) but that flag alone grants no *tenant business
    data* access beyond what the security architecture calls out explicitly -
    see 09-SECURITY-ARCHITECTURE.md.
    """
    if user.is_platform_super_admin:
        return True

    assignments = (
        db.query(fm.UserRoleAssignment)
        .filter(fm.UserRoleAssignment.user_id == user.id)
        .all()
    )
    if not assignments:
        return False

    role_ids = [a.role_id for a in assignments]
    granted_codes = {
        rp.permission_id
        for rp in db.query(fm.RolePermission).filter(fm.RolePermission.role_id.in_(role_ids)).all()
    }
    permission = db.query(fm.Permission).filter(fm.Permission.code == permission_code).one_or_none()
    if permission is None or permission.id not in granted_codes:
        return False

    if scope_type is None:
        return True

    for a in assignments:
        if a.scope_type == "tenant":
            return True
        if a.scope_type == scope_type and a.scope_id == scope_id:
            return True
    return False


def require_permission(
    permission_code: str, scope_type: Optional[str] = None
) -> Callable[..., fm.User]:
    def dependency(
        current_user: fm.User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> fm.User:
        if not user_has_permission(db, current_user, permission_code, scope_type=scope_type):
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission_code}")
        return current_user

    return dependency


def assert_farm_scope(db: Session, user: fm.User, permission_code: str, farm_id: str) -> None:
    """ABAC narrowing for Farm & Crop routes (FR-FARM, Phase 4).

    `require_permission` above only proves the user holds `permission_code`
    *somewhere* (tenant-wide or on some scope). Once a request resolves to a
    specific Farm, this additionally proves the grant actually covers that
    farm - closing the gap 05-RTM.md flagged in Phase 3 ("ABAC farm/plot-scope
    enforcement has no farm/plot entities to test against yet").
    """
    if not user_has_permission(db, user, permission_code, scope_type="farm", scope_id=farm_id):
        raise HTTPException(status_code=403, detail=f"Missing permission on this farm: {permission_code}")
