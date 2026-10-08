from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel


class FiscalYearCreate(BaseModel):
    label: str
    start_date: date
    end_date: date
    status: str = "open"


class FiscalYearUpdate(BaseModel):
    label: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None


class PeriodResponse(BaseModel):
    id: int
    fiscal_year_id: int
    period_number: int
    name: str
    start_date: date
    end_date: date
    is_closed: bool

    model_config = {"from_attributes": True}


class FiscalYearResponse(BaseModel):
    id: int
    label: str
    start_date: date
    end_date: date
    status: str

    model_config = {"from_attributes": True}


class FiscalYearWithPeriods(FiscalYearResponse):
    periods: List[PeriodResponse] = []


class PeriodCreate(BaseModel):
    period_number: int
    name: str
    start_date: date
    end_date: date
    is_closed: bool = False


class PeriodUpdate(BaseModel):
    name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_closed: Optional[bool] = None


# --- Period close & roll forward (PLAN §7.3) -----------------------------------------


class CloseRequest(BaseModel):
    notes: Optional[str] = None
    # finance_admin only: proceed even though working papers are not signed off.
    force: bool = False


class ReopenRequest(BaseModel):
    reason: Optional[str] = None


class RollForwardRequest(BaseModel):
    label: Optional[str] = None  # defaults to the year after the source fiscal year


class UnpostedEntry(BaseModel):
    id: int
    reference: Optional[str]
    status: str
    entry_type: str


class UnsignedDocument(BaseModel):
    document_id: int
    display_name: str
    folder_path: str
    state: str


class PreCloseCheckResponse(BaseModel):
    period_id: int
    fiscal_year_id: int
    already_closed: bool
    ready: bool
    unposted_journal_entries: List[UnpostedEntry] = []
    unsigned_documents: List[UnsignedDocument] = []


class PeriodCloseBalanceResponse(BaseModel):
    account_id: int
    acct_fmtd: str
    opening: Decimal
    ytd_debit: Decimal
    ytd_credit: Decimal
    period_debit: Decimal
    period_credit: Decimal
    aje_debit: Decimal
    aje_credit: Decimal
    rje_debit: Decimal
    rje_credit: Decimal
    closing: Decimal

    model_config = {"from_attributes": True}


class PeriodCloseResponse(BaseModel):
    id: int
    period_id: int
    period_name: Optional[str] = None
    fiscal_year_label: Optional[str] = None
    closed_by_user_id: int
    closed_by_username: Optional[str] = None
    closed_at: datetime
    notes: Optional[str]
    journal_entry_count: int
    account_count: int
    total_debits: Decimal
    total_credits: Decimal
    is_balanced: bool
    overrides: Optional[str]
    reopened_at: Optional[datetime] = None
    reopened_by_user_id: Optional[int] = None
    balances: List[PeriodCloseBalanceResponse] = []


class RollForwardResponse(BaseModel):
    fiscal_year: FiscalYearResponse
    periods_created: int
    accounts_copied: int
    account_mappings_copied: int
    classifications_copied: int
    opening_balances_posted: int
    opening_debits: Decimal
    opening_credits: Decimal
    balanced: bool
    net_surplus: Decimal = Decimal("0")  # closed to accumulated surplus (credit-positive)
    surplus_account: Optional[str] = None
    warnings: List[str] = []
