from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_active_user, require_role
from app.models.report import Report
from app.models.user import User
from app.schemas.report import (
    ReportCreate,
    ReportUpdate,
    ReportResponse,
    ReportGenerateRequest,
    ReportGenerateResponse,
)
from app.services.report_engine import ReportDefinitionError, validate_definition
from app.services.report_generator import export_to_excel, export_to_pdf, generate_report_data, safe_filename

router = APIRouter()

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class DefinitionPayload(BaseModel):
    definition: Dict[str, Any]


class PreviewRequest(ReportGenerateRequest):
    definition: Dict[str, Any]


def _get_report_or_404(db: Session, report_id: int) -> Report:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return report


def _check_definition(definition: Dict[str, Any]) -> None:
    try:
        problems = validate_definition(definition)
    except ReportDefinitionError as exc:
        problems = [str(exc)]
    if problems:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=problems)


def _render(db: Session, definition: Dict[str, Any], data: ReportGenerateRequest) -> Dict[str, Any]:
    try:
        return generate_report_data(db, definition, data.fiscal_year_id, data.period_id)
    except ReportDefinitionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid report definition: {exc}")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _file_response(content: bytes, media_type: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports", response_model=List[ReportResponse])
def list_reports(
    is_template: Optional[bool] = Query(None),
    report_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    stmt = select(Report).order_by(Report.is_template.desc(), Report.name)
    if is_template is not None:
        stmt = stmt.where(Report.is_template == is_template)
    if report_type:
        stmt = stmt.where(Report.report_type == report_type)
    return db.scalars(stmt).all()


@router.post("/reports", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def create_report(
    data: ReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    _check_definition(data.definition)
    now = datetime.now(timezone.utc)
    report = Report(
        name=data.name,
        description=data.description,
        report_type=data.report_type,
        is_template=data.is_template,
        definition=data.definition,
        fiscal_year_id=data.fiscal_year_id,
        created_by_user_id=current_user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.post("/reports/validate")
def validate_report_definition(
    data: DefinitionPayload,
    current_user: User = Depends(get_current_active_user),
):
    """Validate a definition without saving it. Returns {"valid": bool, "problems": [...]}."""
    try:
        problems = validate_definition(data.definition)
    except ReportDefinitionError as exc:
        problems = [str(exc)]
    return {"valid": not problems, "problems": problems}


@router.post("/reports/preview")
def preview_report(
    data: PreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Render an unsaved definition (live preview in the report builder)."""
    return _render(db, data.definition, data)


@router.get("/reports/psab-taxonomy")
def psab_taxonomy(current_user: User = Depends(get_current_active_user)):
    """Classification values used by the built-in templates (for the PSAB mapping UI)."""
    from app.services.builtin_templates import PSAB_TAXONOMY

    return [{"value": v, "label": l, "group": v.split(".")[0]} for v, l in PSAB_TAXONOMY.items()]


@router.get("/reports/{report_id}", response_model=ReportResponse)
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return _get_report_or_404(db, report_id)


@router.put("/reports/{report_id}", response_model=ReportResponse)
def update_report(
    report_id: int,
    data: ReportUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    report = _get_report_or_404(db, report_id)
    if report.is_protected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify a protected report template; clone it to make an editable copy",
        )
    updates = data.model_dump(exclude_unset=True)
    if updates.get("definition") is not None:
        _check_definition(updates["definition"])
    for field, value in updates.items():
        setattr(report, field, value)
    report.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(report)
    return report


@router.delete("/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    report = _get_report_or_404(db, report_id)
    if report.is_protected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Built-in templates cannot be deleted")
    db.delete(report)
    db.commit()


@router.post("/reports/{report_id}/clone", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def clone_report(
    report_id: int,
    name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Create an editable copy of a report or built-in template."""
    source = _get_report_or_404(db, report_id)
    definition = dict(source.definition or {})
    if definition.get("template_key"):
        definition["source_template_key"] = definition.pop("template_key")
    now = datetime.now(timezone.utc)
    copy = Report(
        name=name or f"{source.name} (copy)",
        description=source.description,
        report_type=source.report_type,
        is_template=False,
        is_protected=False,
        definition=definition,
        fiscal_year_id=source.fiscal_year_id,
        created_by_user_id=current_user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return copy


@router.post("/reports/{report_id}/revert", response_model=ReportResponse)
def revert_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Reset a cloned template back to the current standard layout."""
    from app.services.builtin_templates import TEMPLATES

    report = _get_report_or_404(db, report_id)
    key = (report.definition or {}).get("source_template_key")
    if report.is_protected or key not in TEMPLATES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Report was not cloned from a built-in template")
    definition = dict(TEMPLATES[key]["definition"])
    definition["source_template_key"] = definition.pop("template_key")
    report.definition = definition
    report.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(report)
    return report


@router.post("/reports/{report_id}/generate", response_model=ReportGenerateResponse)
def generate_report(
    report_id: int,
    data: ReportGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Render the report for a fiscal year (and optionally a period) as JSON."""
    report = _get_report_or_404(db, report_id)
    report_data = _render(db, report.definition, data)
    return ReportGenerateResponse(
        report_id=report_id,
        title=report_data["title"],
        fiscal_year_id=data.fiscal_year_id,
        period_id=data.period_id,
        data=report_data,
        generated_at=datetime.now(timezone.utc),
    )


@router.post("/reports/{report_id}/export/pdf")
def export_report_pdf(
    report_id: int,
    data: ReportGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    report = _get_report_or_404(db, report_id)
    report_data = _render(db, report.definition, data)
    try:
        pdf_bytes = export_to_pdf(report_data)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return _file_response(pdf_bytes, "application/pdf", f"{safe_filename(report.name)}.pdf")


@router.post("/reports/{report_id}/export/excel")
def export_report_excel(
    report_id: int,
    data: ReportGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    report = _get_report_or_404(db, report_id)
    report_data = _render(db, report.definition, data)
    try:
        xlsx_bytes = export_to_excel(report_data)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return _file_response(xlsx_bytes, XLSX_MEDIA_TYPE, f"{safe_filename(report.name)}.xlsx")
