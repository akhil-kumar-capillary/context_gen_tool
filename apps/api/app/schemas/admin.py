from pydantic import BaseModel
from typing import Optional


class GrantRoleRequest(BaseModel):
    user_email: str
    role_name: str


class RevokeRoleRequest(BaseModel):
    user_email: str
    role_name: str


class GrantPermissionRequest(BaseModel):
    user_email: str
    module: str
    operation: str


class RevokePermissionRequest(BaseModel):
    user_email: str
    module: str
    operation: str


class SecretUpdateRequest(BaseModel):
    key: str  # e.g. 'anthropic_api_key', 'databricks_token'
    value: str
    org_id: Optional[int] = None  # None = global, int = per-org


class UserListResponse(BaseModel):
    id: int
    email: str
    display_name: Optional[str]
    is_admin: bool
    is_active: bool
    roles: list[str]
    permissions: list[dict]
