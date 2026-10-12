"""Materiality thresholds per fiscal year, and the leadsheet accounts they flag."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.export_utils import money_json
from app.core.database import get_db
from app.core.security import get_current_active_user, require_role
from app.models.materiality import Materiality
from app.models.period import FiscalYear
from app.models.user import User
from app.schemas.materiality import (
    MaterialityResponse,
    MaterialitySet,
    UnsupportedMaterialAccountsResponse,
)
from app.services import audit as audit_svc
from app.services import materiality_service as materiality_svc

router = APIRouter()

EDIT_ROLES = ("finance_admin", "finance_officer")


def _username(db: Session, user_id: int) -> Optional[str]:
    return db.scalars(select(User.username).where(User.id == user_id)).first()


def _response(db: Session, row: Materiality) -> MaterialityResponse:
    return MaterialityResponse(
        id=row.id,
        fiscal_year_id=row.fiscal_year_id,
        overall_materiality=row.overall_materiality,
        performance_materiality=row.performance_materiality,
        trivial_threshold=row.trivial_threshold,
        flagging_threshold=materiality_svc.flagging_threshold(row),
        basis=row.basis,
        rationale=row.rationale,
        set_by_user_id=row.set_by_user_id,
        set_by_username=_username(db, row.set_by_user_id),
        set_at=row.set_at,
        updated_at=row.updated_at,
    )


@router.get("/materiality/{fiscal_year_id}", response_model=MaterialityResponse)
def get_materiality(
    fiscal_year_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Current materiality for a fiscal year (any authenticated user)."""
    if db.get(FiscalYear, fiscal_year_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fiscal year not found")
    row = materiality_svc.get_materiality(db, fiscal_year_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Materiality has not been set for this fiscal year")
    return _response(db, row)


@router.put("/materiality/{fiscal_year_id}", response_model=MaterialityResponse)
def set_materiality(
    fiscal_year_id: int,
    data: MaterialitySet,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(*EDIT_ROLES)),
):
    """Set or update a fiscal year's materiality (officer and above)."""
    if db.get(FiscalYear, fiscal_year_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fiscal year not found")
    if data.performance_materiality is not None and data.performance_materiality > data.overall_materiality:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="performance_materiality cannot exceed overall_materiality",
        )
    existing = materiality_svc.get_materiality(db, fiscal_year_id)
    before = {
        "overall_materiality": str(existing.overall_materiality),
        "performance_materiality": str(existing.performance_materiality) if existing.performance_materiality is not None else None,
    } if existing else None

    row = materiality_svc.set_materiality(
        db,
        fiscal_year_id,
        overall_materiality=data.overall_materiality,
        performance_materiality=data.performance_materiality,
        trivial_threshold=data.trivial_threshold,
        basis=data.basis,
        rationale=data.rationale,
        user_id=current_user.id,
    )
    audit_svc.record(
        db,
        user=current_user,
        action="update" if existing else "create",
        resource_type="materiality",
        resource_id=row.id,
        old=before,
        new={"overall_materiality": str(row.overall_materiality),
             "performance_materiality": str(row.performance_materiality) if row.performance_materiality is not None else None},
        summary=f"set materiality for fiscal year {fiscal_year_id} to {row.overall_materiality}",
        request=request,
        commit=True,
    )
    db.refresh(row)
    return _response(db, row)


@router.get(
    "/materiality/{fiscal_year_id}/unsupported-accounts",
    response_model=UnsupportedMaterialAccountsResponse,
)
def get_unsupported_material_accounts(
    fiscal_year_id: int,
    period_id: int = Query(..., description="Flag balances through this period"),
    scheme: str = Query("PSAB", description="Mapping scheme name or id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Leadsheet accounts whose balance meets or exceeds the fiscal year's materiality
    threshold but have no supporting document linked yet. Empty (not an error) if
    materiality hasn't been set for the year.
    """
    if db.get(FiscalYear, fiscal_year_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fiscal year not found")
    try:
        result = materiality_svc.unsupported_material_accounts(db, period_id, scheme)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return money_json(result)
