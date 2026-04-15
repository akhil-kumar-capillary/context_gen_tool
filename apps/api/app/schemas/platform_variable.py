from typing import List
from pydantic import BaseModel, Field


class PlatformVariableCreate(BaseModel):
    key: str = Field(..., max_length=255)
    value: str | None = None
    value_type: str = "string"
    group_name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    default_value: str | None = None
    is_required: bool = False
    validation_rule: str | None = Field(default=None, max_length=200)
    sort_order: int = 0


class PlatformVariableUpdate(BaseModel):
    value: str | None = None
    value_type: str | None = None
    group_name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    default_value: str | None = None
    is_required: bool | None = None
    validation_rule: str | None = Field(default=None, max_length=200)
    sort_order: int | None = None
    change_reason: str | None = None


class PlatformVariableImportRequest(BaseModel):
    variables: List[PlatformVariableCreate] = Field(..., max_length=10000)
    overwrite: bool = False
