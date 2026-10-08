from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class WorkingPaperResponse(BaseModel):
    """A working paper document (the latest version) with its sign-off state."""

    id: int
    root_id: int
    fiscal_year_id: int
    folder_path: str
    filename: str
    display_name: str
    file_type: str
    file_size: int
    uploaded_by_user_id: int
    uploaded_by_username: Optional[str] = None
    uploaded_at: datetime
    description: Optional[str]
    version_number: int
    version_count: int = 1
    parent_version_id: Optional[int]
    superseded_at: Optional[datetime] = None

    # Sign-off workflow (PLAN §7.2)
    sign_off_state: str = "draft"  # draft / prepared / approved / reapproval_required
    requires_reapproval: bool = False
    preparer_signed_off_by_user_id: Optional[int] = None
    preparer_signed_off_by_username: Optional[str] = None
    preparer_signed_off_at: Optional[datetime] = None
    reviewer_signed_off_by_user_id: Optional[int] = None
    reviewer_signed_off_by_username: Optional[str] = None
    reviewer_signed_off_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class WorkingPaperUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    folder_path: Optional[str] = None


class FolderNode(BaseModel):
    path: str
    label: str
    fiscal_year_id: Optional[int] = None
    fiscal_year_status: Optional[str] = None
    document_count: int = 0
    unsigned_count: int = 0
    children: List["FolderNode"] = []


FolderNode.model_rebuild()


class WorkingPaperUploadMetadata(BaseModel):
    fiscal_year_id: int
    folder_path: str = "/permanent"
    display_name: Optional[str] = None
    description: Optional[str] = None


class SignOffRequest(BaseModel):
    note: Optional[str] = None


class AnnotationCreate(BaseModel):
    text: str


class AnnotationResponse(BaseModel):
    id: int
    working_paper_id: int
    user_id: int
    username: Optional[str] = None
    text: str
    created_at: datetime
    is_resolved: bool
    resolved_by_user_id: Optional[int]
    resolved_by_username: Optional[str] = None
    resolved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SignOffResponse(BaseModel):
    message: str
    document_id: int
    sign_off_state: str
    requires_reapproval: bool = False
