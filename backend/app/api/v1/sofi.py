from decimal import Decimal
from typing import List, Literal, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.export_utils import ExportFormat, tabular_response
from app.api.v1.imports import column_map_or_422 as _column_map_or_422
from app.api.v1.imports import mapping_error_422 as _mapping_error_422
from app.core.database import get_db
from app.core.security import get_current_active_user, require_role
from app.models.period import FiscalYear
from app.models.sofi import SofiEntry
from app.models.user import User
from app.services import import_parsers
from app.services import sofi as sofi_svc

router = APIRouter()

ScheduleType = Literal["supplier_payment", "employee_remuneration", "guarantee_indemnity"]


class SofiEntryCreate(BaseModel):
    fiscal_year_id: int
    schedule_type: ScheduleType
    name: str
    position: Optional[str] = None
    is_elected_official: bool = False
    amount: Decimal = Decimal("0")
    expenses: Decimal = Decimal("0")
    description: Optional[str] = None


class SofiEntryResponse(SofiEntryCreate):
    id: int
    source: str

    model_config = {"from_attributes": True}


def _require_fy(db: Session, fiscal_year_id: int) -> FiscalYear:
    fy = db.get(FiscalYear, fiscal_year_id)
    if fy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fiscal year not found")
    return fy


@router.get("/sofi/entries", response_model=List[SofiEntryResponse])
def list_entries(
    fiscal_year_id: int = Query(...),
    schedule_type: Optional[ScheduleType] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    stmt = select(SofiEntry).where(SofiEntry.fiscal_year_id == fiscal_year_id).order_by(SofiEntry.name)
    if schedule_type:
        stmt = stmt.where(SofiEntry.schedule_type == schedule_type)
    return db.scalars(stmt).all()


@router.post("/sofi/entries", response_model=SofiEntryResponse, status_code=status.HTTP_201_CREATED)
def create_entry(
    data: SofiEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    _require_fy(db, data.fiscal_year_id)
    entry = SofiEntry(**data.model_dump(), source="manual")
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/sofi/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    entry = db.get(SofiEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    db.delete(entry)
    db.commit()


@router.post("/sofi/entries/import")
async def import_entries(
    fiscal_year_id: int = Query(...),
    schedule_type: ScheduleType = Query(...),
    replace: bool = Query(True, description="Replace existing entries of this type for the year"),
    sheet: Optional[str] = Query(None, description="Excel sheet name (default: first non-empty sheet)"),
    header_row: Optional[int] = Query(None, ge=0, description="Explicit header row (0-based index into the non-empty rows); auto-detected when omitted"),
    column_map: Optional[str] = Form(None, description='Explicit column mapping as JSON, e.g. {"name": 0, "amount": 2}; column refs may be 0-based indexes or Excel letters'),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """
    Import from CSV, Excel or a QuickBooks/Sage export (AP payment history, T4 summary, …).

    With a ``column_map`` the upload is read exactly as mapped (no header
    auto-detection): canonical fields are name (required) plus amount, expenses,
    position, description and is_elected_official.
    """
    _require_fy(db, fiscal_year_id)
    content = await file.read()
    mapping = _column_map_or_422(column_map)
    is_xlsx = import_parsers.sniff_format(file.filename or "", content) == "xlsx"
    if mapping is not None:
        try:
            rows, errors = sofi_svc.parse_csv(
                content, sheet=sheet if is_xlsx else None, header_row=header_row, column_map=mapping)
        except import_parsers.ImportMappingError as exc:
            raise _mapping_error_422(exc)
        imported = sofi_svc.save_entries(db, fiscal_year_id, schedule_type, rows, replace=replace)
    else:
        imported, errors = sofi_svc.import_entries(
            db, fiscal_year_id, schedule_type, content, replace, sheet=sheet if is_xlsx else None)
    return {"records_imported": imported, "errors": errors}


@router.get("/sofi/schedules/{schedule_type}")
def get_schedule(
    schedule_type: ScheduleType,
    fiscal_year_id: int = Query(...),
    threshold: Optional[Decimal] = Query(None, description="Override the disclosure threshold"),
    format: ExportFormat = Query("json"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    fy = _require_fy(db, fiscal_year_id)
    report = sofi_svc.build_schedule(db, fiscal_year_id, schedule_type, threshold)
    return tabular_response(report, format, f"SOFI_{schedule_type}_{fy.label}")
