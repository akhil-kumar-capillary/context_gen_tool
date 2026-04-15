from typing import List
from pydantic import BaseModel


class PlatformVariableCreate(BaseModel):
    key: str
    value: str | None = None
    value_type: str = "string"
    group_name: str | None = None
    description: str | None = None
    default_value: str | None = None
    is_required: bool = False
    validation_rule: str | None = None
    sort_order: int = 0


class PlatformVariableUpdate(BaseModel):
    value: str | None = None
    value_type: str | None = None
    group_name: str | None = None
    description: str | None = None
    default_value: str | None = None
    is_required: bool | None = None
    validation_rule: str | None = None
    sort_order: int | None = None
    change_reason: str | None = None


class PlatformVariableImportRequest(BaseModel):
    variables: List[PlatformVariableCreate]
    overwrite: bool = False
