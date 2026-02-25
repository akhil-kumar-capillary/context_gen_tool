from pydantic import BaseModel


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


class ToggleAdminRequest(BaseModel):
    user_email: str
