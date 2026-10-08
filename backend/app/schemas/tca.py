from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class TcaLineIn(BaseModel):
    asset_class: str = Field(min_length=1, max_length=200)
    sort_order: Optional[int] = None
    notes: Optional[str] = None
    cost_opening: Decimal = Decimal("0")
    cost_additions: Decimal = Decimal("0")
    cost_disposals: Decimal = Decimal("0")
    amort_opening: Decimal = Decimal("0")
    amort_expense: Decimal = Decimal("0")
    amort_disposals: Decimal = Decimal("0")


class TcaLineResponse(BaseModel):
    id: int
    fiscal_year_id: int
    asset_class: str
    sort_order: int
    notes: Optional[str]
    cost_opening: Decimal
    cost_additions: Decimal
    cost_disposals: Decimal
    cost_closing: Decimal
    amort_opening: Decimal
    amort_expense: Decimal
    amort_disposals: Decimal
    amort_closing: Decimal
    nbv_opening: Decimal
    nbv_closing: Decimal
    source: str

    model_config = {"from_attributes": True}


class TcaReplaceRequest(BaseModel):
    lines: List[TcaLineIn]


class TcaReplaceResponse(BaseModel):
    lines_saved: int
    totals: dict


class TcaImportResponse(BaseModel):
    records_imported: int
    errors: List[str] = []


class TcaRollForwardResponse(BaseModel):
    applied: int
    created: int
    prior_year: Optional[str] = None
    warnings: List[str] = []
