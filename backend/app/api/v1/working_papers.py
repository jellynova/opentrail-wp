from datetime import datetime, timezone
from typing import List, Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.export_utils import ExportFormat, money_json, tabular_response
from app.core.database import get_db
from app.core.security import get_current_active_user, require_role
from app.models.document import WorkingPaper
from app.models.document_links import DocumentAccountLink, DocumentCrossLink
from app.models.account_comment import AccountComment
from app.models.period import FiscalYear
from app.models.user import User
from app.schemas.document_links import (
    AccountCommentCreate,
    AccountCommentResponse,
    AccountLinkCreate,
    AccountLinkResponse,
    RelatedDocumentCreate,
    RelatedDocumentResponse,
)
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


# ── Document-to-document cross-references ("file linking") ──────────────────


def _cross_link_response(db: Session, link: DocumentCrossLink, from_document_id: int) -> RelatedDocumentResponse:
    """Report the link from ``from_document_id``'s point of view, whichever side it's on."""
    other_id = link.related_document_id if link.document_id == from_document_id else link.document_id
    other = db.get(WorkingPaper, other_id)
    username = db.scalars(select(User.username).where(User.id == link.created_by_user_id)).first()
    return RelatedDocumentResponse(
        id=link.id,
        document_id=from_document_id,
        related_document_id=other_id,
        related_document_display_name=other.display_name if other else None,
        related_document_folder_path=other.folder_path if other else None,
        related_document_file_type=other.file_type if other else None,
        note=link.note,
        created_by_user_id=link.created_by_user_id,
        created_by_username=username,
        created_at=link.created_at,
    )


@router.post(
    "/working-papers/{working_paper_id}/related-documents",
    response_model=RelatedDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_related_document(
    working_paper_id: int,
    data: RelatedDocumentCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Cross-reference two documents so reviewers can jump between related evidence."""
    paper = _get_paper_or_404(db, working_paper_id)
    if data.related_document_id == working_paper_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A document cannot be linked to itself")
    other = _get_paper_or_404(db, data.related_document_id)

    existing = db.scalars(
        select(DocumentCrossLink).where(
            ((DocumentCrossLink.document_id == working_paper_id)
             & (DocumentCrossLink.related_document_id == data.related_document_id))
            | ((DocumentCrossLink.document_id == data.related_document_id)
               & (DocumentCrossLink.related_document_id == working_paper_id))
        )
    ).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="These documents are already linked")

    link = DocumentCrossLink(
        document_id=working_paper_id,
        related_document_id=data.related_document_id,
        note=(data.note.strip() if data.note else None) or None,
        created_by_user_id=current_user.id,
    )
    db.add(link)
    db.flush()
    audit_svc.record(
        db,
        user=current_user,
        action="create",
        resource_type="document_cross_link",
        resource_id=link.id,
        new={"document_id": working_paper_id, "related_document_id": data.related_document_id},
        summary=f"linked document {paper.display_name} to {other.display_name}",
        request=request,
        commit=True,
    )
    db.refresh(link)
    return _cross_link_response(db, link, working_paper_id)


@router.get(
    "/working-papers/{working_paper_id}/related-documents",
    response_model=List[RelatedDocumentResponse],
)
def list_related_documents(
    working_paper_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Documents cross-linked to this one, either direction (any authenticated user)."""
    _get_paper_or_404(db, working_paper_id)
    links = db.scalars(
        select(DocumentCrossLink).where(
            (DocumentCrossLink.document_id == working_paper_id)
            | (DocumentCrossLink.related_document_id == working_paper_id)
        ).order_by(DocumentCrossLink.created_at)
    ).all()
    return [_cross_link_response(db, link, working_paper_id) for link in links]


@router.delete(
    "/working-papers/{working_paper_id}/related-documents/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_related_document(
    working_paper_id: int,
    link_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Remove a cross-reference (officer and above)."""
    _get_paper_or_404(db, working_paper_id)
    link = db.get(DocumentCrossLink, link_id)
    if link is None or working_paper_id not in (link.document_id, link.related_document_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document link not found")

    other_id = link.related_document_id if link.document_id == working_paper_id else link.document_id
    db.delete(link)
    db.flush()
    audit_svc.record(
        db,
        user=current_user,
        action="delete",
        resource_type="document_cross_link",
        resource_id=link_id,
        old={"document_id": link.document_id, "related_document_id": link.related_document_id},
        summary=f"unlinked working paper #{working_paper_id} from #{other_id}",
        request=request,
        commit=True,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Account comments ("explain a variance" without a document) ──────────────


def _comment_response(db: Session, c: AccountComment) -> AccountCommentResponse:
    usernames = {
        u.id: u.username
        for u in db.scalars(
            select(User).where(User.id.in_({c.created_by_user_id, c.resolved_by_user_id} - {None}))
        ).all()
    }
    return AccountCommentResponse(
        id=c.id,
        account_code=c.account_code,
        fiscal_year_id=c.fiscal_year_id,
        text=c.text,
        created_by_user_id=c.created_by_user_id,
        created_by_username=usernames.get(c.created_by_user_id),
        created_at=c.created_at,
        is_resolved=c.is_resolved,
        resolved_by_user_id=c.resolved_by_user_id,
        resolved_by_username=usernames.get(c.resolved_by_user_id) if c.resolved_by_user_id else None,
        resolved_at=c.resolved_at,
    )


@router.get(
    "/working-papers/by-account/{account_code}/comments",
    response_model=List[AccountCommentResponse],
)
def list_account_comments(
    account_code: str,
    fiscal_year_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Comments explaining this account's balance/variance (any authenticated user)."""
    comments = db.scalars(
        select(AccountComment)
        .where(AccountComment.account_code == account_code, AccountComment.fiscal_year_id == fiscal_year_id)
        .order_by(AccountComment.created_at)
    ).all()
    return [_comment_response(db, c) for c in comments]


@router.get("/working-papers/comments", response_model=List[AccountCommentResponse])
def list_all_account_comments(
    fiscal_year_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Every account comment for a fiscal year, for cheap per-row indicators on the leadsheet."""
    comments = db.scalars(
        select(AccountComment)
        .where(AccountComment.fiscal_year_id == fiscal_year_id)
        .order_by(AccountComment.created_at)
    ).all()
    return [_comment_response(db, c) for c in comments]


@router.post(
    "/working-papers/by-account/{account_code}/comments",
    response_model=AccountCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_account_comment(
    account_code: str,
    data: AccountCommentCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Add a comment explaining this account's variance (officer and above)."""
    if db.get(FiscalYear, data.fiscal_year_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fiscal year not found")
    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Comment text is required")

    comment = AccountComment(
        account_code=account_code.strip(),
        fiscal_year_id=data.fiscal_year_id,
        text=text,
        created_by_user_id=current_user.id,
    )
    db.add(comment)
    db.flush()
    audit_svc.record(
        db,
        user=current_user,
        action="create",
        resource_type="account_comment",
        resource_id=comment.id,
        new={"account_code": comment.account_code, "fiscal_year_id": comment.fiscal_year_id, "text": text},
        summary=f"commented on account {comment.account_code}",
        request=request,
        commit=True,
    )
    db.refresh(comment)
    return _comment_response(db, comment)


@router.post(
    "/working-papers/by-account/{account_code}/comments/{comment_id}/resolve",
    response_model=AccountCommentResponse,
)
def resolve_account_comment(
    account_code: str,
    comment_id: int,
    request: Request,
    resolved: bool = Query(True, description="False re-opens the comment"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    comment = db.get(AccountComment, comment_id)
    if comment is None or comment.account_code != account_code:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    comment.is_resolved = resolved
    comment.resolved_by_user_id = current_user.id if resolved else None
    comment.resolved_at = datetime.now(timezone.utc) if resolved else None

    db.flush()
    audit_svc.record(
        db,
        user=current_user,
        action="resolve_comment" if resolved else "reopen_comment",
        resource_type="account_comment",
        resource_id=comment.id,
        new={"is_resolved": resolved},
        summary=f"{'resolved' if resolved else 'reopened'} a comment on account {account_code}",
        request=request,
        commit=True,
    )
    db.refresh(comment)
    return _comment_response(db, comment)


@router.delete(
    "/working-papers/by-account/{account_code}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_account_comment(
    account_code: str,
    comment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Only the author or a finance_admin can delete a comment."""
    comment = db.get(AccountComment, comment_id)
    if comment is None or comment.account_code != account_code:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    if comment.created_by_user_id != current_user.id and current_user.role != "finance_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only the author or a finance_admin can delete a comment"
        )
    db.delete(comment)
    db.flush()
    audit_svc.record(
        db,
        user=current_user,
        action="delete",
        resource_type="account_comment",
        resource_id=comment_id,
        old={"account_code": account_code, "text": comment.text},
        summary=f"deleted a comment on account {account_code}",
        request=request,
        commit=True,
    )
    db.commit()
