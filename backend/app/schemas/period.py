from datetime import date
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
