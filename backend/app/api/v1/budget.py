from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_active_user, require_role
from app.models.budget import BudgetYear, BudgetRequest
from app.models.user import User
from app.schemas.budget import (
    BudgetYearCreate,
    BudgetYearUpdate,
    BudgetYearResponse,
    BudgetRequestCreate,
    BudgetRequestUpdate,
    BudgetApprovalRequest,
    BudgetRequestResponse,
    VarianceReport,
)
from app.services import budget_service as bsvc

router = APIRouter()


@router.get("/budget-years", response_model=List[BudgetYearResponse])
def list_budget_years(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return db.scalars(select(BudgetYear).order_by(BudgetYear.id.desc())).all()


@router.post("/budget-years", response_model=BudgetYearResponse, status_code=status.HTTP_201_CREATED)
def create_budget_year(
    data: BudgetYearCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin")),
):
    by = BudgetYear(
        fiscal_year_id=data.fiscal_year_id,
        label=data.label,
        submission_deadline=data.submission_deadline,
        status=data.status,
        instructions_text=data.instructions_text,
        created_by=current_user.id,
    )
    db.add(by)
    db.commit()
    db.refresh(by)
    return by


@router.get("/budget-years/{budget_year_id}", response_model=BudgetYearResponse)
def get_budget_year(
    budget_year_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    by = db.get(BudgetYear, budget_year_id)
    if by is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget year not found")
    return by


@router.put("/budget-years/{budget_year_id}", response_model=BudgetYearResponse)
def update_budget_year(
    budget_year_id: int,
    data: BudgetYearUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin")),
):
    by = db.get(BudgetYear, budget_year_id)
    if by is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget year not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(by, field, value)

    db.commit()
    db.refresh(by)
    return by


@router.get("/budget-years/{budget_year_id}/requests", response_model=List[BudgetRequestResponse])
def list_budget_requests(
    budget_year_id: int,
    department: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    stmt = select(BudgetRequest).where(BudgetRequest.budget_year_id == budget_year_id)
    if department:
        stmt = stmt.where(BudgetRequest.department == department)
    # budget_manager can only see their own submissions
    if current_user.role == "budget_manager":
        stmt = stmt.where(BudgetRequest.submitted_by_user_id == current_user.id)
    return db.scalars(stmt.order_by(BudgetRequest.department)).all()


@router.post(
    "/budget-years/{budget_year_id}/requests",
    response_model=BudgetRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_budget_request(
    budget_year_id: int,
    data: BudgetRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer", "budget_manager")),
):
    by = db.get(BudgetYear, budget_year_id)
    if by is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget year not found")
    if by.status not in ("open", "setup"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot submit requests for budget year in status '{by.status}'",
        )

    req = BudgetRequest(
        budget_year_id=budget_year_id,
        account_id=data.account_id,
        department=data.department,
        prior_year_actual=data.prior_year_actual,
        prior_year_budget=data.prior_year_budget,
        proposed_amount=data.proposed_amount,
        justification_text=data.justification_text,
        supporting_notes=data.supporting_notes,
        submitted_by_user_id=current_user.id,
        status="draft",
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


@router.put("/budget-requests/{request_id}", response_model=BudgetRequestResponse)
def update_budget_request(
    request_id: int,
    data: BudgetRequestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer", "budget_manager")),
):
    req = db.get(BudgetRequest, request_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget request not found")

    if current_user.role == "budget_manager" and req.submitted_by_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your request")

    if req.status not in ("draft", "modified"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot update a request in status '{req.status}'",
        )

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(req, field, value)

    db.commit()
    db.refresh(req)
    return req


@router.post("/budget-requests/{request_id}/submit", response_model=BudgetRequestResponse)
def submit_budget_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer", "budget_manager")),
):
    req = db.get(BudgetRequest, request_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget request not found")

    if current_user.role == "budget_manager" and req.submitted_by_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your request")

    if req.status not in ("draft", "modified"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot submit a request in status '{req.status}'",
        )

    req.status = "submitted"
    req.submitted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(req)
    return req


@router.post("/budget-requests/{request_id}/approve", response_model=BudgetRequestResponse)
def approve_budget_request(
    request_id: int,
    data: BudgetApprovalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    req = db.get(BudgetRequest, request_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget request not found")

    if req.status != "submitted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only approve a submitted request; current status is '{req.status}'",
        )

    req.status = "approved"
    req.reviewed_by_user_id = current_user.id
    req.review_comment = data.review_comment
    if data.approved_amount is not None:
        req.approved_amount = data.approved_amount
    else:
        req.approved_amount = req.proposed_amount

    db.commit()
    db.refresh(req)
    return req


@router.get("/budget-years/{budget_year_id}/variance", response_model=VarianceReport)
def get_variance_report(
    budget_year_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Generate budget vs actual variance report."""
    try:
        report = bsvc.get_variance_report(db=db, budget_year_id=budget_year_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return report
