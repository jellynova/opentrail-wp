"""
Schemas for leadsheet-to-document account links (PLAN §4.3) and fiscal-year reopen.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class AccountLinkCreate(BaseModel):
    account_code: str
    # The fiscal year the leadsheet belongs to; stored on the link so by-account
    # lookups can be scoped to one year's chart of accounts.
    fiscal_year_id: int


class AccountLinkResponse(BaseModel):
    id: int
    working_paper_id: int
    account_code: str
    fiscal_year_id: int
    created_by_user_id: int
    created_by_username: Optional[str] = None
    created_at: datetime
    # Convenience fields for the UI (document display name / folder).
    document_display_name: Optional[str] = None
    document_folder_path: Optional[str] = None

    model_config = {"from_attributes": True}


class DocumentWithLinksResponse(BaseModel):
    """Documents list entry plus its linked account codes (Documents page)."""

    id: int
    display_name: str
    file_type: str
    linked_account_codes: List[str] = []


class FiscalYearReopenRequest(BaseModel):
    reason: str
    # Required to reopen a *locked* year; ordinary closed years need only a reason.
    force: bool = False


class ClosedPeriodInfo(BaseModel):
    id: int
    period_number: int
    name: str
    is_closed: bool


class FiscalYearReopenResponse(BaseModel):
    fiscal_year_id: int
    label: str
    status: str
    forced: bool
    periods_still_closed: int
    closed_periods: List[ClosedPeriodInfo] = []
