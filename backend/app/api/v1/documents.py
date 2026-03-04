import os
import mimetypes
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_active_user, require_role
from app.models.document import WorkingPaper, WPAnnotation
from app.models.user import User
from app.schemas.document import (
    WorkingPaperResponse,
    AnnotationCreate,
    AnnotationResponse,
    SignOffResponse,
)
from app.services import document_manager as doc_mgr

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".docx", ".doc", ".png", ".jpg", ".jpeg", ".gif", ".csv"}

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


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


@router.get("/documents", response_model=List[WorkingPaperResponse])
def list_documents(
    fiscal_year_id: Optional[int] = Query(None),
    folder_path: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    stmt = select(WorkingPaper).order_by(WorkingPaper.uploaded_at.desc())
    if fiscal_year_id is not None:
        stmt = stmt.where(WorkingPaper.fiscal_year_id == fiscal_year_id)
    if folder_path is not None:
        stmt = stmt.where(WorkingPaper.folder_path == folder_path)
    return db.scalars(stmt).all()


@router.post("/documents/upload", response_model=WorkingPaperResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    fiscal_year_id: int = Form(...),
    folder_path: str = Form("/"),
    display_name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Upload a working paper file."""
    original_filename = file.filename or "upload"
    ext = os.path.splitext(original_filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{ext}' not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 50 MB limit",
        )

    # Generate a unique filename to prevent collisions
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_base = "".join(c if c.isalnum() or c in "-_." else "_" for c in os.path.splitext(original_filename)[0])
    stored_filename = f"{timestamp}_{safe_base}{ext}"

    relative_path = doc_mgr.save_file(content, folder_path, stored_filename)

    wp = WorkingPaper(
        fiscal_year_id=fiscal_year_id,
        folder_path=folder_path.rstrip("/") or "/",
        filename=stored_filename,
        display_name=display_name or original_filename,
        file_type=_file_type_from_ext(original_filename),
        file_size=len(content),
        uploaded_by_user_id=current_user.id,
        uploaded_at=datetime.now(timezone.utc),
        description=description,
        version_number=1,
    )
    db.add(wp)
    db.commit()
    db.refresh(wp)
    return wp


@router.get("/documents/{document_id}", response_model=WorkingPaperResponse)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    wp = db.get(WorkingPaper, document_id)
    if wp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return wp


@router.get("/documents/{document_id}/download")
def download_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Download the file content for a working paper."""
    wp = db.get(WorkingPaper, document_id)
    if wp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    wp = db.get(WorkingPaper, document_id)
    if wp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Delete the file from disk
    file_path = doc_mgr.get_file_path(wp)
    doc_mgr.delete_file(file_path)

    db.delete(wp)
    db.commit()


@router.post("/documents/{document_id}/sign-off/preparer", response_model=SignOffResponse)
def preparer_sign_off(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Record preparer sign-off as an annotation."""
    wp = db.get(WorkingPaper, document_id)
    if wp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    annotation = WPAnnotation(
        working_paper_id=document_id,
        user_id=current_user.id,
        text=f"[PREPARER SIGN-OFF] {current_user.username} — {datetime.now(timezone.utc).isoformat()}",
        created_at=datetime.now(timezone.utc),
        is_resolved=True,
    )
    db.add(annotation)
    db.commit()

    return SignOffResponse(message="Preparer sign-off recorded", document_id=document_id)


@router.post("/documents/{document_id}/sign-off/reviewer", response_model=SignOffResponse)
def reviewer_sign_off(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Record reviewer sign-off as an annotation."""
    wp = db.get(WorkingPaper, document_id)
    if wp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    annotation = WPAnnotation(
        working_paper_id=document_id,
        user_id=current_user.id,
        text=f"[REVIEWER SIGN-OFF] {current_user.username} — {datetime.now(timezone.utc).isoformat()}",
        created_at=datetime.now(timezone.utc),
        is_resolved=True,
    )
    db.add(annotation)
    db.commit()

    return SignOffResponse(message="Reviewer sign-off recorded", document_id=document_id)


@router.post("/documents/{document_id}/annotations", response_model=AnnotationResponse, status_code=status.HTTP_201_CREATED)
def add_annotation(
    document_id: int,
    data: AnnotationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    wp = db.get(WorkingPaper, document_id)
    if wp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    annotation = WPAnnotation(
        working_paper_id=document_id,
        user_id=current_user.id,
        text=data.text,
        created_at=datetime.now(timezone.utc),
        is_resolved=False,
    )
    db.add(annotation)
    db.commit()
    db.refresh(annotation)
    return annotation


@router.get("/documents/{document_id}/annotations", response_model=List[AnnotationResponse])
def get_annotations(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    wp = db.get(WorkingPaper, document_id)
    if wp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    return db.scalars(
        select(WPAnnotation)
        .where(WPAnnotation.working_paper_id == document_id)
        .order_by(WPAnnotation.created_at)
    ).all()
