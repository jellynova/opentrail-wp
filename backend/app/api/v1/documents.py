"""
Working paper documents (PLAN §7).

Covers the audit-binder folder structure, versioning, review annotations and the
two-level sign-off workflow (preparer → reviewer), including re-approval when a
signed-off document is modified.
"""
import mimetypes
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_active_user, require_role
from app.models.document import WorkingPaper, WPAnnotation
from app.models.period import FiscalYear
from app.models.user import User
from app.schemas.document import (
    AnnotationCreate,
    AnnotationResponse,
    FolderNode,
    SignOffRequest,
    SignOffResponse,
    WorkingPaperResponse,
    WorkingPaperUpdate,
)
from app.services import audit as audit_svc
from app.services import document_manager as doc_mgr

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".docx", ".doc", ".png", ".jpg", ".jpeg", ".gif", ".csv"}

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB

EDIT_ROLES = ("finance_admin", "finance_officer")


def _file_type_from_ext(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    mapping = {
        ".pdf": "pdf",
        ".xlsx": "xlsx",
        ".xls": "xlsx",
        ".docx": "docx",
        ".doc": "docx",
        ".png": "img",
        ".jpg": "img",
        ".jpeg": "img",
        ".gif": "img",
    }
    return mapping.get(ext, "other")


def _usernames(db: Session, ids) -> Dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: u.username for u in db.scalars(select(User).where(User.id.in_(ids))).all()}


def _versions(db: Session, row: WorkingPaper) -> List[WorkingPaper]:
    return doc_mgr.document_versions(db, row.id)


def _detail(
    db: Session,
    row: WorkingPaper,
    *,
    versions: Optional[List[WorkingPaper]] = None,
    usernames: Optional[Dict[int, str]] = None,
) -> WorkingPaperResponse:
    versions = versions if versions is not None else _versions(db, row)
    if usernames is None:
        usernames = _usernames(
            db,
            {row.uploaded_by_user_id, row.preparer_signed_off_by_user_id, row.reviewer_signed_off_by_user_id},
        )
    state = doc_mgr.sign_off_status(versions, row)
    return WorkingPaperResponse(
        id=row.id,
        root_id=row.root_id,
        fiscal_year_id=row.fiscal_year_id,
        folder_path=row.folder_path,
        filename=row.filename,
        display_name=row.display_name,
        file_type=row.file_type,
        file_size=row.file_size,
        uploaded_by_user_id=row.uploaded_by_user_id,
        uploaded_by_username=usernames.get(row.uploaded_by_user_id),
        uploaded_at=row.uploaded_at,
        description=row.description,
        version_number=row.version_number,
        version_count=state["version_count"],
        parent_version_id=row.parent_version_id,
        superseded_at=row.superseded_at,
        sign_off_state=state["sign_off_state"],
        requires_reapproval=state["requires_reapproval"],
        preparer_signed_off_by_user_id=row.preparer_signed_off_by_user_id,
        preparer_signed_off_by_username=usernames.get(row.preparer_signed_off_by_user_id),
        preparer_signed_off_at=row.preparer_signed_off_at,
        reviewer_signed_off_by_user_id=row.reviewer_signed_off_by_user_id,
        reviewer_signed_off_by_username=usernames.get(row.reviewer_signed_off_by_user_id),
        reviewer_signed_off_at=row.reviewer_signed_off_at,
    )


def _get_document_or_404(db: Session, document_id: int) -> WorkingPaper:
    row = db.get(WorkingPaper, document_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return row


def _latest_version(db: Session, row: WorkingPaper) -> WorkingPaper:
    versions = _versions(db, row)
    return versions[-1] if versions else row


def _clean_folder(folder_path: Optional[str]) -> str:
    try:
        return doc_mgr.clean_folder_path(folder_path)
    except doc_mgr.InvalidFolderPath as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _validate_upload(file: UploadFile, content: bytes) -> str:
    original_filename = file.filename or "upload"
    ext = os.path.splitext(original_filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{ext}' not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 50 MB limit",
        )
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty")
    return original_filename


def _stored_filename(original_filename: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = os.path.splitext(os.path.basename(original_filename))[0]
    safe_base = "".join(c if c.isalnum() or c in "-_." else "_" for c in base)[:80] or "file"
    ext = os.path.splitext(original_filename)[1].lower()
    return f"{timestamp}_{safe_base}{ext}"


def _annotation_response(db: Session, annotation: WPAnnotation, usernames: Optional[Dict[int, str]] = None) -> AnnotationResponse:
    usernames = usernames if usernames is not None else _usernames(db, {annotation.user_id, annotation.resolved_by_user_id})
    return AnnotationResponse(
        id=annotation.id,
        working_paper_id=annotation.working_paper_id,
        user_id=annotation.user_id,
        username=usernames.get(annotation.user_id),
        text=annotation.text,
        created_at=annotation.created_at,
        is_resolved=annotation.is_resolved,
        resolved_by_user_id=annotation.resolved_by_user_id,
        resolved_by_username=usernames.get(annotation.resolved_by_user_id),
        resolved_at=annotation.resolved_at,
    )


# --------------------------------------------------------------------------------------
# Folders and listings
# --------------------------------------------------------------------------------------


@router.get("/documents/folders", response_model=List[FolderNode])
def list_folders(
    fiscal_year_id: Optional[int] = Query(None, description="Count only documents for this fiscal year"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    The binder folder tree (PLAN §7.1). ``/current`` gets one sub-folder per fiscal year on
    file, so the tree follows the municipality's years rather than a hard-coded list.
    """
    stmt = select(WorkingPaper)
    if fiscal_year_id is not None:
        stmt = stmt.where(WorkingPaper.fiscal_year_id == fiscal_year_id)
    rows = db.scalars(stmt).all()

    counts: Dict[str, Dict[str, int]] = {}
    for row in rows:
        if row.superseded_at is not None:
            continue
        bucket = counts.setdefault(row.folder_path, {"documents": 0, "unsigned": 0})
        bucket["documents"] += 1
        if row.reviewer_signed_off_at is None:
            bucket["unsigned"] += 1

    return [FolderNode(**node) for node in doc_mgr.folder_tree(db, counts)]


@router.get("/documents", response_model=List[WorkingPaperResponse])
def list_documents(
    fiscal_year_id: Optional[int] = Query(None),
    folder_path: Optional[str] = Query(None),
    include_versions: bool = Query(False, description="Return every version, not just the latest"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Working papers, newest first. By default one row per document (its latest version)."""
    clean_folder = _clean_folder(folder_path) if folder_path is not None else None
    rows = doc_mgr.latest_versions(
        db,
        fiscal_year_id=fiscal_year_id,
        folder_path=clean_folder,
        include_versions=include_versions,
    )

    usernames = _usernames(
        db,
        {
            i
            for r in rows
            for i in (r.uploaded_by_user_id, r.preparer_signed_off_by_user_id, r.reviewer_signed_off_by_user_id)
        },
    )
    return [_detail(db, r, usernames=usernames) for r in rows]


@router.get("/documents/{document_id}", response_model=WorkingPaperResponse)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    row = _get_document_or_404(db, document_id)
    return _detail(db, _latest_version(db, row))


@router.get("/documents/{document_id}/versions", response_model=List[WorkingPaperResponse])
def get_document_versions(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Version history, oldest first. Superseded versions keep their own sign-off record."""
    row = _get_document_or_404(db, document_id)
    versions = _versions(db, row)
    usernames = _usernames(
        db,
        {
            i
            for v in versions
            for i in (v.uploaded_by_user_id, v.preparer_signed_off_by_user_id, v.reviewer_signed_off_by_user_id)
        },
    )
    # Each version is reported against itself, so its own sign-off state is visible.
    return [_detail(db, v, versions=[v], usernames=usernames) for v in versions]


# --------------------------------------------------------------------------------------
# Upload, new versions, metadata, delete
# --------------------------------------------------------------------------------------


@router.post("/documents/upload", response_model=WorkingPaperResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    fiscal_year_id: int = Form(...),
    folder_path: str = Form("/permanent"),
    display_name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*EDIT_ROLES)),
):
    """Upload a new working paper file into a binder folder."""
    if db.get(FiscalYear, fiscal_year_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fiscal year not found")
    folder = _clean_folder(folder_path)

    content = await file.read()
    original_filename = _validate_upload(file, content)
    stored_filename = _stored_filename(original_filename)
    relative_path = doc_mgr.save_file(content, folder, stored_filename)

    wp = WorkingPaper(
        fiscal_year_id=fiscal_year_id,
        folder_path=folder,
        filename=os.path.basename(relative_path),
        display_name=display_name or original_filename,
        file_type=_file_type_from_ext(original_filename),
        file_size=len(content),
        uploaded_by_user_id=current_user.id,
        uploaded_at=datetime.now(timezone.utc),
        description=description,
        version_number=1,
    )
    db.add(wp)
    db.flush()

    audit_svc.record(
        db,
        user=current_user,
        action="upload",
        resource_type="document",
        resource_id=wp.id,
        new={"display_name": wp.display_name, "folder_path": wp.folder_path, "size": wp.file_size},
        summary=f"uploaded {wp.display_name} to {wp.folder_path}",
        request=request,
        commit=True,
    )
    db.refresh(wp)
    return _detail(db, wp)


@router.post(
    "/documents/{document_id}/versions",
    response_model=WorkingPaperResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_new_version(
    document_id: int,
    request: Request,
    display_name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    folder_path: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*EDIT_ROLES)),
):
    """
    Upload a replacement version of an existing document.

    The previous version is kept (and marked superseded) so the audit trail survives; the
    document's sign-off is void until the new version is reviewed again (PLAN §7.2).
    """
    row = _get_document_or_404(db, document_id)
    root = db.get(WorkingPaper, row.root_id) or row
    latest = _latest_version(db, root)

    content = await file.read()
    original_filename = _validate_upload(file, content)
    stored_filename = _stored_filename(original_filename)
    folder = _clean_folder(folder_path) if folder_path else root.folder_path
    relative_path = doc_mgr.save_file(content, folder, stored_filename)

    previous_state = doc_mgr.sign_off_status(_versions(db, root), latest)

    latest.superseded_at = datetime.now(timezone.utc)

    new_version = WorkingPaper(
        fiscal_year_id=root.fiscal_year_id,
        folder_path=folder,
        filename=os.path.basename(relative_path),
        display_name=display_name or latest.display_name,
        file_type=_file_type_from_ext(original_filename),
        file_size=len(content),
        uploaded_by_user_id=current_user.id,
        uploaded_at=datetime.now(timezone.utc),
        description=description if description is not None else latest.description,
        version_number=latest.version_number + 1,
        parent_version_id=root.id,
        # A replacement of a signed-off paper needs the reviewer's eyes again.
        requires_reapproval=previous_state["sign_off_state"] != "draft",
    )
    db.add(new_version)
    db.flush()

    audit_svc.record(
        db,
        user=current_user,
        action="new_version",
        resource_type="document",
        resource_id=new_version.id,
        old={"version_number": latest.version_number, "sign_off_state": previous_state["sign_off_state"]},
        new={
            "version_number": new_version.version_number,
            "display_name": new_version.display_name,
            "requires_reapproval": new_version.requires_reapproval,
        },
        summary=f"uploaded version {new_version.version_number} of {new_version.display_name}",
        request=request,
        commit=True,
    )
    db.refresh(new_version)
    return _detail(db, new_version)


@router.put("/documents/{document_id}", response_model=WorkingPaperResponse)
def update_document(
    document_id: int,
    data: WorkingPaperUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*EDIT_ROLES)),
):
    """
    Edit a document's metadata (name, description, folder).

    Editing a signed-off document voids its sign-off and flags it for re-approval.
    """
    row = _get_document_or_404(db, document_id)
    latest = _latest_version(db, row)
    before = audit_svc.snapshot(latest, ["display_name", "description", "folder_path"])

    if data.display_name is not None:
        latest.display_name = data.display_name
    if data.description is not None:
        latest.description = data.description
    if data.folder_path is not None:
        latest.folder_path = _clean_folder(data.folder_path)

    signed = latest.preparer_signed_off_at is not None or latest.reviewer_signed_off_at is not None
    if signed:
        latest.preparer_signed_off_by_user_id = None
        latest.preparer_signed_off_at = None
        latest.reviewer_signed_off_by_user_id = None
        latest.reviewer_signed_off_at = None
        latest.requires_reapproval = True

    db.flush()
    audit_svc.record(
        db,
        user=current_user,
        action="update",
        resource_type="document",
        resource_id=latest.id,
        old=before,
        new=audit_svc.snapshot(latest, ["display_name", "description", "folder_path", "requires_reapproval"]),
        summary=f"edited {latest.display_name}" + (" (sign-off reset)" if signed else ""),
        request=request,
        commit=True,
    )
    db.refresh(latest)
    return _detail(db, latest)


@router.get("/documents/{document_id}/download")
def download_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Download a specific version's file content."""
    wp = _get_document_or_404(db, document_id)
    try:
        content = doc_mgr.get_file_bytes(wp)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk. It may have been moved or deleted.",
        )

    media_type, _ = mimetypes.guess_type(wp.filename)
    media_type = media_type or "application/octet-stream"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{wp.display_name}"'},
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*EDIT_ROLES)),
):
    """Delete a document and all of its versions."""
    row = _get_document_or_404(db, document_id)
    versions = _versions(db, row)
    latest = versions[-1] if versions else row

    if latest.reviewer_signed_off_at is not None and current_user.role != "finance_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A reviewed and approved working paper can only be deleted by a finance_admin",
        )

    names = [v.display_name for v in versions]
    for version in versions:
        doc_mgr.delete_file(doc_mgr.get_file_path(version))
        db.delete(version)

    audit_svc.record(
        db,
        user=current_user,
        action="delete",
        resource_type="document",
        resource_id=latest.id,
        old={"display_name": latest.display_name, "folder_path": latest.folder_path, "versions": names},
        summary=f"deleted {latest.display_name}",
        request=request,
        commit=True,
    )


# --------------------------------------------------------------------------------------
# Sign-off workflow (PLAN §7.2)
# --------------------------------------------------------------------------------------


def _signoff_response(db: Session, row: WorkingPaper, message: str) -> SignOffResponse:
    state = doc_mgr.sign_off_status(_versions(db, row), row)
    return SignOffResponse(
        message=message,
        document_id=row.id,
        sign_off_state=state["sign_off_state"],
        requires_reapproval=state["requires_reapproval"],
    )


def _require_latest(db: Session, row: WorkingPaper) -> WorkingPaper:
    latest = _latest_version(db, row)
    if latest.id != row.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Version {row.version_number} has been superseded; sign off version {latest.version_number} instead",
        )
    return latest


@router.post("/documents/{document_id}/sign-off/preparer", response_model=SignOffResponse)
def preparer_sign_off(
    document_id: int,
    request: Request,
    data: Optional[SignOffRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*EDIT_ROLES)),
):
    """Level 1: the finance officer marks the working paper complete."""
    row = _require_latest(db, _get_document_or_404(db, document_id))
    now = datetime.now(timezone.utc)
    previous_reviewer = row.reviewer_signed_off_by_user_id

    row.preparer_signed_off_by_user_id = current_user.id
    row.preparer_signed_off_at = now
    if previous_reviewer is not None:
        # Preparing again after review invalidates the review.
        row.reviewer_signed_off_by_user_id = None
        row.reviewer_signed_off_at = None
        row.requires_reapproval = True
    else:
        row.requires_reapproval = False

    if data is not None and data.note:
        db.add(
            WPAnnotation(
                working_paper_id=row.id,
                user_id=current_user.id,
                text=f"Preparer note: {data.note}",
                created_at=now,
            )
        )

    db.flush()
    audit_svc.record(
        db,
        user=current_user,
        action="sign_off",
        resource_type="document",
        resource_id=row.id,
        new={"level": "preparer", "display_name": row.display_name, "reviewer_cleared": previous_reviewer is not None},
        summary=f"marked {row.display_name} prepared",
        request=request,
        commit=True,
    )
    db.refresh(row)
    return _signoff_response(db, row, "Preparer sign-off recorded")


@router.post("/documents/{document_id}/sign-off/reviewer", response_model=SignOffResponse)
def reviewer_sign_off(
    document_id: int,
    request: Request,
    data: Optional[SignOffRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin")),
):
    """
    Level 2: the finance director reviews and approves the working paper.

    The preparer must have signed off first, and the reviewer cannot be the preparer
    (segregation of duties — the same rule the budget module applies to request reviews).
    """
    row = _require_latest(db, _get_document_or_404(db, document_id))
    if row.preparer_signed_off_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The working paper must be signed off by its preparer before it can be reviewed",
        )
    if row.preparer_signed_off_by_user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A working paper cannot be reviewed by the person who prepared it",
        )

    now = datetime.now(timezone.utc)
    row.reviewer_signed_off_by_user_id = current_user.id
    row.reviewer_signed_off_at = now
    row.requires_reapproval = False

    if data is not None and data.note:
        db.add(
            WPAnnotation(
                working_paper_id=row.id,
                user_id=current_user.id,
                text=f"Reviewer note: {data.note}",
                created_at=now,
            )
        )

    db.flush()
    audit_svc.record(
        db,
        user=current_user,
        action="sign_off",
        resource_type="document",
        resource_id=row.id,
        new={"level": "reviewer", "display_name": row.display_name},
        summary=f"approved working paper {row.display_name}",
        request=request,
        commit=True,
    )
    db.refresh(row)
    return _signoff_response(db, row, "Reviewer sign-off recorded")


@router.post("/documents/{document_id}/sign-off/reset", response_model=SignOffResponse)
def reset_sign_off(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin")),
):
    """Withdraw both sign-offs (e.g. the paper needs rework after approval)."""
    row = _require_latest(db, _get_document_or_404(db, document_id))
    before = audit_svc.snapshot(row, ["preparer_signed_off_by_user_id", "reviewer_signed_off_by_user_id"])

    row.preparer_signed_off_by_user_id = None
    row.preparer_signed_off_at = None
    row.reviewer_signed_off_by_user_id = None
    row.reviewer_signed_off_at = None
    row.requires_reapproval = True

    db.flush()
    audit_svc.record(
        db,
        user=current_user,
        action="sign_off_reset",
        resource_type="document",
        resource_id=row.id,
        old=before,
        new={"requires_reapproval": True},
        summary=f"withdrew sign-off on {row.display_name}",
        request=request,
        commit=True,
    )
    db.refresh(row)
    return _signoff_response(db, row, "Sign-off withdrawn; the working paper needs re-approval")


# --------------------------------------------------------------------------------------
# Annotations
# --------------------------------------------------------------------------------------


@router.get("/documents/{document_id}/annotations", response_model=List[AnnotationResponse])
def list_annotations(
    document_id: int,
    include_resolved: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    row = _get_document_or_404(db, document_id)
    stmt = select(WPAnnotation).where(WPAnnotation.working_paper_id == row.id).order_by(WPAnnotation.created_at)
    if not include_resolved:
        stmt = stmt.where(WPAnnotation.is_resolved.is_(False))
    annotations = db.scalars(stmt).all()
    usernames = _usernames(db, {a.user_id for a in annotations} | {a.resolved_by_user_id for a in annotations})
    return [_annotation_response(db, a, usernames) for a in annotations]


@router.post(
    "/documents/{document_id}/annotations", response_model=AnnotationResponse, status_code=status.HTTP_201_CREATED
)
def add_annotation(
    document_id: int,
    data: AnnotationCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    row = _get_document_or_404(db, document_id)
    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Annotation text is required")

    annotation = WPAnnotation(
        working_paper_id=row.id,
        user_id=current_user.id,
        text=text,
        created_at=datetime.now(timezone.utc),
        is_resolved=False,
    )
    db.add(annotation)
    db.flush()
    audit_svc.record(
        db,
        user=current_user,
        action="comment",
        resource_type="document",
        resource_id=row.id,
        new={"annotation_id": annotation.id, "text": text},
        summary=f"commented on {row.display_name}",
        request=request,
        commit=True,
    )
    db.refresh(annotation)
    return _annotation_response(db, annotation)


@router.post("/documents/{document_id}/annotations/{annotation_id}/resolve", response_model=AnnotationResponse)
def resolve_annotation(
    document_id: int,
    annotation_id: int,
    request: Request,
    resolved: bool = Query(True, description="False re-opens the annotation"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    row = _get_document_or_404(db, document_id)
    annotation = db.get(WPAnnotation, annotation_id)
    if annotation is None or annotation.working_paper_id != row.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")

    annotation.is_resolved = resolved
    annotation.resolved_by_user_id = current_user.id if resolved else None
    annotation.resolved_at = datetime.now(timezone.utc) if resolved else None

    db.flush()
    audit_svc.record(
        db,
        user=current_user,
        action="resolve_comment" if resolved else "reopen_comment",
        resource_type="document",
        resource_id=row.id,
        new={"annotation_id": annotation.id, "is_resolved": resolved},
        summary=f"{'resolved' if resolved else 'reopened'} a comment on {row.display_name}",
        request=request,
        commit=True,
    )
    db.refresh(annotation)
    return _annotation_response(db, annotation)


@router.delete("/documents/{document_id}/annotations/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_annotation(
    document_id: int,
    annotation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    row = _get_document_or_404(db, document_id)
    annotation = db.get(WPAnnotation, annotation_id)
    if annotation is None or annotation.working_paper_id != row.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")
    if annotation.user_id != current_user.id and current_user.role != "finance_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only the author or a finance_admin can delete a comment"
        )
    db.delete(annotation)
    db.commit()
