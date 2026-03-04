from datetime import datetime
from typing import Optional, Any, Dict, List
from pydantic import BaseModel


class ReportCreate(BaseModel):
    name: str
    description: Optional[str] = None
    report_type: str
    is_template: bool = False
    definition: Dict[str, Any] = {}
    fiscal_year_id: Optional[int] = None


class ReportUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    report_type: Optional[str] = None
    definition: Optional[Dict[str, Any]] = None
    fiscal_year_id: Optional[int] = None


class ReportResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    report_type: str
    is_template: bool
    is_protected: bool
    definition: Dict[str, Any]
    fiscal_year_id: Optional[int]
    created_by_user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReportGenerateRequest(BaseModel):
    fiscal_year_id: int
    period_id: Optional[int] = None


class ReportGenerateResponse(BaseModel):
    report_id: int
    title: str
    fiscal_year_id: int
    period_id: Optional[int]
    data: Dict[str, Any]
    generated_at: datetime
