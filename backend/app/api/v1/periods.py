from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_active_user, require_role
from app.models.period import FiscalYear, Period, PeriodClose
from app.models.user import User
from app.schemas.period import (
    CloseRequest,
    FiscalYearCreate,
    FiscalYearUpdate,
    FiscalYearResponse,
    FiscalYearWithPeriods,
    PeriodCloseBalanceResponse,
    PeriodCloseResponse,
    PeriodCreate,
    PeriodUpdate,
    PeriodResponse,
    PreCloseCheckResponse,
    ReopenRequest,
    RollForwardRequest,
    RollForwardResponse,
)
from app.services import audit as audit_svc
from app.services import period_close as close_svc

router = APIRouter()


def _usernames(db: Session, ids) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: u.username for u in db.scalars(select(User).where(User.id.in_(ids))).all()}


def _close_response(db: Session, close: PeriodClose, include_balances: bool = True) -> PeriodCloseResponse:
    period = db.get(Period, close.period_id)
    fy = db.get(FiscalYear, period.fiscal_year_id) if period else None
    usernames = _usernames(db, {close.closed_by_user_id})
    return PeriodCloseResponse(
        id=close.id,
        period_id=close.period_id,
        period_name=period.name if period else None,
        fiscal_year_label=fy.label if fy else None,
        closed_by_user_id=close.closed_by_user_id,
        closed_by_username=usernames.get(close.closed_by_user_id),
        closed_at=close.closed_at,
        notes=close.notes,
        journal_entry_count=close.journal_entry_count,
        account_count=close.account_count,
        total_debits=close.total_debits,
        total_credits=close.total_credits,
        is_balanced=close.is_balanced,
        overrides=close.overrides,
        balances=[PeriodCloseBalanceResponse.model_validate(b) for b in close.balances] if include_balances else [],
    )


def _close_blocked(exc: "close_svc.CloseBlocked") -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"message": str(exc), "reasons": exc.reasons})


@router.get("/fiscal-years", response_model=List[FiscalYearResponse])
def list_fiscal_years(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return db.scalars(select(FiscalYear).order_by(FiscalYear.start_date.desc())).all()


@router.post("/fiscal-years", response_model=FiscalYearResponse, status_code=status.HTTP_201_CREATED)
def create_fiscal_year(
    data: FiscalYearCreate,
    request: Request,
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
    db.flush()
    audit_svc.record(
        db,
        user=current_user,
        action="create",
        resource_type="fiscal_year",
        resource_id=fy.id,
        new={"label": fy.label, "start_date": fy.start_date, "end_date": fy.end_date, "status": fy.status},
        summary=f"created fiscal year {fy.label}",
        request=request,
        commit=True,
    )
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
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin")),
):
    fy = db.get(FiscalYear, fiscal_year_id)
    if fy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fiscal year not found")

    if fy.status == "locked":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot modify a locked fiscal year")
    before = audit_svc.snapshot(fy, ["label", "start_date", "end_date", "status"])

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

    db.flush()
    audit_svc.record(
        db,
        user=current_user,
        action="update",
        resource_type="fiscal_year",
        resource_id=fy.id,
        old=before,
        new=audit_svc.snapshot(fy, ["label", "start_date", "end_date", "status"]),
        summary=f"updated fiscal year {fy.label}",
        request=request,
        commit=True,
    )
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
    request: Request,
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
    db.flush()
    audit_svc.record(
        db,
        user=current_user,
        action="create",
        resource_type="period",
        resource_id=period.id,
        new={"fiscal_year_id": fiscal_year_id, "period_number": period.period_number, "name": period.name},
        summary=f"created period {period.name}",
        request=request,
        commit=True,
    )
    db.refresh(period)
    return period


@router.put("/periods/{period_id}", response_model=PeriodResponse)
def update_period(
    period_id: int,
    data: PeriodUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    period = db.get(Period, period_id)
    if period is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Period not found")
    before = audit_svc.snapshot(period, ["name", "start_date", "end_date", "is_closed"])

    if data.name is not None:
        period.name = data.name
    if data.start_date is not None:
        period.start_date = data.start_date
    if data.end_date is not None:
        period.end_date = data.end_date
    if data.is_closed is not None:
        period.is_closed = data.is_closed

    db.flush()
    audit_svc.record(
        db,
        user=current_user,
        action="update",
        resource_type="period",
        resource_id=period.id,
        old=before,
        new=audit_svc.snapshot(period, ["name", "start_date", "end_date", "is_closed"]),
        summary=f"updated period {period.name}",
        request=request,
        commit=True,
    )
    db.refresh(period)
    return period


@router.get("/periods/{period_id}/close-check", response_model=PreCloseCheckResponse)
def period_close_check(
    period_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Pre-close checks for a period: unposted journal entries and unsigned working papers."""
    period = db.get(Period, period_id)
    if period is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Period not found")
    findings = close_svc.preclose_check(db, period)
    return PreCloseCheckResponse(**findings)


@router.post("/periods/{period_id}/close", response_model=PeriodCloseResponse)
def close_period(
    period_id: int,
    request: Request,
    data: Optional[CloseRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """
    Close a period and snapshot its closing balances (PLAN §7.3).

    All journal entries in the period must be posted. Working papers for the fiscal year
    must be reviewed and signed off, unless a finance_admin forces the close.
    """
    data = data or CloseRequest()
    if data.force and current_user.role != "finance_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a finance_admin can close a period with unsigned working papers",
        )
    try:
        close = close_svc.close_period(
            db, period_id, current_user, notes=data.notes, force=data.force, request=request
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except close_svc.CloseBlocked as exc:
        raise _close_blocked(exc)
    return _close_response(db, close)


@router.post("/periods/{period_id}/reopen", response_model=PeriodResponse)
def reopen_period(
    period_id: int,
    request: Request,
    data: Optional[ReopenRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin")),
):
    """Reopen a closed period for corrections (finance_admin only)."""
    data = data or ReopenRequest()
    try:
        period = close_svc.reopen_period(db, period_id, current_user, reason=data.reason, request=request)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except close_svc.CloseBlocked as exc:
        raise _close_blocked(exc)
    return period


@router.get("/periods/{period_id}/close", response_model=PeriodCloseResponse)
def get_period_close(
    period_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """The closing balance snapshot recorded when the period was closed."""
    close = close_svc.period_close_detail(db, period_id)
    if close is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This period has not been closed")
    return _close_response(db, close)


@router.post("/fiscal-years/{fiscal_year_id}/close", response_model=FiscalYearResponse)
def close_fiscal_year(
    fiscal_year_id: int,
    request: Request,
    data: Optional[CloseRequest] = None,
    force: bool = Query(False, description="Deprecated alias for the force flag in the body"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin")),
):
    """
    Close a fiscal year: every period is closed in order (with its balance snapshot) after
    the pre-close checks pass, then the year is marked closed.
    """
    data = data or CloseRequest(force=force)
    force_flag = data.force or force
    try:
        result = close_svc.close_fiscal_year(db, fiscal_year_id, current_user, force=force_flag, request=request)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except close_svc.CloseBlocked as exc:
        raise _close_blocked(exc)
    return result["fiscal_year"]


@router.post("/fiscal-years/{fiscal_year_id}/roll-forward", response_model=RollForwardResponse)
def roll_forward_fiscal_year(
    fiscal_year_id: int,
    request: Request,
    data: Optional[RollForwardRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin")),
):
    """
    Roll a closed fiscal year forward (PLAN §1.3 / §7.3): create the next year and its
    periods, copy the chart of accounts, ERP mappings and classifications, and post each
    account's prior-year closing balance as the new year's opening balance.
    """
    data = data or RollForwardRequest()
    try:
        summary = close_svc.roll_forward(db, fiscal_year_id, current_user, label=data.label, request=request)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except close_svc.CloseBlocked as exc:
        raise _close_blocked(exc)

    return RollForwardResponse(
        fiscal_year=FiscalYearResponse.model_validate(summary["fiscal_year"]),
        periods_created=summary["periods_created"],
        accounts_copied=summary["accounts_copied"],
        account_mappings_copied=summary["account_mappings_copied"],
        classifications_copied=summary["classifications_copied"],
        opening_balances_posted=summary["opening_balances_posted"],
        opening_debits=summary["opening_debits"],
        opening_credits=summary["opening_credits"],
        balanced=summary["balanced"],
        net_surplus=summary["net_surplus"],
        surplus_account=summary["surplus_account"],
        warnings=summary["warnings"],
    )
