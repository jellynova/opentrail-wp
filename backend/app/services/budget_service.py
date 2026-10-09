"""
Budget module services (PLAN §6): prior-year figures for requests, consolidation of
approved requests into budget lines, budget imports, amendments, budget-to-actual
variance, multi-year comparison and the council budget report.

Sign conventions
----------------
Budget amounts are entered as positive numbers for both revenue and expense. Actuals come
from the balance engine (debit-positive) and are converted to the same "natural" sign:
credit-natured accounts (revenue, liabilities) are negated. Variance is reported as
*favourable-positive*: revenue actual above budget, or spending below budget, is positive.
"""
from __future__ import annotations

import csv
import io
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.account import Account
from app.models.budget import BudgetAmendment, BudgetAmendmentLine, BudgetLine, BudgetRequest, BudgetYear
from app.models.period import FiscalYear, Period
from app.services import import_parsers
from app.services.balances import (
    ZERO,
    account_balances,
    accounts_by_code,
    classifications,
    is_credit_natured,
    last_period_number,
    load_accounts,
    prior_fiscal_year,
    resolve_scheme_id,
)

UNASSIGNED = "Unassigned"


# ---------------------------------------------------------------------------
# Budget amounts
# ---------------------------------------------------------------------------

def budget_year_for_fiscal_year(db: Session, fiscal_year_id: int) -> Optional[BudgetYear]:
    """The budget year for a fiscal year (the most recently created, if several)."""
    return db.scalars(
        select(BudgetYear).where(BudgetYear.fiscal_year_id == fiscal_year_id).order_by(BudgetYear.id.desc())
    ).first()


def original_budget(db: Session, budget_year_id: int) -> Dict[int, Decimal]:
    amounts: Dict[int, Decimal] = {}
    for bl in db.scalars(select(BudgetLine).where(BudgetLine.budget_year_id == budget_year_id)).all():
        amounts[bl.account_id] = amounts.get(bl.account_id, ZERO) + Decimal(str(bl.approved_amount))
    return amounts


def amendment_totals(db: Session, budget_year_id: int) -> Dict[int, Decimal]:
    rows = db.execute(
        select(BudgetAmendmentLine.account_id, BudgetAmendmentLine.amount)
        .join(BudgetAmendment, BudgetAmendmentLine.amendment_id == BudgetAmendment.id)
        .where(BudgetAmendment.budget_year_id == budget_year_id, BudgetAmendment.status == "approved")
    ).all()
    out: Dict[int, Decimal] = {}
    for account_id, amount in rows:
        out[account_id] = out.get(account_id, ZERO) + Decimal(str(amount))
    return out


def budget_amounts_by_account(db: Session, fiscal_year_id: int, version: str = "original") -> Dict[int, Decimal]:
    """
    Budget per account for a fiscal year, as entered (positive for revenue and expense).
    version: "original" (adopted budget lines) or "amended" (plus approved amendments).
    """
    by = budget_year_for_fiscal_year(db, fiscal_year_id)
    if by is None:
        return {}
    amounts = original_budget(db, by.id)
    if version == "amended":
        for acct_id, delta in amendment_totals(db, by.id).items():
            amounts[acct_id] = amounts.get(acct_id, ZERO) + delta
    return amounts


def natural_actual(account: Optional[Account], classification: Optional[str], debit_positive: Decimal) -> Decimal:
    return -debit_positive if is_credit_natured(account, classification) else debit_positive


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

def prior_year_figures(db: Session, budget_year: BudgetYear, account: Account) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    """(prior-year actual, prior-year budget) for the account matched by code, or Nones."""
    prior_fy = prior_fiscal_year(db, budget_year.fiscal_year_id)
    if prior_fy is None:
        return None, None
    prior_acct = accounts_by_code(db, prior_fy.id).get(account.acct_fmtd)
    if prior_acct is None:
        return None, None
    balances = account_balances(db, prior_fy.id, last_period_number(db, prior_fy.id))
    cls = classifications(db, resolve_scheme_id(db, "PSAB"), [prior_acct.id]).get(prior_acct.id)
    b = balances.get(prior_acct.id)
    actual = natural_actual(prior_acct, cls, b.closing()) if b else ZERO
    prior_by = budget_year_for_fiscal_year(db, prior_fy.id)
    budget = None
    if prior_by is not None:
        budget = original_budget(db, prior_by.id).get(prior_acct.id, ZERO) + amendment_totals(db, prior_by.id).get(
            prior_acct.id, ZERO)
    return actual, budget


def consolidate_requests(db: Session, budget_year: BudgetYear) -> int:
    """Replace the budget year's lines with approved/modified requests summed by account."""
    requests = db.scalars(select(BudgetRequest).where(
        BudgetRequest.budget_year_id == budget_year.id, BudgetRequest.status.in_(("approved", "modified"))
    )).all()
    totals: Dict[int, Decimal] = {}
    for r in requests:
        amount = r.approved_amount if r.approved_amount is not None else r.proposed_amount
        totals[r.account_id] = totals.get(r.account_id, ZERO) + Decimal(str(amount or 0))
    return replace_lines(db, budget_year, totals)


def replace_lines(db: Session, budget_year: BudgetYear, totals: Dict[int, Decimal]) -> int:
    for bl in db.scalars(select(BudgetLine).where(BudgetLine.budget_year_id == budget_year.id)).all():
        db.delete(bl)
    accounts = load_accounts(db, totals.keys())
    for acct_id, amount in sorted(totals.items()):
        acct = accounts.get(acct_id)
        db.add(BudgetLine(
            budget_year_id=budget_year.id, account_id=acct_id, approved_amount=amount,
            budget_type="capital" if acct is not None and acct.capital_acct else "operating",
        ))
    db.commit()
    return len(totals)


def lines_from_csv(db: Session, budget_year: BudgetYear, content: bytes,
                   sheet: Optional[str] = None) -> Tuple[Dict[int, Decimal], List[str]]:
    """CSV with Account and Amount columns (case-insensitive). Amounts summed per account."""
    # CSV keeps the historical behaviour; xlsx / tab-delimited / IIF / HTML exports are
    # normalised by the shared parser into the same shape first.
    if import_parsers.sniff_format("", content) != "csv":
        try:
            content = import_parsers.normalise_to_csv(content, "", sheet)
        except import_parsers.ImportParseError as exc:
            return {}, [str(exc)]
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    headers = {h.strip().lower(): h for h in (reader.fieldnames or [])}
    acct_col = next((headers[h] for h in ("account", "acct_fmtd", "account no", "gl account") if h in headers), None)
    amt_col = next((headers[h] for h in ("amount", "budget", "approved_amount") if h in headers), None)
    if acct_col is None or amt_col is None:
        return {}, ["CSV needs 'Account' and 'Amount' columns"]
    by_code = accounts_by_code(db, budget_year.fiscal_year_id)
    totals: Dict[int, Decimal] = {}
    errors: List[str] = []
    for line_no, row in enumerate(reader, start=2):
        code = (row.get(acct_col) or "").strip()
        acct = by_code.get(code)
        if acct is None:
            errors.append(f"Row {line_no}: account '{code}' not found")
            continue
        try:
            amount = import_parsers.parse_amount(row.get(amt_col))
        except Exception:
            errors.append(f"Row {line_no}: invalid amount")
            continue
        totals[acct.id] = totals.get(acct.id, ZERO) + amount
    return totals, errors


def lines_from_connector_rows(db: Session, budget_year: BudgetYear, rows: Iterable[Dict[str, Any]],
                              rec_type: str) -> Tuple[Dict[int, Decimal], List[str]]:
    """
    Convert AMAIS gl-bud rows for one rec-type into budget amounts. ERP amounts use the TB
    import sign convention (positive = credit); they are converted to entered-positive
    amounts by the account's natural side.
    """
    by_code = accounts_by_code(db, budget_year.fiscal_year_id)
    classes = classifications(db, resolve_scheme_id(db, "PSAB"), [a.id for a in by_code.values()])
    totals: Dict[int, Decimal] = {}
    missing = set()
    for row in rows:
        if str(row.get("rec_type", "")).strip() != rec_type:
            continue
        code = str(row.get("acct_fmtd", "") or "").strip()
        acct = by_code.get(code)
        if acct is None:
            missing.add(code)
            continue
        debit_positive = -Decimal(str(row.get("amount") or 0))
        totals[acct.id] = totals.get(acct.id, ZERO) + natural_actual(acct, classes.get(acct.id), debit_positive)
    return totals, [f"Account '{c}' not found; skipped" for c in sorted(missing)]


def next_amendment_number(db: Session, budget_year_id: int) -> int:
    numbers = db.scalars(select(BudgetAmendment.amendment_number).where(
        BudgetAmendment.budget_year_id == budget_year_id)).all()
    return max(numbers, default=0) + 1


# ---------------------------------------------------------------------------
# Budget to actual
# ---------------------------------------------------------------------------

def _departments(db: Session, budget_year_id: int, accounts: Dict[int, Account]) -> Dict[int, str]:
    """Department per account: the ERP dept_code, else the department on its budget requests."""
    from_requests = {
        r.account_id: r.department
        for r in db.scalars(select(BudgetRequest).where(BudgetRequest.budget_year_id == budget_year_id)).all()
    }
    return {
        acct_id: (acct.dept_code or from_requests.get(acct_id) or UNASSIGNED)
        for acct_id, acct in accounts.items()
    }


def traffic_light(variance: Decimal, variance_pct: Optional[Decimal], amber_pct: Decimal, red_pct: Decimal) -> str:
    """green: favourable or within tolerance; amber/red: unfavourable beyond the thresholds."""
    if variance >= 0:
        return "green"
    if variance_pct is None:
        return "red"
    over = abs(variance_pct)
    return "red" if over > red_pct else "amber" if over > amber_pct else "green"


def _variance(kind: str, budget: Decimal, actual: Decimal) -> Tuple[Decimal, Optional[Decimal]]:
    variance = actual - budget if kind == "revenue" else budget - actual
    pct = (variance / budget * Decimal("100")).quantize(Decimal("0.01")) if budget else None
    return variance, pct


def variance_report(
    db: Session,
    budget_year_id: int,
    period_id: Optional[int] = None,
    group_by: str = "account",
    department: Optional[str] = None,
    amber_pct: Decimal = Decimal("5"),
    red_pct: Decimal = Decimal("10"),
) -> Dict[str, Any]:
    """
    Budget vs actual. Actuals are YTD through `period_id` (default: year end) from the TB
    plus posted adjusting/reclassifying entries. group_by: account | department |
    classification. `department` filters to one department (drill-down).
    """
    by = db.get(BudgetYear, budget_year_id)
    if by is None:
        raise ValueError(f"BudgetYear {budget_year_id} not found")
    fy = db.get(FiscalYear, by.fiscal_year_id)
    period = db.get(Period, period_id) if period_id else None
    if period_id and (period is None or period.fiscal_year_id != by.fiscal_year_id):
        raise ValueError(f"Period {period_id} is not in the budget's fiscal year")
    last = last_period_number(db, by.fiscal_year_id)
    through = period.period_number if period else last

    original = original_budget(db, by.id)
    amendments = amendment_totals(db, by.id)
    balances = account_balances(db, by.fiscal_year_id, through)
    budget_ids = set(original) | set(amendments)
    accounts = load_accounts(db, budget_ids | set(balances))
    classes = classifications(db, resolve_scheme_id(db, "PSAB"), accounts.keys())
    depts = _departments(db, by.id, accounts)

    rows = []
    for acct_id, acct in accounts.items():
        cls = classes.get(acct_id)
        top = (cls or "").split(".")[0]
        # Only budgeted accounts and operating (revenue/expense) accounts belong in the comparison.
        if acct_id not in budget_ids and top not in ("revenue", "expense"):
            continue
        if department and depts[acct_id] != department:
            continue
        kind = "revenue" if is_credit_natured(acct, cls) else "expense"
        orig = original.get(acct_id, ZERO)
        amended = orig + amendments.get(acct_id, ZERO)
        b = balances.get(acct_id)
        actual = natural_actual(acct, cls, b.closing()) if b else ZERO
        variance, pct = _variance(kind, amended, actual)
        rows.append({
            "account_id": acct_id,
            "acct_fmtd": acct.acct_fmtd,
            "description": acct.description,
            "department": depts[acct_id],
            "classification": cls,
            "kind": kind,
            "original_budget": orig,
            "amended_budget": amended,
            "approved_budget": amended,  # backwards-compatible name
            "ytd_actual": actual,
            "variance": variance,
            "variance_pct": pct,
            "percent_used": (actual / amended * 100).quantize(Decimal("0.1")) if amended else None,
            "status": traffic_light(variance, pct, amber_pct, red_pct),
        })
    rows.sort(key=lambda r: (r["kind"] != "revenue", r["acct_fmtd"]))

    groups = None
    if group_by in ("department", "classification"):
        acc: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for r in rows:
            key = (r[group_by] or "unclassified", r["kind"])
            g = acc.setdefault(key, {"group": key[0], "kind": key[1], "original_budget": ZERO,
                                     "amended_budget": ZERO, "ytd_actual": ZERO, "accounts": 0})
            for k in ("original_budget", "amended_budget", "ytd_actual"):
                g[k] += r[k]
            g["accounts"] += 1
        groups = []
        for g in sorted(acc.values(), key=lambda g: (g["kind"] != "revenue", g["group"])):
            g["variance"], g["variance_pct"] = _variance(g["kind"], g["amended_budget"], g["ytd_actual"])
            g["status"] = traffic_light(g["variance"], g["variance_pct"], amber_pct, red_pct)
            groups.append(g)

    def total(kind, key):
        return sum((r[key] for r in rows if r["kind"] == kind), ZERO)

    rev_budget, exp_budget = total("revenue", "amended_budget"), total("expense", "amended_budget")
    rev_actual, exp_actual = total("revenue", "ytd_actual"), total("expense", "ytd_actual")
    return {
        "budget_year_id": by.id,
        "budget_year": by.label,
        "fiscal_year": fy.label if fy else None,
        "through_period": through,
        "percent_of_year": (Decimal(through) / Decimal(last) * 100).quantize(Decimal("0.1")) if last else None,
        "group_by": group_by,
        "department": department,
        "rows": rows,
        "groups": groups,
        "total_revenue_budget": rev_budget,
        "total_revenue_actual": rev_actual,
        "total_expense_budget": exp_budget,
        "total_expense_actual": exp_actual,
        # legacy totals: net of revenue and expense in natural terms (surplus)
        "total_budget": rev_budget - exp_budget,
        "total_actual": rev_actual - exp_actual,
        "total_variance": (rev_actual - exp_actual) - (rev_budget - exp_budget),
    }


def multi_year_comparison(db: Session, budget_year_id: int, group_by: str = "classification") -> Dict[str, Any]:
    """Current budget / current actual / prior actual / prior budget, grouped (PLAN §6.3)."""
    current = variance_report(db, budget_year_id, group_by="account")
    by = db.get(BudgetYear, budget_year_id)
    prior_fy = prior_fiscal_year(db, by.fiscal_year_id)
    prior_rows: Dict[str, Dict[str, Any]] = {}
    if prior_fy is not None:
        prior_by = budget_year_for_fiscal_year(db, prior_fy.id)
        if prior_by is not None:
            prior_rows = {r["acct_fmtd"]: r for r in variance_report(db, prior_by.id)["rows"]}
        else:
            balances = account_balances(db, prior_fy.id, last_period_number(db, prior_fy.id))
            accts = load_accounts(db, balances)
            cls = classifications(db, resolve_scheme_id(db, "PSAB"), accts)
            for acct_id, a in accts.items():
                if (cls.get(acct_id) or "").split(".")[0] in ("revenue", "expense"):
                    prior_rows[a.acct_fmtd] = {"ytd_actual": natural_actual(a, cls.get(acct_id),
                                                                            balances[acct_id].closing()),
                                               "amended_budget": ZERO}

    groups: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in current["rows"]:
        key = ((r[group_by] if group_by != "account" else r["acct_fmtd"]) or "unclassified", r["kind"])
        g = groups.setdefault(key, {"group": key[0], "kind": key[1], "current_budget": ZERO,
                                    "current_actual": ZERO, "prior_actual": ZERO, "prior_budget": ZERO})
        p = prior_rows.get(r["acct_fmtd"], {})
        g["current_budget"] += r["amended_budget"]
        g["current_actual"] += r["ytd_actual"]
        g["prior_actual"] += p.get("ytd_actual", ZERO)
        g["prior_budget"] += p.get("amended_budget", ZERO)
    return {
        "budget_year": current["budget_year"],
        "fiscal_year": current["fiscal_year"],
        "prior_fiscal_year": prior_fy.label if prior_fy else None,
        "group_by": group_by,
        "rows": sorted(groups.values(), key=lambda g: (g["kind"] != "revenue", g["group"])),
    }


# ---------------------------------------------------------------------------
# Tabular outputs for export
# ---------------------------------------------------------------------------

def _label_for(group: str) -> str:
    from app.services.builtin_templates import PSAB_TAXONOMY

    return PSAB_TAXONOMY.get(group, group)


def variance_table(report: Dict[str, Any]) -> Dict[str, Any]:
    use_groups = report.get("groups") is not None
    items = report["groups"] if use_groups else report["rows"]
    out: List[Dict[str, Any]] = []
    for kind, title in (("revenue", "Revenue"), ("expense", "Expenses")):
        sub = [i for i in items if i["kind"] == kind]
        if not sub:
            continue
        out.append({"label": title, "values": {}, "level": 0, "style": {"bold": True}, "text": {}})
        tot = {k: ZERO for k in ("original_budget", "amended_budget", "ytd_actual")}
        for i in sub:
            label = _label_for(i["group"]) if use_groups else f"{i['acct_fmtd']}  {i['description'] or ''}"
            out.append({"label": label, "level": 1, "style": {}, "text": {"status": i["status"]},
                        "values": {k: i[k] for k in ("original_budget", "amended_budget", "ytd_actual", "variance",
                                                     "variance_pct")}})
            for k in tot:
                tot[k] += i[k]
        var, pct = _variance(kind, tot["amended_budget"], tot["ytd_actual"])
        out.append({"label": f"Total {title.lower()}", "level": 0, "style": {"bold": True, "underline": "single"},
                    "text": {}, "values": {**tot, "variance": var, "variance_pct": pct}})
    sub_title = f"Through period {report['through_period']} ({report['percent_of_year']}% of year)"
    if report.get("department"):
        sub_title += f" — {report['department']}"
    return {
        "organization": settings.ORGANIZATION_NAME,
        "title": f"Budget vs. Actual — {report['budget_year']}",
        "subtitle": sub_title,
        "number_format": {"decimals": 0},
        "columns": [
            {"key": "original_budget", "label": "Original budget"},
            {"key": "amended_budget", "label": "Amended budget"},
            {"key": "ytd_actual", "label": "Actual YTD"},
            {"key": "variance", "label": "Variance fav/(unfav)"},
            {"key": "variance_pct", "label": "%", "percent": True},
        ],
        "text_columns": [{"key": "status", "label": "Status", "width": 8}],
        "rows": out,
    }


def council_report(db: Session, budget_year_id: int, group_by: str = "classification") -> Dict[str, Any]:
    """Council-ready budget presentation: proposed budget vs prior year budget and actual."""
    data = multi_year_comparison(db, budget_year_id, group_by)
    by = db.get(BudgetYear, budget_year_id)
    out: List[Dict[str, Any]] = []
    totals: Dict[str, Dict[str, Decimal]] = {}
    for kind, title in (("revenue", "Revenue"), ("expense", "Expenses")):
        sub = [g for g in data["rows"] if g["kind"] == kind]
        if not sub:
            continue
        out.append({"label": title, "values": {}, "level": 0, "style": {"bold": True}, "text": {}})
        t = {k: ZERO for k in ("prior_actual", "prior_budget", "current_budget")}
        for g in sub:
            change = g["current_budget"] - g["prior_budget"]
            out.append({"label": _label_for(g["group"]), "level": 1, "style": {}, "text": {}, "values": {
                "prior_actual": g["prior_actual"], "prior_budget": g["prior_budget"],
                "current_budget": g["current_budget"], "change": change,
                "change_pct": (change / g["prior_budget"] * 100) if g["prior_budget"] else None}})
            for k in t:
                t[k] += g[k]
        change = t["current_budget"] - t["prior_budget"]
        out.append({"label": f"Total {title.lower()}", "level": 0, "style": {"bold": True, "underline": "single"},
                    "text": {}, "values": {**t, "change": change,
                                           "change_pct": (change / t["prior_budget"] * 100) if t["prior_budget"] else None}})
        totals[kind] = t
    if "revenue" in totals or "expense" in totals:
        rev = totals.get("revenue", {k: ZERO for k in ("prior_actual", "prior_budget", "current_budget")})
        exp = totals.get("expense", {k: ZERO for k in ("prior_actual", "prior_budget", "current_budget")})
        net = {k: rev[k] - exp[k] for k in rev}
        out.append({"label": "Surplus (deficit) before transfers", "level": 0, "text": {},
                    "style": {"bold": True, "underline": "double"},
                    "values": {**net, "change": net["current_budget"] - net["prior_budget"]}})
    prior = data["prior_fiscal_year"] or "Prior year"
    return {
        "organization": settings.ORGANIZATION_NAME,
        "title": f"{by.label} Budget",
        "subtitle": f"Status: {by.status.replace('_', ' ')}",
        "number_format": {"decimals": 0},
        "columns": [
            {"key": "prior_actual", "label": f"{prior} Actual"},
            {"key": "prior_budget", "label": f"{prior} Budget"},
            {"key": "current_budget", "label": f"{data['fiscal_year']} Budget"},
            {"key": "change", "label": "Change $"},
            {"key": "change_pct", "label": "Change %", "percent": True},
        ],
        "rows": out,
    }
