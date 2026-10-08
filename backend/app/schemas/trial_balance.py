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
    version: int = 1
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TrialBalanceEntryUpdate(BaseModel):
    # Optimistic locking (PLAN §8.1): the version the client loaded.
    version: Optional[int] = None
    opening_debit: Optional[Decimal] = None
    opening_credit: Optional[Decimal] = None
    period_debit: Optional[Decimal] = None
    period_credit: Optional[Decimal] = None
    ytd_debit: Optional[Decimal] = None
    ytd_credit: Optional[Decimal] = None


class WorkingTrialBalanceRow(BaseModel):
    """
    One account in the working trial balance. Balances are signed debit-positive.
    unadjusted = opening + YTD movement; adjusted = unadjusted + AJEs; final = adjusted + RJEs.
    Journal adjustments are cumulative from period 1 through the selected period.
    """

    account_id: int
    acct_fmtd: str
    description: Optional[str]
    classification: Optional[str] = None
    opening_debit: Decimal
    opening_credit: Decimal
    period_debit: Decimal
    period_credit: Decimal
    ytd_debit: Decimal
    ytd_credit: Decimal
    unadjusted_balance: Decimal
    aje_debit: Decimal
    aje_credit: Decimal
    adjusted_balance: Decimal
    rje_debit: Decimal
    rje_credit: Decimal
    adj_debit: Decimal  # AJE + RJE debits
    adj_credit: Decimal  # AJE + RJE credits
    final_balance: Decimal
    closing_debit: Decimal  # final balance when it is a debit, else 0
    closing_credit: Decimal  # final balance when it is a credit, else 0


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
