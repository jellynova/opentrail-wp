"""Shared import parser: format detection, amount normalisation, header auto-detection."""
import csv
import io
from decimal import Decimal

import pytest

from app.services import import_parsers as ip


def to_csv_bytes(rows, headers=None):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers or list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def xlsx_bytes(*sheets, sheet_names=None):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    for i, rows in enumerate(sheets):
        ws = wb.active if i == 0 else wb.create_sheet()
        if sheet_names:
            ws.title = sheet_names[i]
        for row in rows:
            ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ---------------------------------------------------------------------------
# Plain CSV regression
# ---------------------------------------------------------------------------

def test_plain_csv_regression():
    content = to_csv_bytes(
        [{"Account": "4-100", "Debit": "100.50", "Credit": ""}, {"Account": "6-100", "Debit": "", "Credit": "25"}],
        ["Account", "Debit", "Credit"])
    fieldnames, rows = ip.load_rows(content, "tb.csv")
    assert fieldnames == ["Account", "Debit", "Credit"]
    assert rows[0] == {"Account": "4-100", "Debit": "100.50", "Credit": ""}
    assert len(rows) == 2


# ---------------------------------------------------------------------------
# Amount normalisation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("1,234.56", Decimal("1234.56")),
    ("$1,234.56", Decimal("1234.56")),
    ("CAD 1,234.56", Decimal("1234.56")),
    ("(1,234.56)", Decimal("-1234.56")),      # Sage parenthesised negative
    ("1,234.56-", Decimal("-1234.56")),       # trailing minus
    ("N/A", Decimal("0")),                    # Sage empty-amount markers
    ("-", Decimal("0")),
    ("", Decimal("0")),
    ("$", Decimal("0")),
    (None, Decimal("0")),
    (1234.56, Decimal("1234.56")),
    (50000, Decimal("50000")),
])
def test_parse_amount(raw, expected):
    assert ip.parse_amount(raw) == expected


def test_parse_amount_rejects_text():
    from decimal import InvalidOperation
    with pytest.raises(InvalidOperation):
        ip.parse_amount("twelve")


# ---------------------------------------------------------------------------
# Header-row auto-detection
# ---------------------------------------------------------------------------

def test_header_detection_skips_title_rows():
    content = b"City of Springfield\nTrial Balance 2026\n\nAccount,Debit,Credit\n4-100,100,\n"
    fieldnames, rows = ip.load_rows(content, "tb.csv")
    assert fieldnames == ["Account", "Debit", "Credit"]
    assert rows == [{"Account": "4-100", "Debit": "100", "Credit": ""}]


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------

def test_xlsx_with_title_row_and_headers():
    content = xlsx_bytes([  # sheet 1 with a title row
        ["Municipality of Opentrail"],
        [],
        ["Account", "Debit", "Credit"],
        ["4-100", 100, None],
        ["6-100", None, 25],
    ])
    fieldnames, rows = ip.load_rows(content, "tb.xlsx")
    assert fieldnames == ["Account", "Debit", "Credit"]
    assert len(rows) == 2
    assert rows[0]["Account"] == "4-100"


def test_xlsx_sheet_selection():
    content = xlsx_bytes(
        [["Account", "Debit"], ["4-100", 1]],
        [["Account", "Debit"], ["6-100", 2]],
        sheet_names=["Summary", "Detail"],
    )
    fieldnames, rows = ip.load_rows(content, "tb.xlsx")  # default: first non-empty sheet
    assert rows[0]["Account"] == "4-100"
    fieldnames, rows = ip.load_rows(content, "tb.xlsx", sheet="Detail")
    assert rows[0]["Account"] == "6-100"
    with pytest.raises(ip.ImportParseError, match="sheet 'Nope' not found"):
        ip.load_rows(content, "tb.xlsx", sheet="Nope")


# ---------------------------------------------------------------------------
# QuickBooks
# ---------------------------------------------------------------------------

def test_qb_tab_delimited_export():
    content = ("Account\tType\tDebit\tCredit\n"
               "1000 · Cash\tBank\t$1,000.00\t\n"
               "2000 · A/P\tAccounts Payable\t\t$250.50\n").encode("utf-8")
    fieldnames, rows = ip.load_rows(content, "tb.txt")
    assert fieldnames == ["Account", "Type", "Debit", "Credit"]
    mapping, mapped = ip.canonicalize_tb_rows(fieldnames, rows)
    assert mapping == {"Account": "acct_fmtd", "Debit": "period_debit", "Credit": "period_credit"}
    assert mapped[0] == {"Account": "1000 · Cash", "Debit": "$1,000.00", "Credit": ""}
    assert mapped[1]["Credit"] == "$250.50"


def test_qb_single_balance_column():
    _, rows = ip.canonicalize_tb_rows(
        ["Account", "Type", "Balance"],
        [{"Account": "1000", "Type": "Bank", "Balance": "$500.00"},
         {"Account": "2000", "Type": "AP", "Balance": "($120.00)"}])
    assert rows[0] == {"Account": "1000", "Debit": "500.00", "Credit": ""}
    # Negative balance (a credit-natured account) lands in the Credit column
    assert rows[1]["Credit"] == "120.00" and rows[1]["Debit"] == ""


def test_iif_trns_rows():
    iif = ("\t\t\t\n"
           "!TRNS\tTRNSID\tTRNSTYPE\tDATE\tACCNT\tAMOUNT\tMEMO\n"
           "!SPL\tSPLID\tTRNSTYPE\tDATE\tACCNT\tAMOUNT\n"
           "!ENDTRNS\t\n"
           "TRNS\t1\tGENERAL JOURNAL\t10/6/2026\t1000 · Cash\t-250.00\tDeposit\n"
           "TRNS\t2\tGENERAL JOURNAL\t10/6/2026\t4000 · Revenue\t250.00\tDeposit\n"
           "SPL\t1\tGENERAL JOURNAL\t10/6/2026\t4000 · Revenue\t250.00\t\n"
           "ENDTRNS\t\n").encode("utf-8")
    fieldnames, rows = ip.load_rows(iif, "journal.iif")
    assert "ACCNT" in fieldnames and "AMOUNT" in fieldnames
    assert len(rows) == 2  # SPL rows are excluded
    assert rows[0] == {"TRNSID": "1", "TRNSTYPE": "GENERAL JOURNAL", "DATE": "10/6/2026",
                       "ACCNT": "1000 · Cash", "AMOUNT": "-250.00", "MEMO": "Deposit"}
    _, mapped = ip.canonicalize_tb_rows(
        ["Account", "Amount"], [{"Account": r["ACCNT"], "Amount": r["AMOUNT"]} for r in rows])
    assert mapped[0]["Account"] == "1000 · Cash"
    assert mapped[0]["Credit"] == "250.00"  # negative amount -> credit column


# ---------------------------------------------------------------------------
# Sage
# ---------------------------------------------------------------------------

def test_sage_parenthesised_negatives_and_na():
    content = ('"Account Number","Account Name",Debit,Credit\n'
               '"4-100","Taxation","CAD 1,234.56",\n'
               '"6-100","Salaries",,"(1,234.56)"\n'
               '"6-200","Supplies",N/A,N/A\n').encode("utf-8")
    fieldnames, rows = ip.load_rows(content, "sage.csv")
    # Sage uses Account Number / Account Name — both map to the canonical account field
    mapping, mapped = ip.canonicalize_tb_rows(fieldnames, rows)
    assert mapping["Account"] == "acct_fmtd"
    assert ip.parse_amount(rows[0]["Debit"]) == Decimal("1234.56")
    assert ip.parse_amount(rows[1]["Credit"]) == Decimal("-1234.56")
    assert ip.parse_amount(rows[2]["Debit"]) == Decimal("0")


def test_sage_single_amount_column():
    content = ('"Account Number","Account Name",Amount\n'
               '"4-100","Taxation","1,000.00"\n'
               '"6-100","Salaries","(500.00)"\n').encode("utf-8")
    fieldnames, rows = ip.load_rows(content, "sage.csv")
    _, mapped = ip.canonicalize_tb_rows(fieldnames, rows)
    assert mapped[0]["Debit"] == "1000.00"
    assert mapped[1]["Credit"] == "500.00"


# ---------------------------------------------------------------------------
# Format detection and error states
# ---------------------------------------------------------------------------

def test_sniff_html_report():
    html = b"<html><body><table><tr><td>Account</td><td>Debit</td></tr>" \
           b"<tr><td>1000</td><td>50.00</td></tr></table></body></html>"
    assert ip.sniff_format("journal.html", html) == "html"
    fieldnames, rows = ip.load_rows(html, "journal.html")
    assert fieldnames == ["Account", "Debit"]
    assert rows[0]["Debit"] == "50.00"


def test_legacy_xls_rejected():
    with pytest.raises(ip.ImportParseError, match="legacy"):
        ip.load_rows(b"\xd0\xcf\x11\xe0whatever", "tb.xls")


def test_garbage_file_rejected_with_parse_error():
    with pytest.raises(ip.ImportParseError):
        ip.load_rows(b"\x00\x01\x02", "mystery.bin")


def test_canonicalize_requires_account_column():
    with pytest.raises(ip.ImportParseError, match="account column"):
        ip.canonicalize_tb_rows(["Foo", "Debit"], [{"Foo": "x", "Debit": "1"}])


# ---------------------------------------------------------------------------
# Endpoint integration: xlsx upload through the TCA import
# ---------------------------------------------------------------------------

def test_tca_endpoint_accepts_xlsx(client, auth, fy2025):
    content = xlsx_bytes([
        ["Asset register — 2026"],
        [],
        ["Asset class", "Cost opening", "Additions", "Disposals",
         "Accumulated amortization opening", "Amortization", "Amortization disposals"],
        ["Land", 1000000, None, None, None, None, None],
        ["Buildings", 2500000, 50000, None, 900000, 62500, None],
    ])
    r = client.post(
        f"/api/v1/tca/lines/import?fiscal_year_id={fy2025.id}", headers=auth("officer"),
        files={"file": ("tca.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"records_imported": 2, "errors": []}
    rows = client.get("/api/v1/tca/lines", headers=auth("viewer"),
                      params={"fiscal_year_id": fy2025.id}).json()
    by_class = {line["asset_class"]: line for line in rows}
    assert Decimal(by_class["Buildings"]["cost_additions"]) == Decimal("50000")
    assert Decimal(by_class["Buildings"]["amort_expense"]) == Decimal("62500")


def test_tca_endpoint_rejects_unreadable_file(client, auth, fy2025):
    r = client.post(
        f"/api/v1/tca/lines/import?fiscal_year_id={fy2025.id}", headers=auth("officer"),
        files={"file": ("mystery.bin", b"\x00\x01\x02\x03", "application/octet-stream")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["records_imported"] == 0 and body["errors"]
