from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional
from pydantic import BaseModel, Field

BudgetYearStatus = Literal["setup", "open", "under_review", "approved", "adopted"]


class BudgetYearCreate(BaseModel):
    fiscal_year_id: int
    label: str
    submission_deadline: Optional[date] = None
    status: BudgetYearStatus = "setup"
    instructions_text: Optional[str] = None


class BudgetYearUpdate(BaseModel):
    label: Optional[str] = None
    submission_deadline: Optional[date] = None
    status: Optional[BudgetYearStatus] = None
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
    budget_year_id: Optional[int] = None  # taken from the URL
    account_id: int
    department: Optional[str] = None  # defaults to the requesting user's department
    prior_year_actual: Optional[Decimal] = None  # filled from the prior year when omitted
    prior_year_budget: Optional[Decimal] = None
    proposed_amount: Optional[Decimal] = Field(None, ge=0)
    justification_text: Optional[str] = None
    supporting_notes: Optional[str] = None


class BudgetRequestUpdate(BaseModel):
    # Status changes go through the submit / approve / reject / return endpoints only.
    # Optimistic locking (PLAN §8.1): the version the client loaded.
    version: Optional[int] = None
    proposed_amount: Optional[Decimal] = Field(None, ge=0)
    justification_text: Optional[str] = None
    supporting_notes: Optional[str] = None


class BudgetApprovalRequest(BaseModel):
    approved_amount: Optional[Decimal] = Field(None, ge=0)
    review_comment: Optional[str] = None


class BudgetReviewComment(BaseModel):
    review_comment: str


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
    version: int = 1

    model_config = {"from_attributes": True}


class BudgetLineIn(BaseModel):
    account_id: int
    approved_amount: Decimal
    budget_type: Optional[Literal["operating", "capital"]] = None


class BudgetLineResponse(BaseModel):
    id: int
    budget_year_id: int
    account_id: int
    approved_amount: Decimal
    budget_type: str

    model_config = {"from_attributes": True}


class BudgetAmendmentLineIn(BaseModel):
    account_id: int
    amount: Decimal  # change to the budget: positive increases, negative decreases
    description: Optional[str] = None


class BudgetAmendmentCreate(BaseModel):
    approval_reference: Optional[str] = None
    rationale: Optional[str] = None
    lines: List[BudgetAmendmentLineIn] = Field(min_length=1)


class BudgetAmendmentApprove(BaseModel):
    approved_date: Optional[date] = None
    approval_reference: Optional[str] = None


class BudgetAmendmentLineResponse(BudgetAmendmentLineIn):
    id: int

    model_config = {"from_attributes": True}


class BudgetAmendmentResponse(BaseModel):
    id: int
    budget_year_id: int
    amendment_number: int
    approval_reference: Optional[str]
    rationale: Optional[str]
    status: str
    approved_date: Optional[date]
    created_by_user_id: int
    approved_by_user_id: Optional[int]
    created_at: datetime
    lines: List[BudgetAmendmentLineResponse] = []

    model_config = {"from_attributes": True}


class BudgetConnectorImport(BaseModel):
    connector_id: int
    fiscal_year: int  # ERP fiscal year number
    rec_type: str  # AMAIS gl-bud rec-type to use as the budget (e.g. "B1")
