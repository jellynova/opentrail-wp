from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, and_, delete
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_active_user, require_role
from app.models.account import Account, AccountMapping
from app.models.mapping import AccountClassification, MappingScheme
from app.models.segment import SegmentDefinition
from app.models.user import User
from app.schemas.account import (
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    MappingSchemeCreate,
    MappingSchemeUpdate,
    MappingSchemeResponse,
    AccountClassificationUpdate,
    AccountClassificationResponse,
    SegmentDefinitionUpdate,
    SegmentDefinitionResponse,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

@router.get("/accounts", response_model=List[AccountResponse])
def list_accounts(
    fiscal_year_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    stmt = select(Account).order_by(Account.acct_fmtd)
    if fiscal_year_id is not None:
        stmt = stmt.where(Account.fiscal_year_id == fiscal_year_id)
    if is_active is not None:
        stmt = stmt.where(Account.is_active == is_active)
    return db.scalars(stmt).all()


@router.post("/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(
    data: AccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    account = Account(**data.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.get("/accounts/{account_id}", response_model=AccountResponse)
def get_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


@router.put("/accounts/{account_id}", response_model=AccountResponse)
def update_account(
    account_id: int,
    data: AccountUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(account, field, value)

    db.commit()
    db.refresh(account)
    return account


# ---------------------------------------------------------------------------
# Mapping Schemes
# ---------------------------------------------------------------------------

@router.get("/mapping-schemes", response_model=List[MappingSchemeResponse])
def list_mapping_schemes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return db.scalars(select(MappingScheme).order_by(MappingScheme.name)).all()


@router.post("/mapping-schemes", response_model=MappingSchemeResponse, status_code=status.HTTP_201_CREATED)
def create_mapping_scheme(
    data: MappingSchemeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    scheme = MappingScheme(name=data.name, description=data.description)
    db.add(scheme)
    db.commit()
    db.refresh(scheme)
    return scheme


@router.get("/mapping-schemes/{scheme_id}/classifications", response_model=List[AccountClassificationResponse])
def list_classifications(
    scheme_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    scheme = db.get(MappingScheme, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping scheme not found")
    return db.scalars(
        select(AccountClassification)
        .where(AccountClassification.scheme_id == scheme_id)
        .order_by(AccountClassification.sort_order)
    ).all()


@router.put("/accounts/{account_id}/classifications", response_model=List[AccountClassificationResponse])
def update_account_classifications(
    account_id: int,
    data: AccountClassificationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Replace all classifications for an account."""
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    # Delete existing classifications for this account
    db.execute(delete(AccountClassification).where(AccountClassification.account_id == account_id))

    new_classifications = []
    for item in data.classifications:
        scheme = db.get(MappingScheme, item.scheme_id)
        if scheme is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Mapping scheme {item.scheme_id} not found",
            )
        cl = AccountClassification(
            account_id=account_id,
            scheme_id=item.scheme_id,
            classification_value=item.classification_value,
            sort_order=item.sort_order,
        )
        db.add(cl)
        new_classifications.append(cl)

    db.commit()
    for cl in new_classifications:
        db.refresh(cl)
    return new_classifications


# ---------------------------------------------------------------------------
# Segment Definitions
# ---------------------------------------------------------------------------

@router.get("/segment-definitions", response_model=List[SegmentDefinitionResponse])
def list_segment_definitions(
    connector_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    stmt = select(SegmentDefinition).order_by(SegmentDefinition.segment_number)
    if connector_id is not None:
        stmt = stmt.where(SegmentDefinition.connector_id == connector_id)
    return db.scalars(stmt).all()


@router.put("/segment-definitions/{seg_id}", response_model=SegmentDefinitionResponse)
def update_segment_definition(
    seg_id: int,
    data: SegmentDefinitionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin")),
):
    seg = db.get(SegmentDefinition, seg_id)
    if seg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segment definition not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(seg, field, value)

    db.commit()
    db.refresh(seg)
    return seg
