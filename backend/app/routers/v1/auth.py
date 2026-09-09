from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...core.deps import get_current_user, set_tenant_context
from ...core.security import (
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from ...database import get_db
from ...foundation import models as fm
from ...foundation.schemas import LoginRequest, RefreshRequest, TokenPair, UserOut

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    tenant = db.query(fm.Tenant).filter(fm.Tenant.slug == payload.tenant_slug).one_or_none()
    if not tenant or tenant.status != "active":
        raise HTTPException(status_code=401, detail="Invalid tenant, email, or password")

    set_tenant_context(db, tenant.id)
    user = db.query(fm.User).filter(fm.User.email == payload.email).one_or_none()
    if not user or not user.is_active or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid tenant, email, or password")

    return TokenPair(
        access_token=create_access_token(user.id, tenant.id, user.is_platform_super_admin),
        refresh_token=create_refresh_token(user.id, tenant.id),
    )


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    try:
        claims = decode_token(payload.refresh_token, "refresh")
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid refresh token: {exc}") from exc

    set_tenant_context(db, claims["tenant_id"])
    user = db.get(fm.User, claims["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    return TokenPair(
        access_token=create_access_token(user.id, user.tenant_id, user.is_platform_super_admin),
        refresh_token=create_refresh_token(user.id, user.tenant_id),
    )


@router.get("/me", response_model=UserOut)
def me(current_user: fm.User = Depends(get_current_user)):
    return current_user
