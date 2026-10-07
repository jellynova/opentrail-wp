from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Literal, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.v1.export_utils import ExportFormat, money_json, tabular_response
from app.core.database import get_db
from app.core.security import get_current_active_user, require_role
from app.models.account import Account
from app.models.budget import BudgetAmendment, BudgetAmendmentLine, BudgetLine, BudgetRequest, BudgetYear
from app.models.connector import ExternalConnector
from app.models.user import User
from app.schemas.budget import (
    BudgetAmendmentApprove,
    BudgetAmendmentCreate,
    BudgetAmendmentResponse,
    BudgetApprovalRequest,
    BudgetConnectorImport,
    BudgetLineIn,
    BudgetLineResponse,
    BudgetRequestCreate,
    BudgetRequestResponse,
    BudgetRequestUpdate,
    BudgetReviewComment,
    BudgetYearCreate,
    BudgetYearResponse,
    BudgetYearUpdate,
)
from app.services import budget_service as bsvc

router = APIRouter()

FINANCE_ROLES = ("finance_admin", "finance_officer")

# Budget year workflow: setup → open → under_review → approved → adopted (one step back allowed
# until adoption; an adopted budget changes only through amendments).
ALLOWED_TRANSITIONS = {
    "setup": {"open"},
    "open": {"setup", "under_review"},
    "under_review": {"open", "approved"},
    "approved": {"under_review", "adopted"},
    "adopted": set(),
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _budget_year_or_404(db: Session, budget_year_id: int) -> BudgetYear:
    by = db.get(BudgetYear, budget_year_id)
    if by is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget year not found")
    return by


def _request_or_404(db: Session, request_id: int) -> BudgetRequest:
    req = db.get(BudgetRequest, request_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget request not found")
    return req


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _check_owner(req: BudgetRequest, user: User) -> None:
    if user.role == "budget_manager" and req.submitted_by_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your request")


def _require_not_adopted(by: BudgetYear) -> None:
    if by.status == "adopted":
        raise _bad_request("The budget is adopted; change it through an amendment")


def _validate_accounts(db: Session, by: BudgetYear, account_ids) -> None:
    ids = set(account_ids)
    found = db.scalars(select(Account).where(Account.id.in_(ids), Account.fiscal_year_id == by.fiscal_year_id)).all()
    missing = ids - {a.id for a in found}
    if missing:
        raise _bad_request(f"Account(s) {sorted(missing)} not found in the budget's fiscal year")


def _review_target(db: Session, request_id: int, user: User) -> BudgetRequest:
    req = _request_or_404(db, request_id)
    if req.status != "submitted":
        raise _bad_request(f"Can only review a submitted request; current status is '{req.status}'")
    by = _budget_year_or_404(db, req.budget_year_id)
    if by.status not in ("open", "under_review"):
        raise _bad_request(f"Budget year is '{by.status}'; requests can no longer be reviewed")
    if req.submitted_by_user_id == user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Cannot review a request you submitted (segregation of duties)")
    return req


# ---------------------------------------------------------------------------
# Budget years
# ---------------------------------------------------------------------------

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
    return _budget_year_or_404(db, budget_year_id)


@router.put("/budget-years/{budget_year_id}", response_model=BudgetYearResponse)
def update_budget_year(
    budget_year_id: int,
    data: BudgetYearUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin")),
):
    by = _budget_year_or_404(db, budget_year_id)
    updates = data.model_dump(exclude_unset=True)
    new_status = updates.pop("status", None)
    if new_status and new_status != by.status:
        if new_status not in ALLOWED_TRANSITIONS[by.status]:
            raise _bad_request(f"Cannot move a budget from '{by.status}' to '{new_status}'")
        if new_status == "adopted" and not db.scalars(
            select(BudgetLine).where(BudgetLine.budget_year_id == by.id)
        ).first():
            raise _bad_request("Cannot adopt a budget with no budget lines; consolidate or import lines first")
        by.status = new_status
    for field, value in updates.items():
        setattr(by, field, value)

    db.commit()
    db.refresh(by)
    return by


# ---------------------------------------------------------------------------
# Department requests
# ---------------------------------------------------------------------------

@router.get("/budget-years/{budget_year_id}/requests", response_model=List[BudgetRequestResponse])
def list_budget_requests(
    budget_year_id: int,
    department: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    stmt = select(BudgetRequest).where(BudgetRequest.budget_year_id == budget_year_id)
    if department:
        stmt = stmt.where(BudgetRequest.department == department)
    if status_filter:
        stmt = stmt.where(BudgetRequest.status == status_filter)
    # budget managers see their own submissions and their department's requests
    if current_user.role == "budget_manager":
        conditions = [BudgetRequest.submitted_by_user_id == current_user.id]
        if current_user.department:
            conditions.append(BudgetRequest.department == current_user.department)
        stmt = stmt.where(or_(*conditions))
    return db.scalars(stmt.order_by(BudgetRequest.department, BudgetRequest.id)).all()


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
    by = _budget_year_or_404(db, budget_year_id)
    allowed = ("open", "setup") if current_user.role in FINANCE_ROLES else ("open",)
    if by.status not in allowed:
        raise _bad_request(f"Cannot create requests for a budget year in status '{by.status}'")

    department = data.department or current_user.department
    if not department:
        raise _bad_request("department is required")
    if current_user.role == "budget_manager" and current_user.department and department != current_user.department:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"You can only submit requests for {current_user.department}")

    _validate_accounts(db, by, [data.account_id])
    account = db.get(Account, data.account_id)
    prior_actual, prior_budget = data.prior_year_actual, data.prior_year_budget
    if prior_actual is None or prior_budget is None:
        auto_actual, auto_budget = bsvc.prior_year_figures(db, by, account)
        prior_actual = auto_actual if prior_actual is None else prior_actual
        prior_budget = auto_budget if prior_budget is None else prior_budget

    req = BudgetRequest(
        budget_year_id=budget_year_id,
        account_id=data.account_id,
        department=department,
        prior_year_actual=prior_actual,
        prior_year_budget=prior_budget,
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
    req = _request_or_404(db, request_id)
    _check_owner(req, current_user)
    if req.status != "draft":
        raise _bad_request(f"Cannot update a request in status '{req.status}'")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(req, field, value)

    db.commit()
    db.refresh(req)
    return req


@router.delete("/budget-requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer", "budget_manager")),
):
    req = _request_or_404(db, request_id)
    _check_owner(req, current_user)
    if req.status != "draft":
        raise _bad_request("Only draft requests can be deleted")
    db.delete(req)
    db.commit()


@router.post("/budget-requests/{request_id}/submit", response_model=BudgetRequestResponse)
def submit_budget_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer", "budget_manager")),
):
    req = _request_or_404(db, request_id)
    _check_owner(req, current_user)
    if req.status != "draft":
        raise _bad_request(f"Cannot submit a request in status '{req.status}'")
    by = _budget_year_or_404(db, req.budget_year_id)
    if by.status != "open":
        raise _bad_request(f"Budget year is '{by.status}'; submissions are closed")
    if req.proposed_amount is None:
        raise _bad_request("A proposed amount is required before submitting")

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
    current_user: User = Depends(require_role(*FINANCE_ROLES)),
):
    """Approve as requested, or at a different amount (status 'modified')."""
    req = _review_target(db, request_id, current_user)
    amount = data.approved_amount if data.approved_amount is not None else req.proposed_amount
    req.approved_amount = amount
    req.status = "approved" if Decimal(str(amount)) == Decimal(str(req.proposed_amount)) else "modified"
    req.reviewed_by_user_id = current_user.id
    req.review_comment = data.review_comment
    db.commit()
    db.refresh(req)
    return req


@router.post("/budget-requests/{request_id}/reject", response_model=BudgetRequestResponse)
def reject_budget_request(
    request_id: int,
    data: BudgetReviewComment,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*FINANCE_ROLES)),
):
    req = _review_target(db, request_id, current_user)
    req.status = "rejected"
    req.approved_amount = None
    req.reviewed_by_user_id = current_user.id
    req.review_comment = data.review_comment
    db.commit()
    db.refresh(req)
    return req


@router.post("/budget-requests/{request_id}/return", response_model=BudgetRequestResponse)
def return_budget_request(
    request_id: int,
    data: BudgetReviewComment,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*FINANCE_ROLES)),
):
    """Send a submitted request back to the department as a draft for revision."""
    req = _review_target(db, request_id, current_user)
    req.status = "draft"
    req.reviewed_by_user_id = current_user.id
    req.review_comment = data.review_comment
    db.commit()
    db.refresh(req)
    return req


# ---------------------------------------------------------------------------
# Budget lines (the consolidated / adopted budget)
# ---------------------------------------------------------------------------

@router.get("/budget-years/{budget_year_id}/lines", response_model=List[BudgetLineResponse])
def list_budget_lines(
    budget_year_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _budget_year_or_404(db, budget_year_id)
    return db.scalars(select(BudgetLine).where(BudgetLine.budget_year_id == budget_year_id)
                      .order_by(BudgetLine.account_id)).all()


@router.put("/budget-years/{budget_year_id}/lines", response_model=List[BudgetLineResponse])
def replace_budget_lines(
    budget_year_id: int,
    lines: List[BudgetLineIn],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin")),
):
    """Replace all budget lines (manual entry). Not permitted once adopted."""
    by = _budget_year_or_404(db, budget_year_id)
    _require_not_adopted(by)
    _validate_accounts(db, by, [l.account_id for l in lines])
    for bl in db.scalars(select(BudgetLine).where(BudgetLine.budget_year_id == by.id)).all():
        db.delete(bl)
    for l in lines:
        acct = db.get(Account, l.account_id)
        db.add(BudgetLine(budget_year_id=by.id, account_id=l.account_id, approved_amount=l.approved_amount,
                          budget_type=l.budget_type or ("capital" if acct.capital_acct else "operating")))
    db.commit()
    return db.scalars(select(BudgetLine).where(BudgetLine.budget_year_id == by.id)).all()


@router.post("/budget-years/{budget_year_id}/consolidate")
def consolidate_budget(
    budget_year_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin")),
):
    """Build budget lines from approved (and modified) department requests."""
    by = _budget_year_or_404(db, budget_year_id)
    _require_not_adopted(by)
    pending = db.scalars(select(BudgetRequest).where(
        BudgetRequest.budget_year_id == by.id, BudgetRequest.status == "submitted")).all()
    count = bsvc.consolidate_requests(db, by)
    return {"lines": count, "requests_pending_review": len(pending)}


@router.post("/budget-years/{budget_year_id}/lines/import/csv")
async def import_budget_lines_csv(
    budget_year_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin")),
):
    """Replace budget lines from a CSV with Account and Amount columns."""
    by = _budget_year_or_404(db, budget_year_id)
    _require_not_adopted(by)
    totals, errors = bsvc.lines_from_csv(db, by, await file.read())
    count = bsvc.replace_lines(db, by, totals) if totals else 0
    return {"lines": count, "errors": errors}


@router.post("/budget-years/{budget_year_id}/lines/import/connector")
def import_budget_lines_connector(
    budget_year_id: int,
    data: BudgetConnectorImport,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin")),
):
    """Replace budget lines from the ERP budget table (AMAIS gl-bud) for one rec-type."""
    from app.services import sql_connector

    by = _budget_year_or_404(db, budget_year_id)
    _require_not_adopted(by)
    connector = db.get(ExternalConnector, data.connector_id)
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")
    try:
        rows = sql_connector.pull_budget(connector, data.fiscal_year)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Connector pull failed: {exc}")
    totals, errors = bsvc.lines_from_connector_rows(db, by, rows, data.rec_type)
    count = bsvc.replace_lines(db, by, totals) if totals else 0
    return {"lines": count, "errors": errors}


# ---------------------------------------------------------------------------
# Amendments
# ---------------------------------------------------------------------------

@router.get("/budget-years/{budget_year_id}/amendments", response_model=List[BudgetAmendmentResponse])
def list_amendments(
    budget_year_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return db.scalars(select(BudgetAmendment).where(BudgetAmendment.budget_year_id == budget_year_id)
                      .order_by(BudgetAmendment.amendment_number)).all()


@router.post("/budget-years/{budget_year_id}/amendments", response_model=BudgetAmendmentResponse,
             status_code=status.HTTP_201_CREATED)
def create_amendment(
    budget_year_id: int,
    data: BudgetAmendmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*FINANCE_ROLES)),
):
    by = _budget_year_or_404(db, budget_year_id)
    if by.status != "adopted":
        raise _bad_request("Amendments apply to an adopted budget; edit budget lines directly before adoption")
    _validate_accounts(db, by, [l.account_id for l in data.lines])
    amendment = BudgetAmendment(
        budget_year_id=by.id,
        amendment_number=bsvc.next_amendment_number(db, by.id),
        approval_reference=data.approval_reference,
        rationale=data.rationale,
        status="draft",
        created_by_user_id=current_user.id,
    )
    db.add(amendment)
    db.flush()
    for l in data.lines:
        db.add(BudgetAmendmentLine(amendment_id=amendment.id, account_id=l.account_id, amount=l.amount,
                                   description=l.description))
    db.commit()
    db.refresh(amendment)
    return amendment


@router.post("/budget-amendments/{amendment_id}/approve", response_model=BudgetAmendmentResponse)
def approve_amendment(
    amendment_id: int,
    data: BudgetAmendmentApprove,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin")),
):
    amendment = db.get(BudgetAmendment, amendment_id)
    if amendment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Amendment not found")
    if amendment.status != "draft":
        raise _bad_request("Amendment is already approved")
    reference = data.approval_reference or amendment.approval_reference
    if not reference:
        raise _bad_request("An approval reference (bylaw or resolution number) is required")
    amendment.status = "approved"
    amendment.approval_reference = reference
    amendment.approved_date = data.approved_date or date.today()
    amendment.approved_by_user_id = current_user.id
    db.commit()
    db.refresh(amendment)
    return amendment


@router.delete("/budget-amendments/{amendment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_amendment(
    amendment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*FINANCE_ROLES)),
):
    amendment = db.get(BudgetAmendment, amendment_id)
    if amendment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Amendment not found")
    if amendment.status != "draft":
        raise _bad_request("Approved amendments cannot be deleted; record an offsetting amendment")
    db.delete(amendment)
    db.commit()


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@router.get("/budget-years/{budget_year_id}/variance")
def get_variance_report(
    budget_year_id: int,
    period_id: Optional[int] = Query(None, description="Actuals through this period (default: year end)"),
    group_by: Literal["account", "department", "classification"] = Query("account"),
    department: Optional[str] = Query(None, description="Drill down to one department"),
    amber_pct: Decimal = Query(Decimal("5")),
    red_pct: Decimal = Query(Decimal("10")),
    format: ExportFormat = Query("json"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Budget vs actual with original/amended budget, favourable-positive variance and status."""
    try:
        report = bsvc.variance_report(db, budget_year_id, period_id, group_by, department, amber_pct, red_pct)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if format == "json":
        return money_json(report)
    return tabular_response(bsvc.variance_table(report), format, f"Budget_vs_Actual_{report['budget_year']}")


@router.get("/budget-years/{budget_year_id}/multi-year")
def get_multi_year(
    budget_year_id: int,
    group_by: Literal["account", "department", "classification"] = Query("classification"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _budget_year_or_404(db, budget_year_id)
    return money_json(bsvc.multi_year_comparison(db, budget_year_id, group_by))


@router.get("/budget-years/{budget_year_id}/council-report")
def get_council_report(
    budget_year_id: int,
    group_by: Literal["department", "classification"] = Query("classification"),
    format: ExportFormat = Query("json"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Council-ready budget: proposed budget vs prior-year budget and actual, by function or department."""
    by = _budget_year_or_404(db, budget_year_id)
    return tabular_response(bsvc.council_report(db, budget_year_id, group_by), format, f"Budget_{by.label}")
