from pydantic import BaseModel


class ContextCreateRequest(BaseModel):
    name: str
    content: str
    scope: str = "org"


class ContextUpdateRequest(BaseModel):
    context_id: str
    name: str
    content: str
    scope: str = "org"


class BulkUploadItem(BaseModel):
    name: str
    content: str
    scope: str = "org"


class BulkUploadRequest(BaseModel):
    contexts: list[BulkUploadItem]
    existing_name_map: dict[str, str] = {}  # name -> context_id for updates
