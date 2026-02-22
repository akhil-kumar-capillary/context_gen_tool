from pydantic import BaseModel
from typing import Optional


class LoginRequest(BaseModel):
    username: str
    password: str
    cluster: str


class OrgResponse(BaseModel):
    id: int
    name: str


class UserResponse(BaseModel):
    id: int
    email: str
    displayName: str
    isAdmin: bool
    orgs: list[OrgResponse]


class LoginResponse(BaseModel):
    token: str
    user: UserResponse


class SelectOrgRequest(BaseModel):
    org_id: int
    org_name: str
