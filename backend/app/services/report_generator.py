"""
Report generator service.

Implements:
  - ReportDefinition Pydantic model (the JSON config stored in Report.definition)
  - generate_report_data() — renders report data from the DB
  - export_to_excel() — produces an xlsx bytes payload
  - export_to_pdf() — produces a PDF bytes payload via WeasyPrint
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.mapping import AccountClassification, MappingScheme
from app.models.period import FiscalYear, Period
from app.models.trial_balance import TrialBalanceEntry
from app.models.journal_entry import JournalEntry, JournalLine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Report definition schema
# ---------------------------------------------------------------------------

class ReportSection(BaseModel):
    """A section within a report (e.g. 'Revenue', 'Expenses')."""

    title: str
    scheme_id: int  # which mapping scheme to use for this section
    classification_values: List[str]  # which classification_value rows to include
    subtotal_label: Optional[str] = None
    negate: bool = False  # if True, multiply amounts by -1 (e.g. for expenses in surplus statement)
    sort_order: int = 0


class ReportDefinition(BaseModel):
    """
    The full JSON definition for a report stored in Report.definition.

    This flexible structure allows finance_admin to configure custom report shapes
    without code changes. The sections list drives the line groupings.
    """

    title: str
    subtitle: Optional[str] = None
    report_type: str  # psab_sfp / psab_so / custom / etc.
    comparative: bool = False  # include prior year column
    sections: List[ReportSection] = []
    include_account_detail: bool = False  # if True, show individual account lines; else aggregated by section
    show_zero_balances: bool = False
    currency_symbol: str = "$"


# ---------------------------------------------------------------------------
# Core report data generation
# ---------------------------------------------------------------------------

def generate_report_data(
    db: Session,
    report_def: ReportDefinition,
    fiscal_year_id: int,
    period_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Generate report data from the database based on a ReportDefinition.

    Returns a dict with:
      - title, subtitle, fiscal_year_id, period_id, generated_at
      - sections: list of section dicts with line items and subtotals
      - grand_total (for single-total reports)
    """
    # Resolve period — if not given, use all periods in the fiscal year
    if period_id:
        target_period_ids = [period_id]
    else:
        periods = db.scalars(
            select(Period).where(Period.fiscal_year_id == fiscal_year_id)
        ).all()
        target_period_ids = [p.id for p in periods]

    # Load TB entries for the relevant periods
    tb_entries: List[TrialBalanceEntry] = []
    if target_period_ids:
        tb_entries = db.scalars(
            select(TrialBalanceEntry).where(
                TrialBalanceEntry.period_id.in_(target_period_ids)
            )
        ).all()

    # Load posted/approved journal adjustments for these periods
    adj_lines: List[JournalLine] = []
    if target_period_ids:
        stmt = (
            select(JournalLine)
            .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
            .where(
                and_(
                    JournalEntry.period_id.in_(target_period_ids),
                    JournalEntry.status.in_(["posted", "approved"]),
                )
            )
        )
        adj_lines = db.scalars(stmt).all()

    # Net balance by account_id (ytd_credit - ytd_debit + adj_credit - adj_debit)
    ytd_by_acct: Dict[int, Decimal] = {}
    for entry in tb_entries:
        acct_id = entry.account_id
        net = Decimal(str(entry.ytd_credit)) - Decimal(str(entry.ytd_debit))
        ytd_by_acct[acct_id] = ytd_by_acct.get(acct_id, Decimal("0")) + net

    for line in adj_lines:
        acct_id = line.account_id
        net = Decimal(str(line.credit)) - Decimal(str(line.debit))
        ytd_by_acct[acct_id] = ytd_by_acct.get(acct_id, Decimal("0")) + net

    # Load account metadata for all accounts that have balances
    all_acct_ids = set(ytd_by_acct.keys())
    accounts = db.scalars(select(Account).where(Account.id.in_(all_acct_ids))).all()
    account_map = {a.id: a for a in accounts}

    # Load classifications for all relevant scheme IDs
    scheme_ids = list({s.scheme_id for s in report_def.sections})
    classifications: List[AccountClassification] = []
    if scheme_ids and all_acct_ids:
        classifications = db.scalars(
            select(AccountClassification).where(
                and_(
                    AccountClassification.scheme_id.in_(scheme_ids),
                    AccountClassification.account_id.in_(all_acct_ids),
                )
            )
        ).all()

    # Build classification lookup: (account_id, scheme_id) -> classification_value
    classification_map: Dict[tuple, str] = {
        (c.account_id, c.scheme_id): c.classification_value for c in classifications
    }

    # Build report sections
    output_sections = []
    grand_total = Decimal("0")

    for section in sorted(report_def.sections, key=lambda s: s.sort_order):
        lines = []
        section_total = Decimal("0")

        for acct_id, balance in ytd_by_acct.items():
            cv = classification_map.get((acct_id, section.scheme_id))
            if cv not in section.classification_values:
                continue

            display_balance = balance * (-1 if section.negate else 1)

            if not report_def.show_zero_balances and display_balance == Decimal("0"):
                continue

            account = account_map.get(acct_id)
            if account:
                lines.append(
                    {
                        "account_id": acct_id,
                        "acct_fmtd": account.acct_fmtd,
                        "description": account.description,
                        "amount": display_balance,
                    }
                )
            section_total += display_balance

        lines.sort(key=lambda x: x["acct_fmtd"])

        output_sections.append(
            {
                "title": section.title,
                "lines": lines if report_def.include_account_detail else [],
                "subtotal": section_total,
                "subtotal_label": section.subtotal_label or f"Total {section.title}",
            }
        )
        grand_total += section_total

    return {
        "title": report_def.title,
        "subtitle": report_def.subtitle,
        "fiscal_year_id": fiscal_year_id,
        "period_id": period_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sections": output_sections,
        "grand_total": grand_total,
        "currency_symbol": report_def.currency_symbol,
    }


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------

def export_to_excel(report_data: Dict[str, Any]) -> bytes:
    """
    Export report data to an xlsx file and return the bytes.
    Uses openpyxl.
    """
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, numbers
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = report_data.get("title", "Report")[:31]  # Excel sheet name limit

    currency_sym = report_data.get("currency_symbol", "$")
    number_format = f'#{currency_sym}##,##0.00_);[Red](#{currency_sym}##,##0.00)'

    row = 1

    # Title
    ws.cell(row=row, column=1, value=report_data.get("title", ""))
    ws.cell(row=row, column=1).font = Font(bold=True, size=14)
    row += 1

    if report_data.get("subtitle"):
        ws.cell(row=row, column=1, value=report_data["subtitle"])
        ws.cell(row=row, column=1).font = Font(italic=True)
        row += 1

    ws.cell(row=row, column=1, value=f"Generated: {report_data.get('generated_at', '')}")
    row += 2

    for section in report_data.get("sections", []):
        # Section header
        ws.cell(row=row, column=1, value=section["title"])
        ws.cell(row=row, column=1).font = Font(bold=True, underline="single")
        row += 1

        # Account detail lines
        for line in section.get("lines", []):
            ws.cell(row=row, column=1, value=line.get("acct_fmtd", ""))
            ws.cell(row=row, column=2, value=line.get("description", ""))
            amount_cell = ws.cell(row=row, column=3, value=float(line.get("amount", 0)))
            amount_cell.number_format = number_format
            row += 1

        # Subtotal
        subtotal_cell = ws.cell(row=row, column=3, value=float(section.get("subtotal", 0)))
        subtotal_cell.number_format = number_format
        ws.cell(row=row, column=2, value=section.get("subtotal_label", ""))
        ws.cell(row=row, column=2).font = Font(bold=True)
        subtotal_cell.font = Font(bold=True)
        row += 2

    # Grand total
    ws.cell(row=row, column=2, value="Grand Total")
    ws.cell(row=row, column=2).font = Font(bold=True, size=11)
    gt_cell = ws.cell(row=row, column=3, value=float(report_data.get("grand_total", 0)))
    gt_cell.number_format = number_format
    gt_cell.font = Font(bold=True, size=11)

    # Auto-size columns (approx)
    for col_idx in range(1, 4):
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = [20, 45, 18][col_idx - 1]

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------

def export_to_pdf(report_data: Dict[str, Any]) -> bytes:
    """
    Export report data to PDF via WeasyPrint.
    Builds a minimal HTML representation of the report and renders it.
    """
    try:
        from weasyprint import HTML  # type: ignore
    except ImportError:
        raise RuntimeError("WeasyPrint is not installed. Add 'weasyprint' to requirements.txt.")

    currency_sym = report_data.get("currency_symbol", "$")

    def fmt_amount(val: Any) -> str:
        try:
            d = Decimal(str(val))
            if d < 0:
                return f"({currency_sym}{abs(d):,.2f})"
            return f"{currency_sym}{d:,.2f}"
        except Exception:
            return str(val)

    html_parts = [
        "<html><head><style>",
        "body { font-family: Arial, sans-serif; font-size: 11pt; margin: 40px; }",
        "h1 { font-size: 16pt; margin-bottom: 4px; }",
        "h2 { font-size: 12pt; text-decoration: underline; margin-top: 20px; margin-bottom: 4px; }",
        "table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }",
        "td { padding: 2px 6px; }",
        ".amount { text-align: right; }",
        ".subtotal td { font-weight: bold; border-top: 1px solid #333; }",
        ".grand-total td { font-weight: bold; font-size: 12pt; border-top: 2px solid #000; border-bottom: 2px solid #000; }",
        ".meta { color: #666; font-size: 9pt; margin-bottom: 20px; }",
        "</style></head><body>",
        f"<h1>{report_data.get('title', 'Financial Report')}</h1>",
    ]

    if report_data.get("subtitle"):
        html_parts.append(f"<p><em>{report_data['subtitle']}</em></p>")

    html_parts.append(f"<p class='meta'>Generated: {report_data.get('generated_at', '')}</p>")

    for section in report_data.get("sections", []):
        html_parts.append(f"<h2>{section['title']}</h2><table>")

        for line in section.get("lines", []):
            html_parts.append(
                f"<tr><td>{line.get('acct_fmtd', '')}</td>"
                f"<td>{line.get('description', '') or ''}</td>"
                f"<td class='amount'>{fmt_amount(line.get('amount', 0))}</td></tr>"
            )

        html_parts.append(
            f"<tr class='subtotal'><td></td>"
            f"<td>{section.get('subtotal_label', 'Total')}</td>"
            f"<td class='amount'>{fmt_amount(section.get('subtotal', 0))}</td></tr>"
        )
        html_parts.append("</table>")

    html_parts.append(
        f"<table><tr class='grand-total'><td></td>"
        f"<td>Grand Total</td>"
        f"<td class='amount'>{fmt_amount(report_data.get('grand_total', 0))}</td></tr></table>"
    )
    html_parts.append("</body></html>")

    html_string = "\n".join(html_parts)
    pdf_bytes = HTML(string=html_string).write_pdf()
    return pdf_bytes
