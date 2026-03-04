from datetime import datetime, timezone
from typing import List, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_active_user, require_role
from app.models.connector import ExternalConnector
from app.models.user import User
from app.schemas.connector import (
    ConnectorCreate,
    ConnectorUpdate,
    ConnectorResponse,
    ConnectorTestResult,
    PullRequest,
    CustomQueryRequest,
    PullResult,
)
from app.services import sql_connector as svc
from app.services.sql_connector import encrypt_password

router = APIRouter()


@router.get("/connectors", response_model=List[ConnectorResponse])
def list_connectors(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return db.scalars(select(ExternalConnector).order_by(ExternalConnector.name)).all()


@router.post("/connectors", response_model=ConnectorResponse, status_code=status.HTTP_201_CREATED)
def create_connector(
    data: ConnectorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin")),
):
    encrypted_pw = encrypt_password(data.password) if data.password else None
    connector = ExternalConnector(
        name=data.name,
        system_type=data.system_type,
        host=data.host,
        port=data.port,
        database_name=data.database_name,
        username=data.username,
        encrypted_password=encrypted_pw,
        schema_name=data.schema_name,
        created_by_user_id=current_user.id,
    )
    db.add(connector)
    db.commit()
    db.refresh(connector)
    return connector


@router.get("/connectors/{connector_id}", response_model=ConnectorResponse)
def get_connector(
    connector_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    connector = db.get(ExternalConnector, connector_id)
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")
    return connector


@router.put("/connectors/{connector_id}", response_model=ConnectorResponse)
def update_connector(
    connector_id: int,
    data: ConnectorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin")),
):
    connector = db.get(ExternalConnector, connector_id)
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")

    if data.name is not None:
        connector.name = data.name
    if data.host is not None:
        connector.host = data.host
    if data.port is not None:
        connector.port = data.port
    if data.database_name is not None:
        connector.database_name = data.database_name
    if data.username is not None:
        connector.username = data.username
    if data.password is not None:
        connector.encrypted_password = encrypt_password(data.password)
    if data.schema_name is not None:
        connector.schema_name = data.schema_name
    if data.is_active is not None:
        connector.is_active = data.is_active

    db.commit()
    db.refresh(connector)
    return connector


@router.delete("/connectors/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connector(
    connector_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin")),
):
    connector = db.get(ExternalConnector, connector_id)
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")
    db.delete(connector)
    db.commit()


@router.post("/connectors/{connector_id}/test", response_model=ConnectorTestResult)
def test_connector(
    connector_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    connector = db.get(ExternalConnector, connector_id)
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")

    result = svc.test_connection(connector)
    connector.last_tested_at = datetime.now(timezone.utc)
    db.commit()

    return ConnectorTestResult(
        success=result["success"],
        message=result["message"],
        tables=result.get("tables"),
    )


@router.post("/connectors/{connector_id}/pull/coa", response_model=PullResult)
def pull_chart_of_accounts(
    connector_id: int,
    data: PullRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Pull chart of accounts from AMAIS and upsert into accounts table."""
    from sqlalchemy import select as sa_select, and_
    from app.models.account import Account
    from app.models.period import FiscalYear

    connector = db.get(ExternalConnector, connector_id)
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")

    # Find or require a fiscal year
    fy = db.scalars(
        sa_select(FiscalYear).where(FiscalYear.label == str(data.fiscal_year))
    ).first()
    if fy is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No fiscal year found with label '{data.fiscal_year}'. Create it first.",
        )

    try:
        rows = svc.pull_coa(connector, data.fiscal_year)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    created = 0
    updated = 0
    errors: List[str] = []

    for row in rows:
        try:
            acct_fmtd = str(row.get("acct_fmtd", "")).strip()
            if not acct_fmtd:
                continue

            existing = db.scalars(
                sa_select(Account).where(
                    and_(
                        Account.acct_fmtd == acct_fmtd,
                        Account.fiscal_year_id == fy.id,
                    )
                )
            ).first()

            fields: Dict[str, Any] = {
                "description": row.get("description"),
                "acct_type": row.get("acct_type"),
                "record_class": row.get("record_class"),
                "capital_acct": bool(row.get("capital_acct")) if row.get("capital_acct") is not None else None,
                "dept_code": str(row.get("dept_code")) if row.get("dept_code") is not None else None,
                "fund_code": str(row.get("fund_code")) if row.get("fund_code") is not None else None,
                "stat": row.get("stat"),
                "total_lvl": row.get("total_lvl"),
                "total_lvl_cde": row.get("total_lvl_cde"),
                "rev_exp_rpt": row.get("rev_exp_rpt"),
                "object_str": row.get("object_str"),
                "project_str": row.get("project_str"),
                "seg1": row.get("seg1"),
                "seg2": row.get("seg2"),
                "seg3": row.get("seg3"),
                "seg4": row.get("seg4"),
                "seg5": row.get("seg5"),
                "seg6": row.get("seg6"),
                "seg7": row.get("seg7"),
                "seg8": row.get("seg8"),
                "seg9": row.get("seg9"),
                "seg10": row.get("seg10"),
                "seg1_descr": row.get("seg1_descr"),
                "seg2_descr": row.get("seg2_descr"),
                "seg3_descr": row.get("seg3_descr"),
                "seg4_descr": row.get("seg4_descr"),
                "seg5_descr": row.get("seg5_descr"),
                "seg6_descr": row.get("seg6_descr"),
                "seg7_descr": row.get("seg7_descr"),
                "seg8_descr": row.get("seg8_descr"),
                "seg9_descr": row.get("seg9_descr"),
                "seg10_descr": row.get("seg10_descr"),
                "source_system": "amais",
                "connector_id": connector_id,
            }

            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
                updated += 1
            else:
                account = Account(
                    fiscal_year_id=fy.id,
                    acct_fmtd=acct_fmtd,
                    is_active=True,
                    **fields,
                )
                db.add(account)
                created += 1

        except Exception as exc:
            errors.append(f"Account '{row.get('acct_fmtd')}': {exc}")

    connector.last_pull_at = datetime.now(timezone.utc)
    db.commit()

    return PullResult(
        records_processed=len(rows),
        records_created=created,
        records_updated=updated,
        errors=errors,
    )


@router.post("/connectors/{connector_id}/pull/trial-balance", response_model=PullResult)
def pull_trial_balance(
    connector_id: int,
    data: PullRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Pull trial balance from AMAIS for a specific period."""
    from app.models.period import FiscalYear, Period
    from app.services import trial_balance as tb_svc
    from sqlalchemy import select as sa_select

    connector = db.get(ExternalConnector, connector_id)
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")

    if data.period is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="period is required for trial balance pull")

    fy = db.scalars(sa_select(FiscalYear).where(FiscalYear.label == str(data.fiscal_year))).first()
    if fy is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Fiscal year '{data.fiscal_year}' not found")

    period = db.scalars(
        sa_select(Period).where(
            Period.fiscal_year_id == fy.id,
            Period.period_number == data.period,
        )
    ).first()
    if period is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Period {data.period} not found in fiscal year {data.fiscal_year}",
        )

    imported, updated_count, errors = tb_svc.import_from_connector(
        db=db,
        connector_id=connector_id,
        fiscal_year_id=fy.id,
        period_id=period.id,
        fiscal_year=data.fiscal_year,
        period_number=data.period,
    )
    return PullResult(
        records_processed=imported + updated_count,
        records_created=imported,
        records_updated=updated_count,
        errors=errors,
    )


@router.post("/connectors/{connector_id}/pull/budget", response_model=PullResult)
def pull_budget(
    connector_id: int,
    data: PullRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin", "finance_officer")),
):
    """Pull budget data from AMAIS and create BudgetLine records."""
    from decimal import Decimal
    from app.models.budget import BudgetLine, BudgetYear
    from app.models.account import Account
    from app.models.period import FiscalYear
    from sqlalchemy import select as sa_select, and_

    connector = db.get(ExternalConnector, connector_id)
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")

    fy = db.scalars(sa_select(FiscalYear).where(FiscalYear.label == str(data.fiscal_year))).first()
    if fy is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Fiscal year '{data.fiscal_year}' not found")

    try:
        rows = svc.pull_budget(connector, data.fiscal_year)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    # Find or create a BudgetYear for this fiscal year
    budget_year = db.scalars(sa_select(BudgetYear).where(BudgetYear.fiscal_year_id == fy.id)).first()
    if budget_year is None:
        budget_year = BudgetYear(
            fiscal_year_id=fy.id,
            label=f"Budget {fy.label}",
            status="open",
            created_by=current_user.id,
        )
        db.add(budget_year)
        db.flush()

    created = 0
    updated_count = 0
    errors: List[str] = []

    for row in rows:
        try:
            acct_fmtd = str(row.get("acct_fmtd", "")).strip()
            if not acct_fmtd:
                continue

            account = db.scalars(
                sa_select(Account).where(
                    and_(Account.acct_fmtd == acct_fmtd, Account.fiscal_year_id == fy.id)
                )
            ).first()
            if account is None:
                errors.append(f"Account '{acct_fmtd}' not found; skipped")
                continue

            amount = Decimal(str(row.get("amount", 0) or 0))
            existing = db.scalars(
                sa_select(BudgetLine).where(
                    and_(
                        BudgetLine.budget_year_id == budget_year.id,
                        BudgetLine.account_id == account.id,
                    )
                )
            ).first()

            if existing:
                existing.approved_amount = amount
                updated_count += 1
            else:
                bl = BudgetLine(
                    budget_year_id=budget_year.id,
                    account_id=account.id,
                    approved_amount=amount,
                    budget_type="operating",
                )
                db.add(bl)
                created += 1

        except Exception as exc:
            errors.append(f"Budget row '{row.get('acct_fmtd')}': {exc}")

    connector.last_pull_at = datetime.now(timezone.utc)
    db.commit()

    return PullResult(
        records_processed=len(rows),
        records_created=created,
        records_updated=updated_count,
        errors=errors,
    )


@router.post("/connectors/{connector_id}/query")
def custom_query(
    connector_id: int,
    data: CustomQueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("finance_admin")),
) -> List[Dict[str, Any]]:
    """Execute a custom SELECT query against the connector. finance_admin only."""
    connector = db.get(ExternalConnector, connector_id)
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")

    try:
        results = svc.execute_custom_query(connector, data.sql, data.params)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    return results
