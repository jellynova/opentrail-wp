from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel


class BudgetYearCreate(BaseModel):
    fiscal_year_id: int
    label: str
    submission_deadline: Optional[date] = None
    status: str = "setup"
    instructions_text: Optional[str] = None


class BudgetYearUpdate(BaseModel):
    label: Optional[str] = None
    submission_deadline: Optional[date] = None
    status: Optional[str] = None
    instructions_text: Optional[str] = None


class BudgetYearResponse(BaseModel):
    id: int
    fiscal_year_id: int
    label: str
    submission_deadline: Optional[date]
    status: str
    instructions_text: Optional[str]
    created_by: int

    model_config = {"from_attributes": True}


class BudgetRequestCreate(BaseModel):
    budget_year_id: int
    account_id: int
    department: str
    prior_year_actual: Optional[Decimal] = None
    prior_year_budget: Optional[Decimal] = None
    proposed_amount: Optional[Decimal] = None
    justification_text: Optional[str] = None
    supporting_notes: Optional[str] = None


class BudgetRequestUpdate(BaseModel):
    proposed_amount: Optional[Decimal] = None
    justification_text: Optional[str] = None
    supporting_notes: Optional[str] = None
    status: Optional[str] = None


class BudgetApprovalRequest(BaseModel):
    approved_amount: Optional[Decimal] = None
    review_comment: Optional[str] = None


class BudgetRequestResponse(BaseModel):
    id: int
    budget_year_id: int
    account_id: int
    department: str
    prior_year_actual: Optional[Decimal]
    prior_year_budget: Optional[Decimal]
    proposed_amount: Optional[Decimal]
    justification_text: Optional[str]
    supporting_notes: Optional[str]
    submitted_by_user_id: int
    submitted_at: Optional[datetime]
    reviewed_by_user_id: Optional[int]
    review_comment: Optional[str]
    status: str
    approved_amount: Optional[Decimal]

    model_config = {"from_attributes": True}


class VarianceRow(BaseModel):
    account_id: int
    acct_fmtd: str
    description: Optional[str]
    approved_budget: Decimal
    ytd_actual: Decimal
    variance: Decimal
    variance_pct: Optional[Decimal]  # None if budget is zero


class VarianceReport(BaseModel):
    budget_year_id: int
    rows: List[VarianceRow]
    total_budget: Decimal
    total_actual: Decimal
    total_variance: Decimal
