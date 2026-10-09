"""
Caseware-style explicit column mapping: /imports/preview plus column_map on the
four import endpoints, and regression that the no-mapping auto-detect behaviour
is unchanged.
"""
import csv
import io
import json
from decimal import Decimal

import pytest

from app.services import import_parsers as ip
from tests.conftest import make_account, period_of


def to_csv(rows, headers=None):
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
# Parser: column reference normalisation and map application
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spec,expected", [
    (0, 0), (3, 3), ("0", 0), ("12", 12),
    ("A", 0), ("B", 1), ("Z", 25), ("AA", 26), ("BA", 52),
])
def test_column_index_formats(spec, expected):
    assert ip.column_index(spec) == expected


def test_column_index_rejects_junk():
    with pytest.raises(ip.ImportMappingError):
        ip.column_index("1x")
    with pytest.raises(ip.ImportMappingError):
        ip.column_index(-1)
    with pytest.raises(ip.ImportMappingError):
        ip.column_index(None)


def test_apply_column_map_letters_and_index_agree():
    grid = [["code", "name", "amt"], ["4-100", "Taxation", "100"], ["6-100", "Salaries", ""]]
    fields, by_letter = ip.apply_column_map(grid, 0, {"account_code": "A", "account_name": "B", "debit": "C"})
    _, by_index = ip.apply_column_map(grid, 0, {"account_code": 0, "account_name": 1, "debit": 2})
    assert fields == ["account_code", "account_name", "debit"]
    assert by_letter == by_index == [
        {"account_code": "4-100", "account_name": "Taxation", "debit": "100"},
        {"account_code": "6-100", "account_name": "Salaries", "debit": ""},
    ]


def test_apply_column_map_missing_required_names_fields():
    grid = [["4-100", "100"]]
    with pytest.raises(ip.ImportMappingError) as excinfo:
        ip.apply_column_map(grid, 0, {"account_code": 0}, required=("account_code", "debit", "credit"))
    assert excinfo.value.missing == ["debit", "credit"]
    assert "debit" in str(excinfo.value) and "credit" in str(excinfo.value)


def test_apply_column_map_out_of_range():
    grid = [["4-100", "100"]]
    with pytest.raises(ip.ImportMappingError, match="out of range"):
        ip.apply_column_map(grid, 0, {"account_code": 0, "debit": 5}, required=("account_code", "debit"))
    with pytest.raises(ip.ImportMappingError, match="out of range"):
        ip.apply_column_map(grid, 0, {"account_code": "C"}, required=("account_code",))


def test_apply_column_map_header_row_out_of_range():
    with pytest.raises(ip.ImportMappingError, match="header row"):
        ip.apply_column_map([["a"]], 7, {"account_code": 0})


# ---------------------------------------------------------------------------
# Preview endpoint
# ---------------------------------------------------------------------------

def test_preview_csv_reports_grid_header_and_guesses(client, auth):
    content = (
        "City of Springfield\nTrial Balance 2026\n\n"
        "Acct No,Description,Debit,Credit\n"
        "4-100,Taxation,\"1,234.56\",\n"
        "6-100,Salaries,,(500.00)\n"
    ).encode()
    r = client.post("/api/v1/imports/preview", headers=auth("officer"),
                    files={"file": ("tb.csv", content, "text/csv")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["file_type"] == "csv"
    assert body["sheet_names"] == []
    # The blank separator row is dropped by the grid loader, so the header is
    # non-empty-row 2 (0-based).
    assert body["header_row"] == 2
    assert body["total_rows"] == 5
    assert body["rows"][2] == ["Acct No", "Description", "Debit", "Credit"]
    assert body["rows"][3] == ["4-100", "Taxation", "1,234.56", ""]
    guesses = body["column_guesses"]
    assert guesses["account_code"] == {"index": 0, "header": "Acct No"}
    assert guesses["debit"] == {"index": 2, "header": "Debit"}
    assert guesses["credit"] == {"index": 3, "header": "Credit"}
    # amount is NOT guessed here: Debit/Credit were matched first and amount
    # variants only fire on a genuine Amount/Balance header.
    assert "amount" not in guesses


def test_preview_xlsx_reports_sheets_and_respects_sheet_param(client, auth):
    content = xlsx_bytes(
        [["Account", "Debit"], ["4-100", 1]],
        [["Class", "Additions"], ["Buildings", 50]],
        sheet_names=["Summary", "Asset detail"],
    )
    r = client.post("/api/v1/imports/preview", headers=auth("officer"),
                    files={"file": ("tb.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200
    body = r.json()
    assert body["file_type"] == "xlsx"
    assert body["sheet_names"] == ["Summary", "Asset detail"]
    assert body["rows"][0] == ["Account", "Debit"]

    r = client.post("/api/v1/imports/preview", headers=auth("officer"), params={"sheet": "Asset detail"},
                    files={"file": ("tb.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200
    assert r.json()["rows"][0] == ["Class", "Additions"]


def test_preview_limits_rows_and_never_writes(client, auth, fy2025):
    content = ("Account,Debit\n" + "".join(f"1-{n:03},{n}\n" for n in range(40))).encode()
    r = client.post("/api/v1/imports/preview", headers=auth("officer"),
                    files={"file": ("big.csv", content, "text/csv")})
    body = r.json()
    assert len(body["rows"]) == 25 and body["total_rows"] == 41
    assert body["rows"][0] == ["Account", "Debit"]


def test_preview_rejects_unsupported_file(client, auth):
    # Legacy binary .xls is refused outright, as in every import endpoint.
    r = client.post("/api/v1/imports/preview", headers=auth("officer"),
                    files={"file": ("tb.xls", b"\xd0\xcf\x11\xe0whatever", "application/vnd.ms-excel")})
    assert r.status_code == 400
    r = client.post("/api/v1/imports/preview", headers=auth("officer"),
                    files={"file": ("empty.csv", b"", "text/csv")})
    assert r.status_code == 400


def test_preview_requires_auth(client):
    assert client.post("/api/v1/imports/preview", files={"file": ("x.csv", b"a,b", "text/csv")}).status_code == 401


# ---------------------------------------------------------------------------
# Trial balance with explicit column_map
# ---------------------------------------------------------------------------

def _tb_entry(client, auth, fy, code):
    rows = client.get("/api/v1/trial-balance", headers=auth("viewer"),
                      params={"period_id": period_of(fy, 1).id}).json()
    acct = next(a for a in client.get("/api/v1/accounts", headers=auth("viewer"),
                                      params={"fiscal_year_id": fy.id}).json()
                if a["acct_fmtd"] == code)
    return next((e for e in rows if e["account_id"] == acct["id"]), None)


def test_tb_import_with_explicit_map(client, auth, fy2025, db):
    make_account(db, fy2025, "4-100", "Taxation")
    make_account(db, fy2025, "6-100", "Salaries")
    # Odd column order + a title row the auto-detector would trip over
    content = to_csv(
        [{"Dr": "1,000.00", "Code": "4-100", "Extra": "x", "Cr": ""},
         {"Dr": "", "Code": "6-100", "Extra": "y", "Cr": "250.50"}],
        ["Dr", "Code", "Extra", "Cr"])
    r = client.post(
        f"/api/v1/trial-balance/import/csv?period_id={period_of(fy2025, 1).id}&fiscal_year_id={fy2025.id}",
        headers=auth("officer"),
        files={"file": ("tb.csv", content, "text/csv")},
        data={"column_map": json.dumps({"account_code": "B", "debit": "A", "credit": "D"})},
    )
    assert r.status_code == 200, r.text
    assert r.json()["records_imported"] == 2
    entry = _tb_entry(client, auth, fy2025, "4-100")
    assert Decimal(entry["period_debit"]) == Decimal("1000.00")
    entry = _tb_entry(client, auth, fy2025, "6-100")
    assert Decimal(entry["period_credit"]) == Decimal("250.50")


def test_tb_import_map_with_amount_column_splits_signs(client, auth, fy2025, db):
    make_account(db, fy2025, "4-100", "Taxation")
    make_account(db, fy2025, "6-100", "Salaries")
    content = to_csv(
        [{"Acct": "4-100", "Bal": "500"}, {"Acct": "6-100", "Bal": "(120.00)"}],
        ["Acct", "Bal"])
    r = client.post(
        f"/api/v1/trial-balance/import/csv?period_id={period_of(fy2025, 1).id}&fiscal_year_id={fy2025.id}",
        headers=auth("officer"),
        files={"file": ("tb.csv", content, "text/csv")},
        data={"column_map": json.dumps({"account_code": 0, "amount": 1})},
    )
    assert r.status_code == 200, r.text
    assert Decimal(_tb_entry(client, auth, fy2025, "4-100")["period_debit"]) == Decimal("500")
    assert Decimal(_tb_entry(client, auth, fy2025, "6-100")["period_credit"]) == Decimal("120.00")


def test_tb_import_incomplete_map_422_names_missing_fields(client, auth, fy2025):
    r = client.post(
        f"/api/v1/trial-balance/import/csv?period_id={period_of(fy2025, 1).id}&fiscal_year_id={fy2025.id}",
        headers=auth("officer"),
        files={"file": ("tb.csv", b"a,b\n1,2\n", "text/csv")},
        data={"column_map": json.dumps({"debit": 0, "credit": 1})},
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["missing_fields"] == ["account_code"]
    assert "account_code" in detail["message"]


def test_tb_import_out_of_range_map_422(client, auth, fy2025):
    r = client.post(
        f"/api/v1/trial-balance/import/csv?period_id={period_of(fy2025, 1).id}&fiscal_year_id={fy2025.id}",
        headers=auth("officer"),
        files={"file": ("tb.csv", b"a,b\n1,2\n", "text/csv")},
        data={"column_map": json.dumps({"account_code": 0, "debit": 9})},
    )
    assert r.status_code == 422
    assert "out of range" in r.json()["detail"]["message"]


def test_tb_import_map_with_explicit_header_row(client, auth, fy2025, db):
    make_account(db, fy2025, "4-100", "Taxation")
    content = to_csv([{"Account": "4-100", "Debit": "75"}], ["Account", "Debit"])
    r = client.post(
        f"/api/v1/trial-balance/import/csv?period_id={period_of(fy2025, 1).id}&fiscal_year_id={fy2025.id}",
        headers=auth("officer"),
        files={"file": ("tb.csv", content, "text/csv")},
        data={"column_map": json.dumps({"account_code": 0, "debit": 1}), "header_row": "0"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["records_imported"] == 1


def test_tb_import_without_map_unchanged_regression(client, auth, fy2025, db):
    """No column_map: plain well-formed CSV keeps working exactly as before."""
    make_account(db, fy2025, "4-100", "Taxation")
    make_account(db, fy2025, "6-100", "Salaries")
    content = b"Account,Debit,Credit\n4-100,100.50,\n6-100,,25\n"
    r = client.post(
        f"/api/v1/trial-balance/import/csv?period_id={period_of(fy2025, 1).id}&fiscal_year_id={fy2025.id}",
        headers=auth("officer"), files={"file": ("tb.csv", content, "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["records_imported"] == 2
    assert Decimal(_tb_entry(client, auth, fy2025, "4-100")["period_debit"]) == Decimal("100.50")


def test_tb_import_xlsx_with_map(client, auth, fy2025, db):
    make_account(db, fy2025, "4-100", "Taxation")
    content = xlsx_bytes(
        [["City of Opentrail"], [],
         ["Code", "Amount"], ["4-100", 300]])
    r = client.post(
        f"/api/v1/trial-balance/import/csv?period_id={period_of(fy2025, 1).id}&fiscal_year_id={fy2025.id}",
        headers=auth("officer"),
        files={"file": ("tb.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"column_map": json.dumps({"account_code": 0, "amount": 1}), "header_row": "2"},
    )
    assert r.status_code == 200, r.text
    assert Decimal(_tb_entry(client, auth, fy2025, "4-100")["period_debit"]) == Decimal("300")


# ---------------------------------------------------------------------------
# Budget lines with explicit column_map
# ---------------------------------------------------------------------------

@pytest.fixture()
def budget_world(client, auth, db, users, fy2025):
    from app.models.budget import BudgetYear
    make_account(db, fy2025, "4-100", "Taxation")
    make_account(db, fy2025, "6-100", "Salaries")
    by = BudgetYear(fiscal_year_id=fy2025.id, label="2025", status="open", created_by=users["admin"].id)
    db.add(by)
    db.commit()
    db.refresh(by)
    return by


def test_budget_import_with_explicit_map(client, auth, budget_world):
    content = to_csv([{"GL": "4-100", "Amt": "1,200"}, {"GL": "6-100", "Amt": "300"}], ["GL", "Amt"])
    r = client.post(f"/api/v1/budget-years/{budget_world.id}/lines/import/csv", headers=auth("admin"),
                    files={"file": ("budget.csv", content, "text/csv")},
                    data={"column_map": json.dumps({"account_code": 0, "amount": 1})})
    assert r.status_code == 200, r.text
    assert r.json()["lines"] == 2
    lines = client.get(f"/api/v1/budget-years/{budget_world.id}/lines", headers=auth("viewer")).json()
    amounts = {l["account_id"]: Decimal(l["approved_amount"]) for l in lines}
    assert sorted(amounts.values()) == [Decimal("300"), Decimal("1200")]


def test_budget_import_incomplete_map_422(client, auth, budget_world):
    r = client.post(f"/api/v1/budget-years/{budget_world.id}/lines/import/csv", headers=auth("admin"),
                    files={"file": ("budget.csv", b"a,b\n1,2\n", "text/csv")},
                    data={"column_map": json.dumps({"amount": 1})})
    assert r.status_code == 422
    assert r.json()["detail"]["missing_fields"] == ["account_code"]


def test_budget_import_without_map_unchanged_regression(client, auth, budget_world):
    content = b"Account,Amount\n4-100,\"1,200\"\n6-100,300\n"
    r = client.post(f"/api/v1/budget-years/{budget_world.id}/lines/import/csv", headers=auth("admin"),
                    files={"file": ("budget.csv", content, "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["lines"] == 2 and r.json()["errors"] == []


# ---------------------------------------------------------------------------
# TCA with explicit column_map
# ---------------------------------------------------------------------------

def test_tca_import_with_explicit_map(client, auth, fy2025):
    content = to_csv(
        [{"Class": "Land", "Open": "1000000"},
         {"Class": "Buildings", "Open": "2500000", "Add": "50,000"}],
        ["Class", "Open", "Add"])
    r = client.post(f"/api/v1/tca/lines/import?fiscal_year_id={fy2025.id}", headers=auth("officer"),
                    files={"file": ("tca.csv", content, "text/csv")},
                    data={"column_map": json.dumps({"asset_class": 0, "cost_opening": 1, "cost_additions": 2})})
    assert r.status_code == 200, r.text
    assert r.json() == {"records_imported": 2, "errors": []}
    rows = {l["asset_class"]: l for l in client.get("/api/v1/tca/lines", headers=auth("viewer"),
                                                    params={"fiscal_year_id": fy2025.id}).json()}
    assert Decimal(rows["Buildings"]["cost_additions"]) == Decimal("50000")


def test_tca_import_incomplete_map_422(client, auth, fy2025):
    r = client.post(f"/api/v1/tca/lines/import?fiscal_year_id={fy2025.id}", headers=auth("officer"),
                    files={"file": ("tca.csv", b"a,b\n1,2\n", "text/csv")},
                    data={"column_map": json.dumps({"cost_opening": 1})})
    assert r.status_code == 422
    assert r.json()["detail"]["missing_fields"] == ["asset_class"]


def test_tca_import_without_map_unchanged_regression(client, auth, fy2025):
    content = (
        "Asset class,Cost opening,Additions,Disposals,Accumulated amortization opening,"
        "Amortization,Amortization disposals\n"
        "Land,1000000,0,0,0,0,0\n"
    ).encode()
    r = client.post(f"/api/v1/tca/lines/import?fiscal_year_id={fy2025.id}", headers=auth("officer"),
                    files={"file": ("tca.csv", content, "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json() == {"records_imported": 1, "errors": []}


# ---------------------------------------------------------------------------
# SOFI with explicit column_map
# ---------------------------------------------------------------------------

def test_sofi_import_with_explicit_map(client, auth, fy2025):
    content = to_csv(
        [{"Payee": "Acme Ltd", "Paid": "$31,000", "Dept": "roads"},
         {"Payee": "B Ltd", "Paid": "500", "Dept": ""}],
        ["Payee", "Paid", "Dept"])
    r = client.post(
        f"/api/v1/sofi/entries/import?fiscal_year_id={fy2025.id}&schedule_type=supplier_payment",
        headers=auth("officer"),
        files={"file": ("sofi.csv", content, "text/csv")},
        data={"column_map": json.dumps({"name": 0, "amount": 1, "description": 2})},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"records_imported": 2, "errors": []}
    entries = client.get("/api/v1/sofi/entries", headers=auth("viewer"),
                         params={"fiscal_year_id": fy2025.id, "schedule_type": "supplier_payment"}).json()
    by_name = {e["name"]: e for e in entries}
    assert Decimal(by_name["Acme Ltd"]["amount"]) == Decimal("31000")
    assert by_name["Acme Ltd"]["description"] == "roads"


def test_sofi_import_incomplete_map_422(client, auth, fy2025):
    r = client.post(
        f"/api/v1/sofi/entries/import?fiscal_year_id={fy2025.id}&schedule_type=supplier_payment",
        headers=auth("officer"),
        files={"file": ("sofi.csv", b"a,b\n1,2\n", "text/csv")},
        data={"column_map": json.dumps({"amount": 1})},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["missing_fields"] == ["name"]


def test_sofi_import_without_map_unchanged_regression(client, auth, fy2025):
    content = b"Supplier,Amount\nAcme Ltd,31000\n"
    r = client.post(
        f"/api/v1/sofi/entries/import?fiscal_year_id={fy2025.id}&schedule_type=supplier_payment",
        headers=auth("officer"), files={"file": ("sofi.csv", content, "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json() == {"records_imported": 1, "errors": []}


def test_import_invalid_json_column_map_422(client, auth, fy2025):
    r = client.post(
        f"/api/v1/trial-balance/import/csv?period_id={period_of(fy2025, 1).id}&fiscal_year_id={fy2025.id}",
        headers=auth("officer"),
        files={"file": ("tb.csv", b"a,b\n1,2\n", "text/csv")},
        data={"column_map": "not json"},
    )
    assert r.status_code == 422
