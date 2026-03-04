from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Response, status
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
from app.services.report_generator import ReportDefinition, generate_report_data, export_to_excel, export_to_pdf

router = APIRouter()


@router.get("/reports", response_model=List[ReportResponse])
def list_reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return db.scalars(select(Report).order_by(Report.name)).all()


@router.post("/reports", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def create_report(
    data: ReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
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


@router.get("/reports/{report_id}", response_model=ReportResponse)
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return report


@router.put("/reports/{report_id}", response_model=ReportResponse)
def update_report(
    report_id: int,
    data: ReportUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    if report.is_protected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot modify a protected report template")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(report, field, value)
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
    """Generate report data as JSON. The report definition must be a valid ReportDefinition."""
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    try:
        report_def = ReportDefinition.model_validate(report.definition)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid report definition: {exc}",
        )

    report_data = generate_report_data(
        db=db,
        report_def=report_def,
        fiscal_year_id=data.fiscal_year_id,
        period_id=data.period_id,
    )

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
    """Export report as PDF. Returns binary PDF."""
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    try:
        report_def = ReportDefinition.model_validate(report.definition)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid report definition: {exc}")

    report_data = generate_report_data(
        db=db,
        report_def=report_def,
        fiscal_year_id=data.fiscal_year_id,
        period_id=data.period_id,
    )

    try:
        pdf_bytes = export_to_pdf(report_data)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    safe_name = report.name.replace(" ", "_")[:50]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.pdf"'},
    )


@router.post("/reports/{report_id}/export/excel")
def export_report_excel(
    report_id: int,
    data: ReportGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Export report as Excel (.xlsx). Returns binary xlsx."""
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    try:
        report_def = ReportDefinition.model_validate(report.definition)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid report definition: {exc}")

    report_data = generate_report_data(
        db=db,
        report_def=report_def,
        fiscal_year_id=data.fiscal_year_id,
        period_id=data.period_id,
    )

    try:
        xlsx_bytes = export_to_excel(report_data)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    safe_name = report.name.replace(" ", "_")[:50]
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.xlsx"'},
    )
