from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_active_user, require_role
from app.models.period import FiscalYear, Period
from app.models.user import User
from app.schemas.period import (
    FiscalYearCreate,
    FiscalYearUpdate,
    FiscalYearResponse,
    FiscalYearWithPeriods,
    PeriodCreate,
    PeriodUpdate,
    PeriodResponse,
)

router = APIRouter()


@router.get("/fiscal-years", response_model=List[FiscalYearResponse])
def list_fiscal_years(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return db.scalars(select(FiscalYear).order_by(FiscalYear.start_date.desc())).all()


@router.post("/fiscal-years", response_model=FiscalYearResponse, status_code=status.HTTP_201_CREATED)
def create_fiscal_year(
    data: FiscalYearCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin")),
):
    fy = FiscalYear(
        label=data.label,
        start_date=data.start_date,
        end_date=data.end_date,
        status=data.status,
    )
    db.add(fy)
    db.commit()
    db.refresh(fy)
    return fy


@router.get("/fiscal-years/{fiscal_year_id}", response_model=FiscalYearWithPeriods)
def get_fiscal_year(
    fiscal_year_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    fy = db.get(FiscalYear, fiscal_year_id)
    if fy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fiscal year not found")
    return fy


@router.put("/fiscal-years/{fiscal_year_id}", response_model=FiscalYearResponse)
def update_fiscal_year(
    fiscal_year_id: int,
    data: FiscalYearUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin")),
):
    fy = db.get(FiscalYear, fiscal_year_id)
    if fy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fiscal year not found")

    if fy.status == "locked":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot modify a locked fiscal year")

    if data.label is not None:
        fy.label = data.label
    if data.start_date is not None:
        fy.start_date = data.start_date
    if data.end_date is not None:
        fy.end_date = data.end_date
    if data.status is not None:
        valid_statuses = {"open", "closed", "locked"}
        if data.status not in valid_statuses:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status: {data.status}")
        fy.status = data.status

    db.commit()
    db.refresh(fy)
    return fy


@router.get("/fiscal-years/{fiscal_year_id}/periods", response_model=List[PeriodResponse])
def list_periods(
    fiscal_year_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    fy = db.get(FiscalYear, fiscal_year_id)
    if fy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fiscal year not found")
    return db.scalars(
        select(Period)
        .where(Period.fiscal_year_id == fiscal_year_id)
        .order_by(Period.period_number)
    ).all()


@router.post(
    "/fiscal-years/{fiscal_year_id}/periods",
    response_model=PeriodResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_period(
    fiscal_year_id: int,
    data: PeriodCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    fy = db.get(FiscalYear, fiscal_year_id)
    if fy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fiscal year not found")
    if fy.status == "locked":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Fiscal year is locked")

    # Check for duplicate period number
    existing = db.scalars(
        select(Period).where(
            Period.fiscal_year_id == fiscal_year_id,
            Period.period_number == data.period_number,
        )
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Period {data.period_number} already exists for this fiscal year",
        )

    period = Period(
        fiscal_year_id=fiscal_year_id,
        period_number=data.period_number,
        name=data.name,
        start_date=data.start_date,
        end_date=data.end_date,
        is_closed=data.is_closed,
    )
    db.add(period)
    db.commit()
    db.refresh(period)
    return period


@router.put("/periods/{period_id}", response_model=PeriodResponse)
def update_period(
    period_id: int,
    data: PeriodUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    period = db.get(Period, period_id)
    if period is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Period not found")

    if data.name is not None:
        period.name = data.name
    if data.start_date is not None:
        period.start_date = data.start_date
    if data.end_date is not None:
        period.end_date = data.end_date
    if data.is_closed is not None:
        period.is_closed = data.is_closed

    db.commit()
    db.refresh(period)
    return period


@router.post("/fiscal-years/{fiscal_year_id}/close", response_model=FiscalYearResponse)
def close_fiscal_year(
    fiscal_year_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin")),
):
    """Close a fiscal year and mark all its periods as closed."""
    fy = db.get(FiscalYear, fiscal_year_id)
    if fy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fiscal year not found")
    if fy.status == "locked":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Fiscal year is already locked")

    fy.status = "closed"
    periods = db.scalars(select(Period).where(Period.fiscal_year_id == fiscal_year_id)).all()
    for p in periods:
        p.is_closed = True

    db.commit()
    db.refresh(fy)
    return fy
