"""
Shared import parsing for accounting-software exports.

Every import endpoint (trial balance, budget lines, TCA schedule, SOFI entries)
accepts CSV plus the formats the finance team actually receives from their
accounting systems:

* Excel workbooks (.xlsx) — read with openpyxl; the first non-empty sheet is
  used unless the request names one.
* Plain CSV and tab-delimited text (.csv, .txt, .tsv).
* QuickBooks Desktop report exports — HTML journal/trial balance reports and
  tab-delimited .txt / .iif files (TRNS/TRNSP journal rows).
* QuickBooks Online / Sage 50 CSV — with parenthesised negatives, currency
  symbols, thousands separators and 'N/A' cells.

Everything is normalised to the same shape: (fieldnames, rows) where rows are
dicts of strings keyed by the source file's own header names, with the header
row auto-detected (some exports carry title rows above the headers). Amounts
go through parse_amount() so callers only ever see Decimals.

The parser is deterministic: no locale awareness, no inference beyond the
documented rules, and the first matching column/header always wins.
"""
from __future__ import annotations

import csv
import html as html_mod
import io
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Sequence, Tuple

ZERO = Decimal("0")

# Cells that mean "no amount" in Sage / spreadsheet exports.
EMPTY_CELLS = {"", "-", "--", "—", "–", "n/a", "na", "nil", "null", "none", "tbd"}

# Currency markers stripped before Decimal() — Sage writes "CAD 1,234.56",
# QuickBooks writes "$1,234.56".
_CURRENCY_RE = re.compile(r"(?i)\b(?:cad|usd|aud|nzd)\b|[$€£¥]")

# Words that identify a header row above data (title rows rarely contain them).
_HEADER_KEYWORDS = (
    "account", "acct", "g/l", "gl ", "name", "debit", "credit", "dr", "cr",
    "amount", "balance", "net", "total", "date", "class", "type", "memo",
    "description", "notes", "vendor", "supplier", "employee", "payee", "agreement",
    "cost", "amort", "opening", "additions", "disposals", "budget", "position",
    "expenses", "remuneration", "elected", "split", "accnt", "num", "no",
)

_NUM_RE = re.compile(r"^[\s$€£¥\-+(]*[\d,]+(\.\d+)?[\s)\-]*$")

# Canonical column-name variants (compared case-insensitively after stripping).
ACCOUNT_VARIANTS = (
    "account", "account name", "account number", "account no", "acct", "acct no",
    "acct_fmtd", "g/l account", "gl account", "g/l", "accnt", "full name",
    "account description",
)
# Debit/Credit columns that belong to the *current* period (not opening/YTD).
DEBIT_VARIANTS = ("debit", "debits", "debit amount", "dr", "period debit", "dr amount")
CREDIT_VARIANTS = ("credit", "credits", "credit amount", "cr", "period credit", "cr amount")
# A single signed-amount column.
AMOUNT_VARIANTS = ("amount", "balance", "net", "net amount", "net change", "total")


class ImportParseError(ValueError):
    """The uploaded file could not be interpreted as any supported format."""


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def sniff_format(filename: str, content: bytes) -> str:
    """Classify an upload by extension plus content sniffing (magic bytes)."""
    name = (filename or "").lower()
    if content[:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"):
        if name.endswith((".xlsx", ".xlsm")):
            return "xlsx"
        return "xlsx"  # a zip container with a spreadsheet-y name is still Excel
    if name.endswith((".xlsx", ".xlsm")):
        return "xlsx"
    if name.endswith(".xls"):
        return "xls"  # legacy binary Excel — not supported (see load_rows)
    head = content[:8192]
    stripped = head.lstrip(b"\xef\xbb\xbf \t\r\n")
    if stripped.startswith(b"!") or name.endswith(".iif"):
        return "iif"
    low = head.lower()
    if b"<table" in low or low.startswith(b"<!doctype html") or b"<html" in low:
        return "html"
    first_line = stripped.split(b"\n", 1)[0]
    tabs, commas = first_line.count(b"\t"), first_line.count(b",")
    if name.endswith((".txt", ".tsv")) or (tabs > commas and tabs >= 1):
        return "tsv"
    return "csv"


def decode(content: bytes) -> str:
    """UTF-8 (with BOM) first, Windows-1252 as the fallback for QB/Sage exports."""
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("cp1252", errors="replace")


# ---------------------------------------------------------------------------
# Amount normalisation
# ---------------------------------------------------------------------------

def parse_amount(value: Any) -> Decimal:
    """
    Normalise a spreadsheet/export cell to Decimal.

    Handles QuickBooks/Sage conventions: currency symbols ($, CAD), comma
    thousands separators, parentheses for negatives ((1,234.56) = -1234.56),
    trailing-minus negatives, and empty/'N/A'/'-' cells treated as zero.
    Raises InvalidOperation for genuinely unparseable text.
    """
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return Decimal(int(value))
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    s = str(value).strip()
    if s.lower() in EMPTY_CELLS:
        return ZERO
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1].strip()
    if s.endswith("-"):  # accounting trailing minus
        negative, s = True, s[:-1].strip()
    s = _CURRENCY_RE.sub("", s)
    s = s.replace(",", "").replace(" ", "").strip()
    if not s:
        return ZERO
    if s in ("-",):
        return ZERO
    try:
        amount = Decimal(s)
    except InvalidOperation:
        raise InvalidOperation(f"cannot parse amount from {value!r}") from None
    return -amount if negative else amount


# ---------------------------------------------------------------------------
# Header-row detection and grids
# ---------------------------------------------------------------------------

def _is_numeric_cell(cell: str) -> bool:
    return bool(cell) and bool(_NUM_RE.match(cell))


def _looks_like_header(cells: Sequence[str]) -> bool:
    """A header row: >=2 filled cells, none numeric, at least one known column word."""
    filled = [c.strip() for c in cells if c and c.strip()]
    if len(filled) < 2:
        return False
    if any(_is_numeric_cell(c) for c in filled):
        return False
    joined = " ".join(filled).lower()
    return any(keyword in joined for keyword in _HEADER_KEYWORDS)


def find_header_row(grid: Sequence[Sequence[Any]], max_scan: int = 25) -> int:
    """Index of the first row that plausibly names columns (skips title rows)."""
    for i, row in enumerate(grid[:max_scan]):
        cells = [str(c) if c is not None else "" for c in row]
        if _looks_like_header(cells):
            return i
    # Fall back to the first row with two or more text cells.
    for i, row in enumerate(grid[:max_scan]):
        cells = [str(c) if c is not None else "" for c in row]
        filled = [c for c in cells if c.strip()]
        if len(filled) >= 2 and not any(_is_numeric_cell(c) for c in filled):
            return i
    return 0


def _cell_str(value: Any) -> str:
    """Stringify a spreadsheet cell without float noise (50000.0 -> '50000')."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        text = format(value, ".10g")
        return text
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value).strip()


def _grid_from_xlsx(content: bytes, sheet: Optional[str]) -> List[List[str]]:
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - openpyxl is a pinned dep
        raise ImportParseError("Excel support is not installed") from exc
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception as exc:
        raise ImportParseError(f"could not read Excel workbook: {exc}") from exc
    try:
        if sheet:
            if sheet not in workbook.sheetnames:
                raise ImportParseError(f"sheet '{sheet}' not found in workbook "
                                       f"(sheets: {', '.join(workbook.sheetnames)})")
            worksheet = workbook[sheet]
        else:
            # First sheet with any non-empty cell.
            worksheet = None
            for candidate in workbook.worksheets:
                if any(cell.value is not None and str(cell.value).strip() != ""
                       for row in candidate.iter_rows(max_row=50) for cell in row):
                    worksheet = candidate
                    break
            worksheet = worksheet or (workbook.worksheets[0] if workbook.worksheets else None)
        if worksheet is None:
            raise ImportParseError("workbook has no sheets")
        grid: List[List[str]] = []
        for row in worksheet.iter_rows(values_only=True):
            grid.append([_cell_str(v) for v in row])
        return grid
    finally:
        workbook.close()


_TAG_RE = re.compile(r"<[^>]+>")
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)


def _grid_from_html(content: bytes) -> List[List[str]]:
    """Rows of the first <table> in a QuickBooks Desktop HTML report export."""
    text = decode(content)
    table = re.search(r"<table.*?>(.*)</table>", text, re.IGNORECASE | re.DOTALL)
    if not table:
        raise ImportParseError("no table found in HTML export")
    grid: List[List[str]] = []
    for row_match in _ROW_RE.finditer(table.group(1)):
        cells = []
        for cell_match in _CELL_RE.finditer(row_match.group(1)):
            cell = _TAG_RE.sub("", cell_match.group(1))
            cells.append(html_mod.unescape(cell).replace("\xa0", " ").strip())
        grid.append(cells)
    if not grid:
        raise ImportParseError("no rows found in HTML export")
    return grid


def _grid_from_delimited(text: str, delimiter: str) -> List[List[str]]:
    return [list(row) for row in csv.reader(io.StringIO(text), delimiter=delimiter)]


def _load_iif(text: str) -> Tuple[List[str], List[Dict[str, str]]]:
    """
    QuickBooks IIF: tab-delimited with header lines starting with '!'.
    Journal rows live in the TRNS / TRNSP sections (!TRNS defines the columns,
    TRNS lines are data); other sections (SPL, etc.) are ignored.
    """
    headers: Dict[str, List[str]] = {}
    rows: List[Dict[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")
        if not line.strip():
            continue
        fields = line.split("\t")
        if fields[0].startswith("!"):
            section = fields[0][1:].strip().upper()
            headers[section] = [f.strip() for f in fields[1:]]
            continue
        section = fields[0].strip().upper()
        if section not in ("TRNS", "TRNSP"):
            continue
        names = headers.get(section)
        if not names:
            raise ImportParseError(f"IIF file has {section} rows but no !{section} header line")
        row = {name: (fields[i + 1].strip() if i + 1 < len(fields) else "") for i, name in enumerate(names)}
        rows.append(row)
    if not rows:
        raise ImportParseError("no TRNS/TRNSP journal rows found in IIF file")
    fieldnames = list(dict.fromkeys(f for h in headers.values() for f in h))
    return fieldnames, rows


def load_rows(content: bytes, filename: str = "", sheet: Optional[str] = None
              ) -> Tuple[List[str], List[Dict[str, str]]]:
    """
    Parse any supported upload into (fieldnames, rows).

    fieldnames keeps the source header names (like csv.DictReader.fieldnames);
    rows are dicts keyed by those names with stripped string values. Blank rows
    are dropped and the header row is auto-detected (title rows are skipped).
    """
    if not content:
        raise ImportParseError("the file is empty")
    kind = sniff_format(filename, content)
    if kind == "xls":
        raise ImportParseError("legacy .xls files are not supported; save as .xlsx or CSV")

    if kind == "iif":
        fieldnames, rows = _load_iif(decode(content))
        return fieldnames, [r for r in rows if any(r.values())]

    if kind == "xlsx":
        grid = _grid_from_xlsx(content, sheet)
    elif kind == "html":
        grid = _grid_from_html(content)
    else:
        text = decode(content)
        if kind == "tsv":
            grid = _grid_from_delimited(text, "\t")
        else:
            grid = _grid_from_delimited(text, ",")

    grid = [row for row in grid if any(cell.strip() for cell in row)]
    if not grid:
        raise ImportParseError("the file has no data rows")
    header_index = find_header_row(grid)
    raw_headers = grid[header_index]
    fieldnames: List[str] = []
    for i, cell in enumerate(raw_headers):
        name = cell.strip() or f"Column {i + 1}"
        fieldnames.append(name)
    rows: List[Dict[str, str]] = []
    for grid_row in grid[header_index + 1:]:
        row = {name: (grid_row[i].strip() if i < len(grid_row) else "")
               for i, name in enumerate(fieldnames)}
        if any(row.values()):
            rows.append(row)
    if not rows:
        raise ImportParseError("no data rows found below the header row")
    return fieldnames, rows


def normalise_to_csv(content: bytes, filename: str = "", sheet: Optional[str] = None) -> bytes:
    """
    Convert any supported non-CSV upload (xlsx, tab-delimited, IIF, HTML) into plain
    CSV with the source header names, for the per-domain CSV importers.
    """
    fieldnames, rows = load_rows(content, filename, sheet)
    return to_csv_bytes(fieldnames, rows)


# ---------------------------------------------------------------------------
# Canonical column mapping (trial balance auto-detection)
# ---------------------------------------------------------------------------

def to_csv_bytes(fieldnames: Sequence[str], rows: List[Dict[str, str]]) -> bytes:
    """Serialise normalised rows back to CSV bytes for the existing importers."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(fieldnames), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _find_column(fieldnames: Sequence[str], variants: Sequence[str]) -> Optional[str]:
    lowered = {name.strip().lower(): name for name in fieldnames}
    for variant in variants:
        if variant in lowered:
            return lowered[variant]
    # Substring fallback so 'Debit Amount (period)' style headers still match.
    for variant in variants:
        for lower, original in lowered.items():
            if variant in lower:
                return original
    return None


def canonicalize_tb_rows(fieldnames: Sequence[str], rows: List[Dict[str, str]]
                         ) -> Tuple[Dict[str, str], List[Dict[str, str]]]:
    """
    Map QuickBooks/Sage-style headers onto the canonical trial balance layout.

    Returns (mapping, rows) where mapping uses the canonical header names the
    importer expects, e.g. {"Account": "acct_fmtd", "Debit": "period_debit",
    "Credit": "period_credit"}. With only a signed Amount/Balance column,
    rows are split into Debit/Credit by sign (positive = debit).
    """
    account = _find_column(fieldnames, ACCOUNT_VARIANTS)
    debit = _find_column(fieldnames, DEBIT_VARIANTS)
    credit = _find_column(fieldnames, CREDIT_VARIANTS)
    amount = _find_column(fieldnames, AMOUNT_VARIANTS)
    if account is None:
        raise ImportParseError(
            "no account column found; expected one of: " + ", ".join(ACCOUNT_VARIANTS)
        )

    mapping: Dict[str, str] = {"Account": "acct_fmtd"}
    out: List[Dict[str, str]] = []
    if debit and credit:
        mapping["Debit"], mapping["Credit"] = "period_debit", "period_credit"
        for row in rows:
            out.append({"Account": row.get(account, ""), "Debit": row.get(debit, ""),
                        "Credit": row.get(credit, "")})
    elif amount:
        # Single signed-amount column: positive is a debit, negative a credit.
        mapping["Debit"], mapping["Credit"] = "period_debit", "period_credit"
        for row in rows:
            value = parse_amount(row.get(amount, ""))
            out.append({"Account": row.get(account, ""),
                        "Debit": str(value) if value > 0 else "",
                        "Credit": str(-value) if value < 0 else ""})
    else:
        raise ImportParseError(
            "no amount columns found; expected Debit/Credit columns or a single Amount/Balance column"
        )
    return mapping, out
