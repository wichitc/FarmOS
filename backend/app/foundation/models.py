import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


def _uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)


class TenantScopedMixin:
    """Standard fields per 08-DATA-ARCHITECTURE.md §4 (DATA-001). Every table
    that mixes this in gets an RLS policy in the Phase-3 migration."""

    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)


class Tenant(Base):
    """Root of the hierarchy - deliberately NOT tenant-scoped itself (BR-007)."""

    __tablename__ = "tenants"

    id: Mapped[str] = _uuid_pk()
    slug: Mapped[str] = mapped_column(String(63), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Organization(TenantScopedMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[str] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255))


class User(TenantScopedMixin, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[str] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(255), index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_platform_super_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    role_assignments: Mapped[list["UserRoleAssignment"]] = relationship(back_populates="user")


class Permission(Base):
    """Global catalog of grantable permissions (module.feature.action), per
    FR-PLT-004 - not tenant-scoped, it's a platform-defined vocabulary."""

    __tablename__ = "permissions"

    id: Mapped[str] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(255), default="")


class Role(TenantScopedMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_roles_tenant_code"),)

    id: Mapped[str] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)

    permissions: Mapped[list["RolePermission"]] = relationship(back_populates="role", cascade="all, delete-orphan")


class RolePermission(Base):
    __tablename__ = "role_permissions"

    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    role_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)

    role: Mapped["Role"] = relationship(back_populates="permissions")


class UserRoleAssignment(TenantScopedMixin, Base):
    """ABAC scope layered on RBAC role grant (FR-PLT-004). scope_type is one
    of 'tenant' (org-wide grant) / 'farm' / 'plot'; scope_id is null for a
    tenant-wide grant."""

    __tablename__ = "user_role_assignments"

    id: Mapped[str] = _uuid_pk()
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("roles.id", ondelete="CASCADE"), index=True)
    scope_type: Mapped[str] = mapped_column(String(20), default="tenant")
    scope_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)

    user: Mapped["User"] = relationship(back_populates="role_assignments")


class AuditEntry(Base):
    """Append-only per BR-004 - no updated_at/updated_by, no soft delete, no
    UPDATE/DELETE path is exposed anywhere in the application layer."""

    __tablename__ = "audit_entries"

    id: Mapped[str] = _uuid_pk()
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    actor_user_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(100), index=True)
    entity_id: Mapped[str] = mapped_column(String(100), index=True)
    old_values: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    new_values: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TenantConfig(TenantScopedMixin, Base):
    __tablename__ = "tenant_config"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_tenant_config_key"),)

    id: Mapped[str] = _uuid_pk()
    key: Mapped[str] = mapped_column(String(150))
    value: Mapped[dict] = mapped_column(JSONB)


class Crop(TenantScopedMixin, Base):
    """Seed of the Crop Configuration Engine (FR-FARM-003 / §9 of the brief).
    Full agronomic-rule versioning lands in a later phase; this establishes
    the master-data shape so Farm & Crop (Phase 4) has something to bind to."""

    __tablename__ = "crops"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_crops_tenant_code"),)

    id: Mapped[str] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(50))
    name_en: Mapped[str] = mapped_column(String(150))
    name_th: Mapped[str] = mapped_column(String(150))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    varieties: Mapped[list["Variety"]] = relationship(back_populates="crop", cascade="all, delete-orphan")


class Variety(TenantScopedMixin, Base):
    __tablename__ = "varieties"
    __table_args__ = (UniqueConstraint("tenant_id", "crop_id", "code", name="uq_varieties_tenant_crop_code"),)

    id: Mapped[str] = _uuid_pk()
    crop_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("crops.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(50))
    name_en: Mapped[str] = mapped_column(String(150))
    name_th: Mapped[str] = mapped_column(String(150))
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    crop: Mapped["Crop"] = relationship(back_populates="varieties")


WORKFLOW_STATUSES = ("draft", "submitted", "approved", "rejected", "returned", "cancelled")


class WorkflowDefinition(TenantScopedMixin, Base):
    """Generic configurable approval workflow (FR-PLT-005/006). `steps` is an
    ordered list of {"step": int, "approver_role_code": str, "condition":
    {...} | None} - condition keys are compared against the instance's
    `context` at submit time (e.g. {"amount_gte": 100000})."""

    __tablename__ = "workflow_definitions"
    __table_args__ = (UniqueConstraint("tenant_id", "entity_type", "name", name="uq_workflow_def_tenant_entity_name"),)

    id: Mapped[str] = _uuid_pk()
    entity_type: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(150))
    steps: Mapped[list] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class WorkflowInstance(TenantScopedMixin, Base):
    __tablename__ = "workflow_instances"

    id: Mapped[str] = _uuid_pk()
    workflow_definition_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("workflow_definitions.id"))
    entity_type: Mapped[str] = mapped_column(String(100), index=True)
    entity_id: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    current_step_index: Mapped[int] = mapped_column(Integer, default=0)
    context: Mapped[dict] = mapped_column(JSONB, default=dict)
    submitted_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)


class WorkflowStepEvent(Base):
    """Append-only decision log per BR-004 - the approval-history trail."""

    __tablename__ = "workflow_step_events"

    id: Mapped[str] = _uuid_pk()
    tenant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False, index=True)
    workflow_instance_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("workflow_instances.id"), index=True)
    step_index: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(20))
    actor_user_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(TenantScopedMixin, Base):
    __tablename__ = "notifications"

    id: Mapped[str] = _uuid_pk()
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(20), default="web")
    severity: Mapped[str] = mapped_column(String(20), default="info")
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(String(2000), default="")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    related_entity_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    related_entity_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
