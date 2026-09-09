from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.deps import get_current_user
from ...database import get_db
from ...foundation import models as fm
from ...foundation.schemas import TenantCreate, TenantOut
from ...foundation.seed import provision_tenant

router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])


def require_platform_super_admin(current_user: fm.User = Depends(get_current_user)) -> fm.User:
    if not current_user.is_platform_super_admin:
        raise HTTPException(status_code=403, detail="Requires platform super admin")
    return current_user


@router.get("", response_model=list[TenantOut])
def list_tenants(
    db: Session = Depends(get_db),
    _admin: fm.User = Depends(require_platform_super_admin),
):
    # Tenant is deliberately not RLS-scoped (it's the hierarchy root, per
    # 09-SECURITY-ARCHITECTURE.md §4) - the platform-super-admin gate above is
    # what makes this endpoint safe, not row-level filtering.
    return db.query(fm.Tenant).order_by(fm.Tenant.created_at.asc()).all()


class TenantProvisionRequest(TenantCreate):
    admin_email: str
    admin_password: str
    admin_full_name: str


@router.post("", response_model=TenantOut, status_code=201)
def create_tenant(
    payload: TenantProvisionRequest,
    db: Session = Depends(get_db),
    _admin: fm.User = Depends(require_platform_super_admin),
):
    try:
        tenant, _admin_user = provision_tenant(
            db,
            slug=payload.slug,
            name=payload.name,
            admin_email=payload.admin_email,
            admin_password=payload.admin_password,
            admin_full_name=payload.admin_full_name,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Tenant slug already exists") from exc
    return tenant
