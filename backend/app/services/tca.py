"""
Tangible capital asset schedule (PS 3150) — PLAN §5.2.

A continuity schedule by asset class, plus the reconciliation a finance team needs before
it goes into the financial statements: the schedule's amortization and net book value
movements should agree with the GL accounts classified as TCA cost and accumulated
amortization in the PSAB scheme (the same accounts the Statement of Change in Net
Financial Assets pulls from).
"""
from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.period import FiscalYear
from app.models.tca import TcaScheduleLine
from app.services.balances import (
    ZERO,
    account_balances,
    classifications,
    match_classification,
    resolve_scheme_id,
)

COST_CLASSIFICATIONS = ["non_financial_assets.tca_cost"]
AMORT_CLASSIFICATIONS = ["non_financial_assets.tca_amortization"]

# Accepted CSV header names (case-insensitive) for each field.
CSV_ALIASES: Dict[str, Tuple[str, ...]] = {
    "asset_class": ("asset class", "class", "asset_class", "category", "description", "asset category"),
    "cost_opening": ("cost opening", "opening cost", "cost - opening", "cost_beginning", "opening balance cost"),
    "cost_additions": ("additions", "cost additions", "additions cost", "acquisitions"),
    "cost_disposals": ("disposals", "cost disposals", "disposals cost", "retirements", "write-offs"),
    "amort_opening": ("accumulated amortization opening", "amortization opening", "accumulated amortization - opening",
                      "amort opening", "amortization_beginning"),
    "amort_expense": ("amortization", "amortization expense", "amortization for the year", "amort expense"),
    "amort_disposals": ("amortization disposals", "accumulated amortization disposals", "amort disposals"),
    "notes": ("notes", "note", "comment", "comments"),
}


def _dec(value: Any) -> Decimal:
    """Money from a spreadsheet cell: $, thousands separators and (parentheses) negatives."""
    s = str(value if value is not None else "").replace("$", "").replace(",", "").strip()
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    return Decimal(s) if s else ZERO


def parse_csv(content: bytes) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Parse a TCA continuity spreadsheet export into line dicts. Returns (rows, errors)."""
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    headers = {h.strip().lower(): h for h in (reader.fieldnames or [])}
    columns = {
        field: next((headers[a] for a in aliases if a in headers), None)
        for field, aliases in CSV_ALIASES.items()
    }
    if columns["asset_class"] is None:
        return [], [f"No asset class column found; expected one of: {', '.join(CSV_ALIASES['asset_class'])}"]

    rows, errors = [], []
    for line_no, raw in enumerate(reader, start=2):
        asset_class = (raw.get(columns["asset_class"]) or "").strip()
        if not asset_class:
            errors.append(f"Row {line_no}: missing asset class")
            continue
        try:
            row: Dict[str, Any] = {"asset_class": asset_class}
            for field in ("cost_opening", "cost_additions", "cost_disposals",
                          "amort_opening", "amort_expense", "amort_disposals"):
                row[field] = _dec(raw.get(columns[field])) if columns[field] else ZERO
            row["notes"] = ((raw.get(columns["notes"]) or "").strip() or None) if columns["notes"] else None
        except InvalidOperation:
            errors.append(f"Row {line_no}: invalid amount")
            continue
        rows.append(row)
    return rows, errors


def _stored(line: TcaScheduleLine, field: str) -> Decimal:
    """A line's current amount, treating a not-yet-flushed column as zero."""
    value = getattr(line, field, None)
    return Decimal(str(value)) if value is not None else ZERO


def list_lines(db: Session, fiscal_year_id: int) -> List[TcaScheduleLine]:
    return list(db.scalars(
        select(TcaScheduleLine)
        .where(TcaScheduleLine.fiscal_year_id == fiscal_year_id)
        .order_by(TcaScheduleLine.sort_order, TcaScheduleLine.asset_class)
    ).all())


def replace_lines(db: Session, fiscal_year_id: int, rows: List[Dict[str, Any]], source: str = "manual") -> int:
    """Replace the year's schedule with `rows` (one per asset class). Returns the row count."""
    for existing in list_lines(db, fiscal_year_id):
        db.delete(existing)
    db.flush()
    for index, row in enumerate(rows):
        db.add(TcaScheduleLine(
            fiscal_year_id=fiscal_year_id,
            asset_class=row["asset_class"],
            sort_order=row.get("sort_order", index),
            notes=row.get("notes"),
            cost_opening=row.get("cost_opening", ZERO),
            cost_additions=row.get("cost_additions", ZERO),
            cost_disposals=row.get("cost_disposals", ZERO),
            amort_opening=row.get("amort_opening", ZERO),
            amort_expense=row.get("amort_expense", ZERO),
            amort_disposals=row.get("amort_disposals", ZERO),
            source=source,
        ))
    db.flush()
    return len(rows)


def import_csv(db: Session, fiscal_year_id: int, content: bytes, replace: bool = True) -> Tuple[int, List[str]]:
    rows, errors = parse_csv(content)
    if not rows:
        return 0, errors
    if replace:
        replace_lines(db, fiscal_year_id, rows, source="csv")
        return len(rows), errors
    # Append: merge by asset class, adding to whatever is already there
    existing = {line.asset_class.strip().lower(): line for line in list_lines(db, fiscal_year_id)}
    for row in rows:
        line = existing.get(row["asset_class"].strip().lower())
        if line is None:
            line = TcaScheduleLine(fiscal_year_id=fiscal_year_id, asset_class=row["asset_class"], source="csv")
            db.add(line)
            existing[row["asset_class"].strip().lower()] = line
        for field in ("cost_opening", "cost_additions", "cost_disposals",
                      "amort_opening", "amort_expense", "amort_disposals"):
            # A line added in this request has no column defaults applied yet, so read
            # the value through _stored() rather than assuming it is a Decimal.
            setattr(line, field, _stored(line, field) + row[field])
        if row.get("notes"):
            line.notes = row["notes"]
    db.flush()
    return len(rows), errors


def previous_year(db: Session, fy: FiscalYear) -> Optional[FiscalYear]:
    years = db.scalars(select(FiscalYear).order_by(FiscalYear.start_date)).all()
    earlier = [y for y in years if y.start_date < fy.start_date]
    return earlier[-1] if earlier else None


def apply_prior_year_openings(db: Session, fy: FiscalYear) -> Dict[str, Any]:
    """
    Carry the prior year's closing cost and accumulated amortization in as this year's
    openings, so the continuity schedule ties year over year. Asset classes that appear
    only in the prior year are created here; classes added this year keep their openings.
    """
    prior = previous_year(db, fy)
    if prior is None:
        return {"applied": 0, "created": 0, "prior_year": None, "warnings": ["No earlier fiscal year to carry forward"]}

    prior_lines = list_lines(db, prior.id)
    if not prior_lines:
        return {"applied": 0, "created": 0, "prior_year": prior.label,
                "warnings": [f"Fiscal year {prior.label} has no TCA schedule to carry forward"]}

    current = {line.asset_class.strip().lower(): line for line in list_lines(db, fy.id)}
    applied = created = 0
    for prior_line in prior_lines:
        key = prior_line.asset_class.strip().lower()
        line = current.get(key)
        if line is None:
            line = TcaScheduleLine(
                fiscal_year_id=fy.id, asset_class=prior_line.asset_class,
                sort_order=prior_line.sort_order, source="roll_forward",
            )
            db.add(line)
            current[key] = line
            created += 1
        line.cost_opening = prior_line.cost_closing
        line.amort_opening = prior_line.amort_closing
        applied += 1
    db.flush()
    return {"applied": applied, "created": created, "prior_year": prior.label, "warnings": []}


def _gl_balances(db: Session, fy: FiscalYear) -> Optional[Dict[str, Decimal]]:
    """
    Closing balances per the GL for the accounts the PSAB scheme classifies as TCA cost and
    accumulated amortization, presented the same way the schedule presents them: cost
    debit-positive, accumulated amortization positive. None when nothing is classified
    (schedule-only setups).

    The classification alone cannot decide the natural side here — accumulated
    amortization sits under `non_financial_assets` like cost does — so each bucket carries
    its own sign convention.
    """
    balances = account_balances(db, fy.id)
    if not balances:
        return None
    classes = classifications(db, resolve_scheme_id(db, "PSAB"), balances.keys())

    def closing(patterns: List[str], sign: int) -> Optional[Decimal]:
        total = ZERO
        found = False
        for account_id, balance in balances.items():
            if not match_classification(classes.get(account_id), patterns):
                continue
            found = True
            total += sign * balance.closing()
        return total if found else None

    cost = closing(COST_CLASSIFICATIONS, 1)
    amort = closing(AMORT_CLASSIFICATIONS, -1)
    if cost is None and amort is None:
        return None
    return {"cost": cost or ZERO, "amortization": amort or ZERO}


def build_schedule(db: Session, fiscal_year_id: int, layout: str = "continuity") -> Dict[str, Any]:
    """
    PS 3150 schedule in the common tabular shape. ``layout`` is "continuity" (cost and
    accumulated amortization roll forwards) or "summary" (closing cost, accumulated
    amortization and net book value only).
    """
    fy = db.get(FiscalYear, fiscal_year_id)
    if fy is None:
        raise ValueError(f"Fiscal year {fiscal_year_id} not found")
    lines = list_lines(db, fiscal_year_id)

    if layout == "summary":
        columns = [
            {"key": "cost_closing", "label": "Cost"},
            {"key": "amort_closing", "label": "Accumulated amortization"},
            {"key": "nbv_closing", "label": "Net book value"},
        ]
    else:
        columns = [
            {"key": "cost_opening", "label": "Cost — opening"},
            {"key": "cost_additions", "label": "Additions"},
            {"key": "cost_disposals", "label": "Disposals"},
            {"key": "cost_closing", "label": "Cost — closing"},
            {"key": "amort_opening", "label": "Accum. amortization — opening"},
            {"key": "amort_expense", "label": "Amortization"},
            {"key": "amort_disposals", "label": "Disposals"},
            {"key": "amort_closing", "label": "Accum. amortization — closing"},
            {"key": "nbv_opening", "label": "Net book value — opening"},
            {"key": "nbv_closing", "label": "Net book value — closing"},
        ]

    rows: List[Dict[str, Any]] = []
    totals = {c["key"]: ZERO for c in columns}
    for line in lines:
        values = {c["key"]: getattr(line, c["key"]) for c in columns}
        for key, value in values.items():
            totals[key] += Decimal(str(value))
        rows.append({
            "label": line.asset_class, "level": 0, "style": {}, "values": values,
            "text": {}, "source": line.source, "notes": line.notes,
        })
    rows.append({
        "label": "Total", "level": 0, "style": {"bold": True, "underline": "double"},
        "values": totals, "text": {},
    })

    return {
        "organization": settings.ORGANIZATION_NAME,
        "title": "Schedule of Tangible Capital Assets",
        "subtitle": f"PS 3150 — for the year ended {fy.end_date.strftime('%B')} {fy.end_date.day}, {fy.end_date.year}",
        "sheet_name": f"TCA {fy.label}",
        "number_format": {"decimals": 0, "currency_symbol": "$"},
        "layout": layout,
        "columns": columns,
        "rows": rows,
        "reconciliation": _reconciliation(db, fy, totals),
        "line_count": len(lines),
    }


def _reconciliation(db: Session, fy: FiscalYear, totals: Dict[str, Decimal]) -> Dict[str, Any]:
    """
    Compare the schedule's closing cost and accumulated amortization with the closing
    balances of the GL accounts classified as TCA cost / accumulated amortization. A
    difference is not necessarily wrong (assets under construction, a GL-only adjustment),
    so this reports rather than blocks.
    """
    gl = _gl_balances(db, fy)
    if gl is None:
        return {"available": False, "reason": "No PSAB classification for TCA cost/accumulated amortization"}

    cost_diff = Decimal(str(totals.get("cost_closing", ZERO))) - gl["cost"]
    amort_diff = Decimal(str(totals.get("amort_closing", ZERO))) - gl["amortization"]
    return {
        "available": True,
        "gl_cost": str(gl["cost"]),
        "gl_accumulated_amortization": str(gl["amortization"]),
        "schedule_cost": str(totals.get("cost_closing", ZERO)),
        "schedule_accumulated_amortization": str(totals.get("amort_closing", ZERO)),
        "cost_difference": str(cost_diff),
        "amortization_difference": str(amort_diff),
        "agrees": cost_diff == ZERO and amort_diff == ZERO,
    }
