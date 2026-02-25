from pydantic import BaseModel


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
