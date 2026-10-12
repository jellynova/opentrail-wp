"""Materiality thresholds and the leadsheet accounts they flag (PLAN gap vs. CaseWare)."""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, field_validator


class MaterialitySet(BaseModel):
    overall_materiality: Decimal
    performance_materiality: Optional[Decimal] = None
    trivial_threshold: Optional[Decimal] = None
    basis: Optional[str] = None
    rationale: Optional[str] = None

    @field_validator("overall_materiality")
    @classmethod
    def _positive_overall(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("overall_materiality must be greater than zero")
        return v

    @field_validator("performance_materiality", "trivial_threshold")
    @classmethod
    def _non_negative(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v < 0:
            raise ValueError("must not be negative")
        return v


class MaterialityResponse(BaseModel):
    id: int
    fiscal_year_id: int
    overall_materiality: Decimal
    performance_materiality: Optional[Decimal] = None
    trivial_threshold: Optional[Decimal] = None
    # performance_materiality if set, else overall_materiality -- a convenience so the
    # UI doesn't have to re-derive which figure is actually used for flagging.
    flagging_threshold: Decimal
    basis: Optional[str] = None
    rationale: Optional[str] = None
    set_by_user_id: int
    set_by_username: Optional[str] = None
    set_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UnsupportedMaterialAccount(BaseModel):
    account_id: int
    acct_fmtd: str
    description: Optional[str] = None
    classification: Optional[str] = None
    final_balance: Decimal
    threshold: Decimal
    excess: Decimal


class UnsupportedMaterialAccountsResponse(BaseModel):
    period_id: int
    threshold: Optional[Decimal] = None
    threshold_basis: Optional[str] = None  # "performance_materiality" | "overall_materiality"
    accounts: List[UnsupportedMaterialAccount] = []
