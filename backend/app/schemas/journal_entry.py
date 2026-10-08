from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional, List
from pydantic import BaseModel, computed_field, model_validator

EntryType = Literal["adjusting", "reclassifying", "elimination", "budget_variance"]


class JournalLineCreate(BaseModel):
    account_id: int
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    description: Optional[str] = None
    gl_reference: Optional[str] = None

    @model_validator(mode="after")
    def _one_sided_positive(self):
        if self.debit < 0 or self.credit < 0:
            raise ValueError("debit and credit must not be negative")
        if self.debit > 0 and self.credit > 0:
            raise ValueError("a line may have a debit or a credit, not both")
        if self.debit == 0 and self.credit == 0:
            raise ValueError("a line must have a non-zero debit or credit")
        return self


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
    reference: Optional[str] = None  # auto-numbered (AJE-001, RJE-001, ...) when omitted
    description: Optional[str] = None
    entry_type: EntryType
    lines: List[JournalLineCreate]


class JournalEntryUpdate(BaseModel):
    # Optimistic locking (PLAN §8.1): the version the client loaded, if it is tracking one.
    version: Optional[int] = None
    entry_date: Optional[date] = None
    reference: Optional[str] = None
    description: Optional[str] = None
    entry_type: Optional[EntryType] = None
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
    version: int = 1
    created_at: datetime
    lines: List[JournalLineResponse] = []

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_debit(self) -> Decimal:
        return sum((Decimal(str(l.debit)) for l in self.lines), Decimal("0"))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_credit(self) -> Decimal:
        return sum((Decimal(str(l.credit)) for l in self.lines), Decimal("0"))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_balanced(self) -> bool:
        return self.total_debit == self.total_credit
