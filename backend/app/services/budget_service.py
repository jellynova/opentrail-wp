"""
Budget service: variance analysis and budget workflow helpers.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.budget import BudgetLine, BudgetYear
from app.models.period import Period
from app.models.trial_balance import TrialBalanceEntry


def get_variance_report(db: Session, budget_year_id: int) -> Dict[str, Any]:
    """
    Build a budget vs actual variance report for the given budget year.

    Actuals are derived from YTD trial balance entries for all periods belonging
    to the associated fiscal year. Budget figures come from BudgetLine rows.

    Returns a dict matching the VarianceReport schema.
    """
    budget_year = db.get(BudgetYear, budget_year_id)
    if budget_year is None:
        raise ValueError(f"BudgetYear {budget_year_id} not found")

    fiscal_year_id = budget_year.fiscal_year_id

    # Load all budget lines for this budget year
    budget_lines = db.scalars(
        select(BudgetLine).where(BudgetLine.budget_year_id == budget_year_id)
    ).all()

    budget_by_account: Dict[int, Decimal] = {}
    for bl in budget_lines:
        budget_by_account[bl.account_id] = budget_by_account.get(bl.account_id, Decimal("0")) + Decimal(
            str(bl.approved_amount)
        )

    # Load all periods for the fiscal year to get their IDs
    periods = db.scalars(
        select(Period).where(Period.fiscal_year_id == fiscal_year_id)
    ).all()
    period_ids = [p.id for p in periods]

    # Aggregate YTD actuals from trial balance entries (take the max period's ytd values
    # since YTD is cumulative; we want the latest closed period's YTD)
    # Strategy: group by account_id, take the latest period's ytd figures
    ytd_by_account: Dict[int, Decimal] = {}
    if period_ids:
        tb_entries = db.scalars(
            select(TrialBalanceEntry).where(TrialBalanceEntry.period_id.in_(period_ids))
        ).all()

        # For each account, sum up the period movements to get YTD actual
        # (Use ytd_debit - ytd_credit as net amount; this is approximate without knowing normal_balance)
        # More accurately, sum period debits and credits across all periods
        account_period_debits: Dict[int, Decimal] = {}
        account_period_credits: Dict[int, Decimal] = {}
        for entry in tb_entries:
            acct_id = entry.account_id
            account_period_debits[acct_id] = account_period_debits.get(acct_id, Decimal("0")) + Decimal(
                str(entry.period_debit)
            )
            account_period_credits[acct_id] = account_period_credits.get(acct_id, Decimal("0")) + Decimal(
                str(entry.period_credit)
            )

        for acct_id in account_period_debits.keys() | account_period_credits.keys():
            net = account_period_credits.get(acct_id, Decimal("0")) - account_period_debits.get(
                acct_id, Decimal("0")
            )
            ytd_by_account[acct_id] = net

    # Build variance rows for all account IDs appearing in budget lines
    all_account_ids = set(budget_by_account.keys()) | set(ytd_by_account.keys())
    accounts = db.scalars(select(Account).where(Account.id.in_(all_account_ids))).all()
    account_map = {a.id: a for a in accounts}

    rows = []
    total_budget = Decimal("0")
    total_actual = Decimal("0")

    for acct_id in sorted(all_account_ids):
        account = account_map.get(acct_id)
        approved_budget = budget_by_account.get(acct_id, Decimal("0"))
        ytd_actual = ytd_by_account.get(acct_id, Decimal("0"))
        variance = approved_budget - ytd_actual

        if approved_budget != Decimal("0"):
            variance_pct = (variance / approved_budget * Decimal("100")).quantize(Decimal("0.01"))
        else:
            variance_pct = None

        rows.append(
            {
                "account_id": acct_id,
                "acct_fmtd": account.acct_fmtd if account else str(acct_id),
                "description": account.description if account else None,
                "approved_budget": approved_budget,
                "ytd_actual": ytd_actual,
                "variance": variance,
                "variance_pct": variance_pct,
            }
        )
        total_budget += approved_budget
        total_actual += ytd_actual

    return {
        "budget_year_id": budget_year_id,
        "rows": rows,
        "total_budget": total_budget,
        "total_actual": total_actual,
        "total_variance": total_budget - total_actual,
    }
