from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr


class LoginRequest(BaseModel):
    tenant_slug: str
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: str
    tenant_id: str
    email: str
    full_name: str
    is_active: bool
    is_platform_super_admin: bool

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class TenantCreate(BaseModel):
    slug: str
    name: str


class TenantOut(BaseModel):
    id: str
    slug: str
    name: str
    status: str

    model_config = ConfigDict(from_attributes=True)


class RoleOut(BaseModel):
    id: str
    code: str
    name: str
    is_system: bool

    model_config = ConfigDict(from_attributes=True)


class PermissionOut(BaseModel):
    id: str
    code: str
    description: str

    model_config = ConfigDict(from_attributes=True)


class RoleAssignmentCreate(BaseModel):
    user_id: str
    role_id: str
    scope_type: str = "tenant"
    scope_id: Optional[str] = None


class RoleAssignmentOut(BaseModel):
    id: str
    user_id: str
    role_id: str
    scope_type: str
    scope_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AuditEntryOut(BaseModel):
    id: str
    actor_user_id: Optional[str] = None
    action: str
    entity_type: str
    entity_id: str
    old_values: Optional[dict] = None
    new_values: Optional[dict] = None
    reason: Optional[str] = None
    correlation_id: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TenantConfigSet(BaseModel):
    key: str
    value: Any


class TenantConfigOut(BaseModel):
    key: str
    value: Any
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CropCreate(BaseModel):
    code: str
    name_en: str
    name_th: str


class VarietyCreate(BaseModel):
    code: str
    name_en: str
    name_th: str


class VarietyOut(BaseModel):
    id: str
    crop_id: str
    code: str
    name_en: str
    name_th: str
    version: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class CropOut(BaseModel):
    id: str
    code: str
    name_en: str
    name_th: str
    is_active: bool
    varieties: list[VarietyOut] = []

    model_config = ConfigDict(from_attributes=True)


class WorkflowDefinitionCreate(BaseModel):
    entity_type: str
    name: str
    steps: list[dict]


class WorkflowDefinitionOut(BaseModel):
    id: str
    entity_type: str
    name: str
    steps: list[dict]
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class WorkflowSubmitRequest(BaseModel):
    workflow_definition_id: str
    entity_type: str
    entity_id: str
    context: dict = {}


class WorkflowDecisionRequest(BaseModel):
    reason: Optional[str] = None


class WorkflowInstanceOut(BaseModel):
    id: str
    workflow_definition_id: str
    entity_type: str
    entity_id: str
    status: str
    current_step_index: int
    context: dict
    submitted_by: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class NotificationOut(BaseModel):
    id: str
    channel: str
    severity: str
    title: str
    body: str
    is_read: bool
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
