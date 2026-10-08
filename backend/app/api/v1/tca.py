"""
Tangible capital asset schedule (PS 3150) — PLAN §5.2, build item 18.

The schedule is maintained by the finance team (CSV import from their asset register, or
manual entry) rather than pulled from the GL, because the AMAIS fixed-asset module is
empty at the reference installation. It is exported as a statement in the same
JSON/Excel/PDF shape as every other schedule.
"""
from decimal import Decimal
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.api.v1.export_utils import ExportFormat, tabular_response
from app.core.database import get_db
from app.core.security import get_current_active_user, require_role
from app.models.period import FiscalYear
from app.models.tca import TcaScheduleLine
from app.models.user import User
from app.schemas.tca import (
    TcaImportResponse,
    TcaLineResponse,
    TcaReplaceRequest,
    TcaReplaceResponse,
    TcaRollForwardResponse,
)
from app.services import audit as audit_svc
from app.services import tca as tca_svc

router = APIRouter()

WRITERS = ("finance_admin", "finance_officer")
TcaLayout = Literal["continuity", "summary"]

TOTAL_FIELDS = ("cost_opening", "cost_additions", "cost_disposals", "cost_closing",
                "amort_opening", "amort_expense", "amort_disposals", "amort_closing",
                "nbv_opening", "nbv_closing")


def _require_fy(db: Session, fiscal_year_id: int) -> FiscalYear:
    fy = db.get(FiscalYear, fiscal_year_id)
    if fy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fiscal year not found")
    return fy


def _require_writable(db: Session, fiscal_year_id: int) -> FiscalYear:
    """A locked year is frozen: the schedule backs a signed statement."""
    fy = _require_fy(db, fiscal_year_id)
    if fy.status == "locked":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Fiscal year {fy.label} is locked; its tangible capital asset schedule cannot be changed",
        )
    return fy


def _totals(lines: List[TcaScheduleLine]) -> dict:
    return {
        field: str(sum((Decimal(str(getattr(line, field))) for line in lines), Decimal("0")))
        for field in TOTAL_FIELDS
    }


@router.get("/tca/lines", response_model=List[TcaLineResponse])
def list_tca_lines(
    fiscal_year_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    _require_fy(db, fiscal_year_id)
    return tca_svc.list_lines(db, fiscal_year_id)


@router.put("/tca/lines", response_model=TcaReplaceResponse)
def replace_tca_lines(
    data: TcaReplaceRequest,
    request: Request,
    fiscal_year_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*WRITERS)),
):
    """Replace the year's schedule with the posted rows (one per asset class)."""
    fy = _require_writable(db, fiscal_year_id)
    seen = {}
    for line in data.lines:
        key = line.asset_class.strip().lower()
        if key in seen:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Duplicate asset class: {line.asset_class}",
            )
        seen[key] = line
    rows = [{**line.model_dump(), "asset_class": line.asset_class.strip()} for line in data.lines]
    count = tca_svc.replace_lines(db, fiscal_year_id, rows, source="manual")
    lines = tca_svc.list_lines(db, fiscal_year_id)
    totals = _totals(lines)
    audit_svc.record(
        db, user=current_user, action="update", resource_type="tca_schedule", resource_id=fiscal_year_id,
        new={"lines": count, "cost_closing": totals["cost_closing"],
             "nbv_closing": totals["nbv_closing"]},
        summary=f"updated the tangible capital asset schedule for {fy.label} ({count} asset classes)",
        request=request, commit=True,
    )
    return TcaReplaceResponse(lines_saved=count, totals=totals)


@router.post("/tca/lines/import", response_model=TcaImportResponse)
async def import_tca_lines(
    request: Request,
    fiscal_year_id: int = Query(...),
    replace: bool = Query(True, description="Replace the schedule, or merge into it"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*WRITERS)),
):
    """Import a continuity schedule from CSV (the municipality's asset register export)."""
    fy = _require_writable(db, fiscal_year_id)
    imported, errors = tca_svc.import_csv(db, fiscal_year_id, await file.read(), replace=replace)
    if imported:
        audit_svc.record(
            db, user=current_user, action="import", resource_type="tca_schedule", resource_id=fiscal_year_id,
            new={"imported": imported, "replace": replace, "errors": len(errors)},
            summary=f"imported the tangible capital asset schedule for {fy.label} from CSV ({imported} rows)",
            request=request, commit=True,
        )
    else:
        db.commit()
    return TcaImportResponse(records_imported=imported, errors=errors)


@router.post("/tca/lines/roll-forward", response_model=TcaRollForwardResponse)
def roll_forward_tca_openings(
    request: Request,
    fiscal_year_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*WRITERS)),
):
    """Set opening cost and accumulated amortization from the prior year's closing balances."""
    fy = _require_writable(db, fiscal_year_id)
    result = tca_svc.apply_prior_year_openings(db, fy)
    if result["applied"]:
        audit_svc.record(
            db, user=current_user, action="roll_forward", resource_type="tca_schedule", resource_id=fiscal_year_id,
            new=result,
            summary=f"carried {result['prior_year']} tangible capital asset balances into {fy.label}",
            request=request, commit=True,
        )
    else:
        db.commit()
    return TcaRollForwardResponse(**result)


@router.get("/tca/schedule")
def get_tca_schedule(
    fiscal_year_id: int = Query(...),
    layout: TcaLayout = Query("continuity", description="Full continuity, or closing figures only"),
    format: ExportFormat = Query("json"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """PS 3150 schedule, with a reconciliation against the GL's TCA accounts."""
    fy = _require_fy(db, fiscal_year_id)
    report = tca_svc.build_schedule(db, fiscal_year_id, layout)
    return tabular_response(report, format, f"TCA_Schedule_{fy.label}")
