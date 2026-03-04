from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel


class JournalLineCreate(BaseModel):
    account_id: int
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    description: Optional[str] = None
    gl_reference: Optional[str] = None


class JournalLineResponse(BaseModel):
    id: int
    journal_entry_id: int
    account_id: int
    debit: Decimal
    credit: Decimal
    description: Optional[str]
    gl_reference: Optional[str]

    model_config = {"from_attributes": True}


class JournalEntryCreate(BaseModel):
    period_id: int
    entry_date: date
    reference: Optional[str] = None
    description: Optional[str] = None
    entry_type: str  # adjusting / reclassifying / elimination / budget_variance
    lines: List[JournalLineCreate]


class JournalEntryUpdate(BaseModel):
    entry_date: Optional[date] = None
    reference: Optional[str] = None
    description: Optional[str] = None
    entry_type: Optional[str] = None
    lines: Optional[List[JournalLineCreate]] = None


class JournalEntryResponse(BaseModel):
    id: int
    period_id: int
    entry_date: date
    reference: Optional[str]
    description: Optional[str]
    entry_type: str
    prepared_by_user_id: int
    reviewed_by_user_id: Optional[int]
    status: str
    created_at: datetime
    lines: List[JournalLineResponse] = []

    model_config = {"from_attributes": True}
