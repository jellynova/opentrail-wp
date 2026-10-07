"""
Report rendering and export.

Every report — builder reports, working papers, budget reports — is rendered to a common
"tabular report" shape before export:

    {
      "title": str, "subtitle": str | None, "organization": str | None,
      "number_format": {"decimals": 0, "currency_symbol": "$"},
      "columns": [{"key": "cy", "label": "2025"}, ...],
      "text_columns": [{"key": "acct_fmtd", "label": "Account"}],   # optional, left of label
      "rows": [{"label": str, "level": int, "style": {...}, "values": {key: Decimal|None},
                "text": {key: str}}],
    }

export_to_excel() and export_to_pdf() accept that shape.
"""
from __future__ import annotations

import html
import io
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.report_engine import format_amount, generate


def generate_report_data(
    db: Session,
    definition: Dict[str, Any],
    fiscal_year_id: int,
    period_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Render a saved report definition (v1 or v2) for a fiscal year / period."""
    return generate(db, definition, fiscal_year_id, period_id)


def _num(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    return float(Decimal(str(v)))


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------

def export_to_excel(report: Dict[str, Any]) -> bytes:
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = (report.get("sheet_name") or report.get("title") or "Report")[:31].replace("/", "-")

    decimals = int((report.get("number_format") or {}).get("decimals", 0))
    frac = ("." + "0" * decimals) if decimals else ""
    number_format = f"#,##0{frac}_);(#,##0{frac});\"-\"_)"

    text_cols = report.get("text_columns") or []
    cols = report.get("columns") or []
    label_col = len(text_cols) + 1

    row = 1
    for heading, font in (
        (report.get("organization"), Font(bold=True, size=12)),
        (report.get("title"), Font(bold=True, size=14)),
        (report.get("subtitle"), Font(italic=True)),
    ):
        if heading:
            ws.cell(row=row, column=1, value=heading).font = font
            row += 1
    row += 1

    for i, c in enumerate(text_cols):
        ws.cell(row=row, column=i + 1, value=c["label"]).font = Font(bold=True)
    for i, c in enumerate(cols):
        cell = ws.cell(row=row, column=label_col + 1 + i, value=c["label"])
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="right")
        cell.border = Border(bottom=Side(style="thin"))
    ws.freeze_panes = ws.cell(row=row + 1, column=1)
    row += 1

    thin, double = Side(style="thin"), Side(style="double")
    for r in report.get("rows", []):
        style = r.get("style") or {}
        bold = bool(style.get("bold"))
        for i, c in enumerate(text_cols):
            ws.cell(row=row, column=i + 1, value=(r.get("text") or {}).get(c["key"]))
        label = ws.cell(row=row, column=label_col, value=r.get("label"))
        label.font = Font(bold=bold, italic=bool(style.get("italic")))
        label.alignment = Alignment(indent=int(r.get("level", 0)))
        for i, c in enumerate(cols):
            v = _num((r.get("values") or {}).get(c["key"]))
            if v is None:
                continue
            cell = ws.cell(row=row, column=label_col + 1 + i, value=v)
            cell.number_format = number_format if not c.get("percent") else "0.0\"%\""
            cell.font = Font(bold=bold)
            underline = style.get("underline")
            if underline == "single":
                cell.border = Border(top=thin)
            elif underline == "double":
                cell.border = Border(top=thin, bottom=double)
        row += 1

    for i, c in enumerate(text_cols):
        ws.column_dimensions[get_column_letter(i + 1)].width = c.get("width", 16)
    ws.column_dimensions[get_column_letter(label_col)].width = 50
    for i in range(len(cols)):
        ws.column_dimensions[get_column_letter(label_col + 1 + i)].width = 16
    ws.sheet_view.showGridLines = False
    ws.print_options.horizontalCentered = True
    ws.page_setup.fitToWidth = 1

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

PDF_CSS = """
@page { size: letter; margin: 2cm 1.8cm; @bottom-right { content: counter(page) " of " counter(pages); font-size: 8pt; color: #666; } }
body { font-family: 'Liberation Serif', 'Times New Roman', serif; font-size: 10.5pt; }
.head { text-align: center; margin-bottom: 18px; }
.org { font-size: 13pt; font-weight: bold; text-transform: uppercase; }
.title { font-size: 13pt; font-weight: bold; margin-top: 2px; }
.subtitle { font-style: italic; margin-top: 2px; }
table { width: 100%; border-collapse: collapse; }
th { text-align: right; font-weight: bold; border-bottom: 1px solid #000; padding: 2px 6px; }
th.text, td.text { text-align: left; white-space: nowrap; }
td { padding: 1.5px 6px; vertical-align: bottom; }
td.amt { text-align: right; white-space: nowrap; width: 15%; }
tr.bold td { font-weight: bold; }
tr.italic td { font-style: italic; }
tr.u-single td.amt { border-top: 1px solid #000; }
tr.u-double td.amt { border-top: 1px solid #000; border-bottom: 3px double #000; }
.meta { margin-top: 14px; font-size: 8pt; color: #666; }
"""


def report_to_html(report: Dict[str, Any]) -> str:
    esc = html.escape
    nf = report.get("number_format") or {}
    text_cols = report.get("text_columns") or []
    cols = report.get("columns") or []

    parts = ["<html><head><meta charset='utf-8'><style>", PDF_CSS, "</style></head><body><div class='head'>"]
    if report.get("organization"):
        parts.append(f"<div class='org'>{esc(report['organization'])}</div>")
    parts.append(f"<div class='title'>{esc(report.get('title') or '')}</div>")
    if report.get("subtitle"):
        parts.append(f"<div class='subtitle'>{esc(report['subtitle'])}</div>")
    parts.append("</div><table><thead><tr>")
    parts.extend(f"<th class='text'>{esc(c['label'])}</th>" for c in text_cols)
    parts.append("<th class='text'></th>")
    parts.extend(f"<th>{esc(str(c['label']))}</th>" for c in cols)
    parts.append("</tr></thead><tbody>")

    for r in report.get("rows", []):
        style = r.get("style") or {}
        classes = [k for k in ("bold", "italic") if style.get(k)]
        if style.get("underline") in ("single", "double"):
            classes.append(f"u-{style['underline']}")
        parts.append(f"<tr class='{' '.join(classes)}'>")
        for c in text_cols:
            parts.append(f"<td class='text'>{esc(str((r.get('text') or {}).get(c['key']) or ''))}</td>")
        indent = 1.2 * int(r.get("level", 0))
        parts.append(f"<td style='padding-left:{indent + 0.4:.1f}em'>{esc(r.get('label') or '')}</td>")
        for c in cols:
            v = (r.get("values") or {}).get(c["key"])
            if c.get("percent"):
                cell = "" if v is None else f"{Decimal(str(v)):.1f}%"
            else:
                cell = format_amount(None if v is None else Decimal(str(v)), nf)
            parts.append(f"<td class='amt'>{esc(cell)}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table>")
    if report.get("generated_at"):
        parts.append(f"<div class='meta'>Generated {esc(str(report['generated_at']))[:19]} UTC</div>")
    parts.append("</body></html>")
    return "".join(parts)


def export_to_pdf(report: Dict[str, Any]) -> bytes:
    try:
        from weasyprint import HTML  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("WeasyPrint is not installed") from exc
    return HTML(string=report_to_html(report)).write_pdf()


def safe_filename(name: str) -> str:
    keep = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in name).strip()
    return (keep.replace(" ", "_") or "report")[:80]


def table_rows(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Helper for converters: ensure every row has the optional keys."""
    for r in items:
        r.setdefault("level", 0)
        r.setdefault("style", {})
        r.setdefault("values", {})
    return items
