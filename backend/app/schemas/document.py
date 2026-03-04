from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class WorkingPaperResponse(BaseModel):
    id: int
    fiscal_year_id: int
    folder_path: str
    filename: str
    display_name: str
    file_type: str
    file_size: int
    uploaded_by_user_id: int
    uploaded_at: datetime
    description: Optional[str]
    version_number: int
    parent_version_id: Optional[int]

    model_config = {"from_attributes": True}


class WorkingPaperUploadMetadata(BaseModel):
    fiscal_year_id: int
    folder_path: str = "/"
    display_name: Optional[str] = None
    description: Optional[str] = None


class AnnotationCreate(BaseModel):
    text: str


class AnnotationResponse(BaseModel):
    id: int
    working_paper_id: int
    user_id: int
    text: str
    created_at: datetime
    is_resolved: bool
    resolved_by_user_id: Optional[int]

    model_config = {"from_attributes": True}


class SignOffResponse(BaseModel):
    message: str
    document_id: int
