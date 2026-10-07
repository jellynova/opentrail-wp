"""
Auto-generated working papers (PLAN §4.3 / §5.3):

* Working trial balance — opening → unadjusted → AJEs → RJEs → final, per account
* Leadsheets — working TB grouped by a mapping scheme's classification (PSAB by default),
  with prior-year final balances for comparison
* Adjusting / reclassifying journal entry schedules
"""
from __future__ import annotations

import io
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


# ---------------------------------------------------------------------------
# Tabular conversions for Excel/PDF export
# ---------------------------------------------------------------------------

def _org() -> str:
    from app.core.config import settings

    return settings.ORGANIZATION_NAME


def wtb_table(db: Session, period_id: int) -> Dict[str, Any]:
    period = get_period(db, period_id)
    fy = db.get(FiscalYear, period.fiscal_year_id)
    rows = working_trial_balance(db, period_id)
    keys = ["unadjusted_balance", "aje_net", "adjusted_balance", "rje_net", "final_balance"]
    out = []
    totals = {k: ZERO for k in keys}
    for r in rows:
        vals = {
            "unadjusted_balance": r["unadjusted_balance"],
            "aje_net": r["aje_debit"] - r["aje_credit"],
            "adjusted_balance": r["adjusted_balance"],
            "rje_net": r["rje_debit"] - r["rje_credit"],
            "final_balance": r["final_balance"],
        }
        for k in keys:
            totals[k] += vals[k]
        out.append({"label": r["description"] or "", "text": {"acct": r["acct_fmtd"]}, "values": vals,
                    "level": 0, "style": {}})
    out.append({"label": "Total (debits less credits)", "values": totals, "level": 0,
                "style": {"bold": True, "underline": "double"}, "text": {}})
    return {
        "organization": _org(),
        "title": "Working Trial Balance",
        "subtitle": f"{fy.label if fy else ''} — through {period.name} (debits positive, credits negative)",
        "number_format": {"decimals": 2},
        "text_columns": [{"key": "acct", "label": "Account", "width": 18}],
        "columns": [
            {"key": "unadjusted_balance", "label": "Unadjusted"},
            {"key": "aje_net", "label": "AJEs"},
            {"key": "adjusted_balance", "label": "Adjusted"},
            {"key": "rje_net", "label": "RJEs"},
            {"key": "final_balance", "label": "Final"},
        ],
        "rows": out,
    }


def leadsheets_table(db: Session, period_id: int, scheme: Optional[object] = "PSAB") -> Dict[str, Any]:
    data = leadsheets(db, period_id, scheme)
    labels = {}
    try:
        from app.services.builtin_templates import PSAB_TAXONOMY

        labels = PSAB_TAXONOMY
    except ImportError:  # pragma: no cover
        pass
    out = []
    for g in data["leadsheets"]:
        title = labels.get(g["classification"], g["classification"].replace("_", " ").replace(".", " — ").title())
        out.append({"label": title, "values": {}, "level": 0, "style": {"bold": True}, "text": {}})
        for a in g["accounts"]:
            out.append({"label": a["description"] or "", "text": {"acct": a["acct_fmtd"]}, "level": 1, "style": {},
                        "values": {k: a[k] for k in ("prior_year", "unadjusted", "aje", "rje", "final", "change")}})
        out.append({"label": f"Total {title}", "values": dict(g["totals"]), "level": 0, "text": {},
                    "style": {"bold": True, "underline": "single"}})
    return {
        "organization": _org(),
        "title": "Leadsheets",
        "subtitle": f"{data['fiscal_year']} — through {data['period_name']} (debits positive, credits negative)",
        "number_format": {"decimals": 2},
        "text_columns": [{"key": "acct", "label": "Account", "width": 18}],
        "columns": [
            {"key": "prior_year", "label": data["prior_fiscal_year"] or "Prior year"},
            {"key": "unadjusted", "label": "Unadjusted"},
            {"key": "aje", "label": "AJEs"},
            {"key": "rje", "label": "RJEs"},
            {"key": "final", "label": data["fiscal_year"] or "Final"},
            {"key": "change", "label": "Change"},
        ],
        "rows": out,
    }


def je_schedule_table(db: Session, fiscal_year_id: int, entry_type: str = "adjusting",
                      include_drafts: bool = False) -> Dict[str, Any]:
    data = journal_entry_schedule(db, fiscal_year_id, entry_type, include_drafts)
    titles = {"adjusting": "Adjusting Journal Entries", "reclassifying": "Reclassification Entries",
              "elimination": "Elimination Entries", "budget_variance": "Budget Adjustment Entries"}
    out = []
    for e in data["entries"]:
        out.append({"label": f"{e['reference'] or ''} — {e['description'] or ''}".strip(" —"),
                    "text": {"date": str(e["entry_date"]), "acct": ""}, "values": {}, "level": 0,
                    "style": {"bold": True}})
        for l in e["lines"]:
            out.append({"label": l["description"] or l["account_description"] or "", "level": 1, "style": {},
                        "text": {"date": "", "acct": l["acct_fmtd"]},
                        "values": {"debit": l["debit"] or None, "credit": l["credit"] or None}})
        out.append({"label": "", "values": {"debit": e["total_debit"], "credit": e["total_credit"]}, "level": 1,
                    "style": {"underline": "single"}, "text": {}})
    out.append({"label": "Total", "values": {"debit": data["total_debit"], "credit": data["total_credit"]},
                "level": 0, "style": {"bold": True, "underline": "double"}, "text": {}})
    return {
        "organization": _org(),
        "title": titles.get(entry_type, entry_type),
        "subtitle": f"Fiscal year {data['fiscal_year']}" + (" (including drafts)" if include_drafts else ""),
        "number_format": {"decimals": 2},
        "text_columns": [{"key": "date", "label": "Date", "width": 12}, {"key": "acct", "label": "Account", "width": 18}],
        "columns": [{"key": "debit", "label": "Debit"}, {"key": "credit", "label": "Credit"}],
        "rows": out,
    }


def working_paper_package(db: Session, period_id: int) -> bytes:
    """ZIP of the working papers and built-in financial statements for a period (PLAN §5.4)."""
    import zipfile

    from sqlalchemy import select as _select

    from app.models.report import Report
    from app.services.report_engine import ReportDefinitionError
    from app.services.report_generator import export_to_excel, export_to_pdf, generate_report_data, safe_filename

    period = get_period(db, period_id)
    fy = db.get(FiscalYear, period.fiscal_year_id)
    docs = [
        ("01_Working_Trial_Balance", wtb_table(db, period_id)),
        ("02_Leadsheets", leadsheets_table(db, period_id)),
        ("03_Adjusting_Entries", je_schedule_table(db, period.fiscal_year_id, "adjusting")),
        ("04_Reclassification_Entries", je_schedule_table(db, period.fiscal_year_id, "reclassifying")),
    ]
    statements = db.scalars(
        _select(Report).where(Report.is_template.is_(True), Report.report_type.like("psab_%")).order_by(Report.id)
    ).all()
    problems: List[str] = []
    for i, report in enumerate(statements, start=1):
        try:
            docs.append((f"Statements/{i:02d}_{safe_filename(report.name)}",
                         generate_report_data(db, report.definition, period.fiscal_year_id, period_id)))
        except (ReportDefinitionError, ValueError) as exc:
            problems.append(f"{report.name}: {exc}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, table in docs:
            zf.writestr(f"{name}.xlsx", export_to_excel(table))
            try:
                zf.writestr(f"{name}.pdf", export_to_pdf(table))
            except Exception as exc:  # PDF rendering is best-effort; Excel is always included
                problems.append(f"{name}.pdf: {exc}")
            problems.extend(f"{name}: {w}" for w in table.get("warnings", []))
        index = [f"Working paper package — {_org()}", f"Fiscal year {fy.label if fy else ''}, through {period.name}", ""]
        index += [name for name, _ in docs]
        if problems:
            index += ["", "Warnings:"] + problems
        zf.writestr("README.txt", "\n".join(index) + "\n")
    return buf.getvalue()
