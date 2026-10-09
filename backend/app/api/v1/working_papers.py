from typing import List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.export_utils import ExportFormat, money_json, tabular_response
from app.core.database import get_db
from app.core.security import get_current_active_user, require_role
from app.models.document import WorkingPaper
from app.models.document_links import DocumentAccountLink
from app.models.period import FiscalYear
from app.models.user import User
from app.schemas.document_links import AccountLinkCreate, AccountLinkResponse
from app.services import audit as audit_svc
from app.services import working_papers as wp

router = APIRouter()


@router.get("/working-papers/trial-balance")
def get_working_trial_balance(
    period_id: int = Query(...),
    scheme: Optional[str] = Query(None, description="Mapping scheme name or id to attach classifications"),
    format: ExportFormat = Query("json"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Working trial balance: opening → unadjusted → AJE → RJE → final per account."""
    try:
        if format != "json":
            return tabular_response(wp.wtb_table(db, period_id), format, "Working_Trial_Balance")
        return money_json(wp.working_trial_balance(db, period_id, scheme))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/working-papers/leadsheets")
def get_leadsheets(
    period_id: int = Query(...),
    scheme: str = Query("PSAB", description="Mapping scheme name or id"),
    format: ExportFormat = Query("json"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Leadsheets grouped by classification with prior-year comparatives."""
    try:
        if format != "json":
            return tabular_response(wp.leadsheets_table(db, period_id, scheme), format, "Leadsheets")
        return money_json(wp.leadsheets(db, period_id, scheme))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/working-papers/je-schedule")
def get_je_schedule(
    fiscal_year_id: int = Query(...),
    entry_type: Literal["adjusting", "reclassifying", "elimination", "budget_variance"] = Query("adjusting"),
    include_drafts: bool = Query(False),
    format: ExportFormat = Query("json"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Adjusting (AJE) or reclassification (RJE) journal entry schedule for a fiscal year."""
    if db.get(FiscalYear, fiscal_year_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fiscal year not found")
    if format != "json":
        table = wp.je_schedule_table(db, fiscal_year_id, entry_type, include_drafts)
        return tabular_response(table, format, f"{entry_type}_entries")
    return money_json(wp.journal_entry_schedule(db, fiscal_year_id, entry_type, include_drafts))


@router.get("/working-papers/package")
def get_working_paper_package(
    period_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """ZIP of the working TB, leadsheets, AJE/RJE schedules and PSAB statements (Excel + PDF)."""
    try:
        content = wp.working_paper_package(db, period_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return Response(content=content, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="working_papers_{period_id}.zip"'})


# ── Leadsheet-to-document account links (PLAN §4.3) ──────────────────────────


def _link_response(db: Session, link: DocumentAccountLink) -> AccountLinkResponse:
    username = db.scalars(
        select(User.username).where(User.id == link.created_by_user_id)
    ).first()
    paper = db.get(WorkingPaper, link.working_paper_id)
    return AccountLinkResponse(
        id=link.id,
        working_paper_id=link.working_paper_id,
        account_code=link.account_code,
        fiscal_year_id=link.fiscal_year_id,
        created_by_user_id=link.created_by_user_id,
        created_by_username=username,
        created_at=link.created_at,
        document_display_name=paper.display_name if paper else None,
        document_folder_path=paper.folder_path if paper else None,
    )


def _get_paper_or_404(db: Session, working_paper_id: int) -> WorkingPaper:
    paper = db.get(WorkingPaper, working_paper_id)
    if paper is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Working paper not found")
    return paper


@router.post(
    "/working-papers/{working_paper_id}/account-links",
    response_model=AccountLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_account_link(
    working_paper_id: int,
    data: AccountLinkCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Attach a working paper document to a leadsheet account code (officer and above)."""
    paper = _get_paper_or_404(db, working_paper_id)
    if db.get(FiscalYear, data.fiscal_year_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fiscal year not found")

    account_code = data.account_code.strip()
    if not account_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="account_code must not be empty")

    existing = db.scalars(
        select(DocumentAccountLink).where(
            DocumentAccountLink.working_paper_id == working_paper_id,
            DocumentAccountLink.account_code == account_code,
        )
    ).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Account {account_code} is already linked to this document",
        )

    link = DocumentAccountLink(
        working_paper_id=working_paper_id,
        account_code=account_code,
        fiscal_year_id=data.fiscal_year_id,
        created_by_user_id=current_user.id,
    )
    db.add(link)
    db.flush()
    audit_svc.record(
        db,
        user=current_user,
        action="create",
        resource_type="document_account_link",
        resource_id=link.id,
        new={
            "working_paper_id": working_paper_id,
            "account_code": account_code,
            "fiscal_year_id": data.fiscal_year_id,
        },
        summary=f"linked document {paper.display_name} to account {account_code}",
        request=request,
        commit=True,
    )
    db.refresh(link)
    return _link_response(db, link)


@router.get(
    "/working-papers/{working_paper_id}/account-links",
    response_model=List[AccountLinkResponse],
)
def list_account_links(
    working_paper_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """All leadsheet account codes linked to a document (any authenticated user)."""
    _get_paper_or_404(db, working_paper_id)
    links = db.scalars(
        select(DocumentAccountLink)
        .where(DocumentAccountLink.working_paper_id == working_paper_id)
        .order_by(DocumentAccountLink.account_code)
    ).all()
    return [_link_response(db, link) for link in links]


@router.delete(
    "/working-papers/{working_paper_id}/account-links/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_account_link(
    working_paper_id: int,
    link_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Detach a leadsheet account code from a document (officer and above)."""
    _get_paper_or_404(db, working_paper_id)
    link = db.get(DocumentAccountLink, link_id)
    if link is None or link.working_paper_id != working_paper_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account link not found")

    code = link.account_code
    db.delete(link)
    db.flush()
    audit_svc.record(
        db,
        user=current_user,
        action="delete",
        resource_type="document_account_link",
        resource_id=link_id,
        old={"working_paper_id": working_paper_id, "account_code": code},
        summary=f"unlinked account {code} from working paper #{working_paper_id}",
        request=request,
        commit=True,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/working-papers/by-account/{account_code}",
    response_model=List[AccountLinkResponse],
)
def links_by_account(
    account_code: str,
    fiscal_year_id: Optional[int] = Query(None, description="Scope the lookup to one fiscal year"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Documents linked to a leadsheet account code (any authenticated user)."""
    stmt = select(DocumentAccountLink).where(DocumentAccountLink.account_code == account_code)
    if fiscal_year_id is not None:
        stmt = stmt.where(DocumentAccountLink.fiscal_year_id == fiscal_year_id)
    links = db.scalars(stmt.order_by(DocumentAccountLink.created_at)).all()
    return [_link_response(db, link) for link in links]
