"""
Statement of Financial Information schedules (PLAN §5.2, LGDE/SOFI).

* Schedule of supplier payments — suppliers paid more than the threshold (default
  $25,000) listed individually, plus a consolidated total for all others.
* Schedule of employee remuneration and expenses — elected officials listed individually
  regardless of amount; employees whose remuneration exceeds the threshold (default
  $75,000) listed individually; a consolidated total for all other employees.
* Schedule of guarantee and indemnity agreements — every agreement listed.

Each schedule is returned in the common tabular shape (see report_generator) so it can be
exported to Excel/PDF.
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
from app.models.sofi import SofiEntry

SCHEDULE_TYPES = ("supplier_payment", "employee_remuneration", "guarantee_indemnity")
DEFAULT_THRESHOLDS = {"supplier_payment": Decimal("25000"), "employee_remuneration": Decimal("75000")}
ZERO = Decimal("0")

# Accepted CSV header names (case-insensitive) for each field.
CSV_ALIASES = {
    "name": ("name", "supplier", "vendor", "vendor name", "supplier name", "employee", "employee name", "payee",
             "agreement"),
    "amount": ("amount", "total", "payments", "remuneration", "salary", "gross", "guarantee amount"),
    "expenses": ("expenses", "expense"),
    "position": ("position", "title", "office"),
    "is_elected_official": ("elected", "elected official", "is_elected_official"),
    "description": ("description", "notes", "details"),
}


def _dec(value: Any) -> Decimal:
    s = str(value or "").replace("$", "").replace(",", "").strip()
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    return Decimal(s) if s else ZERO


def parse_csv(content: bytes) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Parse a CSV export into entry dicts. Returns (rows, errors)."""
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    headers = {h.strip().lower(): h for h in (reader.fieldnames or [])}
    columns = {field: next((headers[a] for a in aliases if a in headers), None) for field, aliases in CSV_ALIASES.items()}
    if columns["name"] is None:
        return [], [f"No name column found; expected one of: {', '.join(CSV_ALIASES['name'])}"]

    rows, errors = [], []
    for line_no, raw in enumerate(reader, start=2):
        name = (raw.get(columns["name"]) or "").strip()
        if not name:
            errors.append(f"Row {line_no}: missing name")
            continue
        try:
            row = {
                "name": name,
                "amount": _dec(raw.get(columns["amount"])) if columns["amount"] else ZERO,
                "expenses": _dec(raw.get(columns["expenses"])) if columns["expenses"] else ZERO,
                "position": (raw.get(columns["position"]) or "").strip() or None if columns["position"] else None,
                "description": (raw.get(columns["description"]) or "").strip() or None if columns["description"] else None,
                "is_elected_official": str(raw.get(columns["is_elected_official"]) or "").strip().lower()
                in ("1", "y", "yes", "true", "x") if columns["is_elected_official"] else False,
            }
        except InvalidOperation:
            errors.append(f"Row {line_no}: invalid amount")
            continue
        rows.append(row)
    return rows, errors


def import_entries(db: Session, fiscal_year_id: int, schedule_type: str, content: bytes,
                   replace: bool = True) -> Tuple[int, List[str]]:
    rows, errors = parse_csv(content)
    if replace and rows:
        for e in db.scalars(select(SofiEntry).where(
            SofiEntry.fiscal_year_id == fiscal_year_id, SofiEntry.schedule_type == schedule_type
        )).all():
            db.delete(e)
    for r in rows:
        db.add(SofiEntry(fiscal_year_id=fiscal_year_id, schedule_type=schedule_type, source="csv", **r))
    db.commit()
    return len(rows), errors


def _entries(db: Session, fiscal_year_id: int, schedule_type: str) -> List[SofiEntry]:
    return db.scalars(select(SofiEntry).where(
        SofiEntry.fiscal_year_id == fiscal_year_id, SofiEntry.schedule_type == schedule_type
    )).all()


def _row(label: str, values: Dict[str, Any], text: Optional[Dict[str, Any]] = None, **style) -> Dict[str, Any]:
    return {"label": label, "level": 0, "style": style, "values": values, "text": text or {}}


def _header(fy: FiscalYear, title: str) -> Dict[str, Any]:
    return {"organization": settings.ORGANIZATION_NAME, "title": title,
            "subtitle": f"For the year ended {fy.end_date.strftime('%B')} {fy.end_date.day}, {fy.end_date.year}",
            "number_format": {"decimals": 2, "currency_symbol": "$"}}


def supplier_schedule(db: Session, fy: FiscalYear, threshold: Decimal) -> Dict[str, Any]:
    totals: Dict[str, Dict[str, Any]] = {}
    for e in _entries(db, fy.id, "supplier_payment"):
        key = " ".join(e.name.split()).upper()  # payments to the same supplier aggregate
        t = totals.setdefault(key, {"name": " ".join(e.name.split()), "amount": ZERO})
        t["amount"] += Decimal(str(e.amount))

    listed = sorted((t for t in totals.values() if t["amount"] > threshold), key=lambda t: t["name"].upper())
    listed_total = sum((t["amount"] for t in listed), ZERO)
    others = [t for t in totals.values() if t["amount"] <= threshold]
    other_total = sum((t["amount"] for t in others), ZERO)

    rows = [_row(t["name"], {"amount": t["amount"]}) for t in listed]
    rows += [
        _row(f"Total of suppliers who received more than ${threshold:,.0f}", {"amount": listed_total},
             bold=True, underline="single"),
        _row(f"Consolidated total of payments to suppliers who received ${threshold:,.0f} or less "
             f"({len(others)} suppliers)", {"amount": other_total}),
        _row("Total payments to suppliers", {"amount": listed_total + other_total}, bold=True, underline="double"),
    ]
    return {**_header(fy, "Schedule of Payments to Suppliers for Goods and Services"),
            "columns": [{"key": "amount", "label": "Amount"}], "rows": rows,
            "summary": {"threshold": threshold, "suppliers_listed": len(listed), "suppliers_consolidated": len(others),
                        "total": listed_total + other_total}}


def remuneration_schedule(db: Session, fy: FiscalYear, threshold: Decimal) -> Dict[str, Any]:
    entries = _entries(db, fy.id, "employee_remuneration")
    elected = sorted((e for e in entries if e.is_elected_official), key=lambda e: e.name.upper())
    staff = [e for e in entries if not e.is_elected_official]
    listed = sorted((e for e in staff if Decimal(str(e.amount)) > threshold), key=lambda e: e.name.upper())
    others = [e for e in staff if Decimal(str(e.amount)) <= threshold]

    def vals(rem, exp):
        return {"remuneration": rem, "expenses": exp}

    def total(items):
        return (sum((Decimal(str(e.amount)) for e in items), ZERO), sum((Decimal(str(e.expenses)) for e in items), ZERO))

    rows: List[Dict[str, Any]] = [_row("Elected officials", {}, bold=True)]
    rows += [_row(e.name, vals(Decimal(str(e.amount)), Decimal(str(e.expenses))), {"position": e.position or ""})
             for e in elected]
    et = total(elected)
    rows.append(_row("Total elected officials", vals(*et), bold=True, underline="single"))
    rows.append(_row(f"Employees with remuneration over ${threshold:,.0f}", {}, bold=True))
    rows += [_row(e.name, vals(Decimal(str(e.amount)), Decimal(str(e.expenses))), {"position": e.position or ""})
             for e in listed]
    lt, ot = total(listed), total(others)
    rows.append(_row(f"Total employees over ${threshold:,.0f}", vals(*lt), bold=True, underline="single"))
    rows.append(_row(f"Consolidated total of other employees with remuneration of ${threshold:,.0f} or less "
                     f"({len(others)} employees)", vals(*ot)))
    rows.append(_row("Total remuneration and expenses", vals(et[0] + lt[0] + ot[0], et[1] + lt[1] + ot[1]),
                     bold=True, underline="double"))
    return {**_header(fy, "Schedule of Remuneration and Expenses"),
            "text_columns": [{"key": "position", "label": "Position", "width": 24}],
            "columns": [{"key": "remuneration", "label": "Remuneration"}, {"key": "expenses", "label": "Expenses"}],
            "rows": rows,
            "summary": {"threshold": threshold, "elected_officials": len(elected), "employees_listed": len(listed),
                        "employees_consolidated": len(others)}}


def guarantee_schedule(db: Session, fy: FiscalYear) -> Dict[str, Any]:
    entries = sorted(_entries(db, fy.id, "guarantee_indemnity"), key=lambda e: e.name.upper())
    if entries:
        rows = [_row(e.name, {"amount": Decimal(str(e.amount)) or None}, {"description": e.description or ""})
                for e in entries]
    else:
        rows = [_row(f"{settings.ORGANIZATION_NAME} has not given any guarantees or indemnities under the "
                     "Guarantees and Indemnities Regulation.", {})]
    return {**_header(fy, "Schedule of Guarantee and Indemnity Agreements"),
            "text_columns": [{"key": "description", "label": "Description", "width": 40}],
            "columns": [{"key": "amount", "label": "Amount"}], "rows": rows,
            "summary": {"agreements": len(entries)}}


def build_schedule(db: Session, fiscal_year_id: int, schedule_type: str,
                   threshold: Optional[Decimal] = None) -> Dict[str, Any]:
    fy = db.get(FiscalYear, fiscal_year_id)
    if fy is None:
        raise ValueError(f"Fiscal year {fiscal_year_id} not found")
    if schedule_type == "supplier_payment":
        return supplier_schedule(db, fy, threshold or DEFAULT_THRESHOLDS[schedule_type])
    if schedule_type == "employee_remuneration":
        return remuneration_schedule(db, fy, threshold or DEFAULT_THRESHOLDS[schedule_type])
    if schedule_type == "guarantee_indemnity":
        return guarantee_schedule(db, fy)
    raise ValueError(f"Unknown schedule type '{schedule_type}'")
