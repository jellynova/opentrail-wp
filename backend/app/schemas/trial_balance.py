from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any
from pydantic import BaseModel


class TrialBalanceEntryResponse(BaseModel):
    id: int
    period_id: int
    account_id: int
    opening_debit: Decimal
    opening_credit: Decimal
    period_debit: Decimal
    period_credit: Decimal
    ytd_debit: Decimal
    ytd_credit: Decimal
    source: str
    imported_at: datetime
    connector_id: Optional[int]

    model_config = {"from_attributes": True}


class TrialBalanceEntryUpdate(BaseModel):
    opening_debit: Optional[Decimal] = None
    opening_credit: Optional[Decimal] = None
    period_debit: Optional[Decimal] = None
    period_credit: Optional[Decimal] = None
    ytd_debit: Optional[Decimal] = None
    ytd_credit: Optional[Decimal] = None


class WorkingTrialBalanceRow(BaseModel):
    account_id: int
    acct_fmtd: str
    description: Optional[str]
    opening_debit: Decimal
    opening_credit: Decimal
    period_debit: Decimal
    period_credit: Decimal
    ytd_debit: Decimal
    ytd_credit: Decimal
    adj_debit: Decimal  # sum of journal entry debits
    adj_credit: Decimal  # sum of journal entry credits
    closing_debit: Decimal  # ytd_debit + adj_debit - adj_credit (when normal_balance=debit)
    closing_credit: Decimal


class CSVImportRequest(BaseModel):
    period_id: int
    column_mapping: Dict[str, str]  # {"Account": "acct_fmtd", "Debit": "period_debit", ...}


class ConnectorImportRequest(BaseModel):
    connector_id: int
    fiscal_year_id: int
    period_id: int
    fiscal_year: int  # the AMAIS fiscal year number
    period_number: int  # the AMAIS period number


class ImportResult(BaseModel):
    records_imported: int
    records_updated: int
    errors: list[str] = []
