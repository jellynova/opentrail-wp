"""
Auto-generated working papers (PLAN §4.3 / §5.3):

* Working trial balance — opening → unadjusted → AJEs → RJEs → final, per account
* Leadsheets — working TB grouped by a mapping scheme's classification (PSAB by default),
  with prior-year final balances for comparison
* Adjusting / reclassifying journal entry schedules
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.journal_entry import JournalEntry
from app.models.period import FiscalYear, Period
from app.services.balances import (
    ZERO,
    D,
    account_balances,
    accounts_by_code,
    classifications,
    last_period_number,
    load_accounts,
    prior_fiscal_year,
    resolve_scheme_id,
)

UNCLASSIFIED = "unclassified"


def _split(net: Decimal) -> tuple[Decimal, Decimal]:
    return (net, ZERO) if net >= 0 else (ZERO, -net)


def get_period(db: Session, period_id: int) -> Period:
    period = db.get(Period, period_id)
    if period is None:
        raise ValueError(f"Period {period_id} not found")
    return period


def working_trial_balance(
    db: Session, period_id: int, scheme: Optional[object] = None
) -> List[Dict[str, Any]]:
    """Working trial balance through the given period (cumulative within the fiscal year)."""
    period = get_period(db, period_id)
    balances = account_balances(db, period.fiscal_year_id, period.period_number)
    accounts = load_accounts(db, balances.keys())
    scheme_id = resolve_scheme_id(db, scheme) if scheme is not None else None
    classes = classifications(db, scheme_id, balances.keys())

    rows = []
    for acct_id, b in balances.items():
        account = accounts.get(acct_id)
        aje_d, aje_c = b.adj_debit("adjusting"), b.adj_credit("adjusting")
        rje_d, rje_c = b.adj_debit("reclassifying"), b.adj_credit("reclassifying")
        adjusted = b.unadjusted + aje_d - aje_c
        final = adjusted + rje_d - rje_c
        closing_debit, closing_credit = _split(final)
        rows.append(
            {
                "account_id": acct_id,
                "acct_fmtd": account.acct_fmtd if account else str(acct_id),
                "description": account.description if account else None,
                "classification": classes.get(acct_id),
                "opening_debit": b.opening_debit,
                "opening_credit": b.opening_credit,
                "period_debit": b.period_debit,
                "period_credit": b.period_credit,
                "ytd_debit": b.ytd_debit,
                "ytd_credit": b.ytd_credit,
                "unadjusted_balance": b.unadjusted,
                "aje_debit": aje_d,
                "aje_credit": aje_c,
                "adjusted_balance": adjusted,
                "rje_debit": rje_d,
                "rje_credit": rje_c,
                "adj_debit": aje_d + rje_d,
                "adj_credit": aje_c + rje_c,
                "final_balance": final,
                "closing_debit": closing_debit,
                "closing_credit": closing_credit,
            }
        )
    rows.sort(key=lambda r: r["acct_fmtd"])
    return rows


def leadsheets(db: Session, period_id: int, scheme: Optional[object] = "PSAB") -> Dict[str, Any]:
    """
    Group the working trial balance by classification value. Each leadsheet lists its
    accounts with prior-year final balance (matched by acct_fmtd), unadjusted balance,
    AJE and RJE net adjustments, final balance and change from prior year.
    """
    period = get_period(db, period_id)
    scheme_id = resolve_scheme_id(db, scheme)
    if scheme_id is None:
        raise ValueError(f"Mapping scheme '{scheme}' not found")
    wtb = working_trial_balance(db, period_id, scheme_id)

    prior_by_code: Dict[str, Decimal] = {}
    prior_fy = prior_fiscal_year(db, period.fiscal_year_id)
    if prior_fy is not None:
        prior_bal = account_balances(db, prior_fy.id, last_period_number(db, prior_fy.id))
        code_of = {a.id: code for code, a in accounts_by_code(db, prior_fy.id).items()}
        for acct_id, b in prior_bal.items():
            if acct_id in code_of:
                prior_by_code[code_of[acct_id]] = b.closing()

    groups: Dict[str, Dict[str, Any]] = {}
    for r in wtb:
        key = r["classification"] or UNCLASSIFIED
        g = groups.setdefault(
            key,
            {
                "classification": key,
                "accounts": [],
                "totals": {k: ZERO for k in ("prior_year", "unadjusted", "aje", "rje", "final", "change")},
            },
        )
        prior = prior_by_code.get(r["acct_fmtd"], ZERO)
        line = {
            "account_id": r["account_id"],
            "acct_fmtd": r["acct_fmtd"],
            "description": r["description"],
            "prior_year": prior,
            "unadjusted": r["unadjusted_balance"],
            "aje": r["aje_debit"] - r["aje_credit"],
            "rje": r["rje_debit"] - r["rje_credit"],
            "final": r["final_balance"],
            "change": r["final_balance"] - prior,
        }
        g["accounts"].append(line)
        for k in g["totals"]:
            g["totals"][k] += line[k]

    ordered = sorted(groups.values(), key=lambda g: (g["classification"] == UNCLASSIFIED, g["classification"]))
    fy = db.get(FiscalYear, period.fiscal_year_id)
    return {
        "fiscal_year": fy.label if fy else None,
        "prior_fiscal_year": prior_fy.label if prior_fy else None,
        "period_id": period_id,
        "period_name": period.name,
        "scheme_id": scheme_id,
        "leadsheets": ordered,
    }


def journal_entry_schedule(
    db: Session,
    fiscal_year_id: int,
    entry_type: str = "adjusting",
    include_drafts: bool = False,
) -> Dict[str, Any]:
    """All entries of a type for the fiscal year, with lines and account codes."""
    stmt = (
        select(JournalEntry)
        .join(Period, JournalEntry.period_id == Period.id)
        .where(Period.fiscal_year_id == fiscal_year_id, JournalEntry.entry_type == entry_type)
        .order_by(JournalEntry.reference, JournalEntry.id)
    )
    if not include_drafts:
        stmt = stmt.where(JournalEntry.status.in_(("posted", "approved")))
    entries = db.scalars(stmt).all()
    accounts = load_accounts(db, (l.account_id for e in entries for l in e.lines))

    out = []
    total_debit = total_credit = ZERO
    for e in entries:
        lines = []
        for l in e.lines:
            a = accounts.get(l.account_id)
            lines.append(
                {
                    "account_id": l.account_id,
                    "acct_fmtd": a.acct_fmtd if a else str(l.account_id),
                    "account_description": a.description if a else None,
                    "description": l.description,
                    "debit": D(l.debit),
                    "credit": D(l.credit),
                }
            )
        e_debit = sum((l["debit"] for l in lines), ZERO)
        e_credit = sum((l["credit"] for l in lines), ZERO)
        total_debit += e_debit
        total_credit += e_credit
        out.append(
            {
                "id": e.id,
                "reference": e.reference,
                "entry_date": e.entry_date,
                "description": e.description,
                "status": e.status,
                "lines": lines,
                "total_debit": e_debit,
                "total_credit": e_credit,
            }
        )

    fy = db.get(FiscalYear, fiscal_year_id)
    return {
        "fiscal_year": fy.label if fy else None,
        "entry_type": entry_type,
        "entries": out,
        "total_debit": total_debit,
        "total_credit": total_credit,
    }
