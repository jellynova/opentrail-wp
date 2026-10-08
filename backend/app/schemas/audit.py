from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: int
    user_id: Optional[int]
    username: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[int]
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    ip_address: Optional[str]
    timestamp: datetime
    description: str


class AuditLogPage(BaseModel):
    items: List[AuditLogResponse]
    limit: int
    offset: int
    has_more: bool
