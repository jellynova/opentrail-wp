from decimal import Decimal

import pytest

from app.models.budget import BudgetLine, BudgetYear
from app.services.report_engine import (
    ReportDefinitionError, evaluate_formula, format_amount, generate, normalize_definition, validate_definition,
)
from app.services.report_generator import export_to_excel, report_to_html
from tests.conftest import add_je, add_tb, classify, make_account, make_fiscal_year, make_scheme, period_of


@pytest.fixture()
def ds(db, users):
    fy24, fy25 = make_fiscal_year(db, 2024), make_fiscal_year(db, 2025)
    psab = make_scheme(db)
    acc = {}
    for fy, y in ((fy24, 24), (fy25, 25)):
        for code, desc, cls in [
            ("1-100", "Cash", "financial_assets.cash"),
            ("1-200", "Taxes receivable", "financial_assets.receivables"),
            ("2-100", "Accounts payable", "liabilities.payables"),
            ("2-500", "Long-term debt", "liabilities.debt"),
            ("3-100", "Tangible capital assets", "non_financial_assets.tca"),
            ("4-100", "Property taxes", "revenue.taxation"),
            ("4-200", "User fees", "revenue.sale_of_services"),
            ("6-100", "Roads", "expense.transportation"),
            ("6-200", "Parks", "expense.recreation"),
        ]:
            acc[f"{code}/{y}"] = a = make_account(db, fy, code, desc)
            classify(db, psab, a, cls)

    def tb(y, fy, entries):
        p12 = period_of(fy, 12)
        for code, opening, ytd in entries:
            add_tb(db, p12, acc[f"{code}/{y}"], opening=opening, ytd=ytd)

    # FY2024 closing: cash 400, rec 100, AP -150, debt -300, TCA 1000 => accumulated surplus 1050
    tb(24, fy24, [("1-100", 300, 100), ("1-200", 100, 0), ("2-100", -100, -50), ("2-500", -350, 50),
                  ("3-100", 900, 100), ("4-100", 0, -800), ("6-100", 0, 500), ("6-200", 0, 100)])
    # FY2025 (opening = 2024 closing for balance sheet)
    tb(25, fy25, [("1-100", 400, 250), ("1-200", 100, 50), ("2-100", -150, -100), ("2-500", -300, 50),
                  ("3-100", 1000, 0), ("4-100", 0, -900), ("4-200", 0, -100), ("6-100", 0, 600),
                  ("6-200", 0, 150)])
    # posted AJE: accrue $50 parks expense
    add_je(db, period_of(fy25, 12), users["officer"], "adjusting", [(acc["6-200/25"], 50), (acc["2-100/25"], -50)])

    by = BudgetYear(fiscal_year_id=fy25.id, label="2025 Budget", status="adopted", created_by=users["admin"].id)
    db.add(by)
    db.flush()
    for code, amt in [("4-100", 950), ("4-200", 80), ("6-100", 650), ("6-200", 180)]:
        db.add(BudgetLine(budget_year_id=by.id, account_id=acc[f"{code}/25"].id, approved_amount=amt,
                          budget_type="operating"))
    db.commit()
    return {"fy24": fy24, "fy25": fy25, "acc": acc}


SO_DEF = {
    "version": 2,
    "title": "Statement of Operations",
    "subtitle": "Year ended {period_end}",
    "columns": [
        {"key": "bud", "label": "{fiscal_year} Budget", "source": "budget"},
        {"key": "cy", "label": "{fiscal_year}", "source": "actual"},
        {"key": "py", "label": "{prior_fiscal_year}", "source": "actual", "year_offset": -1},
        {"key": "var", "label": "Variance", "source": "formula", "formula": "cy - bud"},
    ],
    "rows": [
        {"id": "rev", "type": "section", "label": "Revenue", "total_label": "Total revenue", "children": [
            {"id": "tax", "type": "accounts", "label": "Taxation", "classifications": ["revenue.taxation"], "sign": -1},
            {"type": "accounts", "label": "Sale of services", "classifications": ["revenue.sale_of_services"], "sign": -1},
        ]},
        {"id": "exp", "type": "section", "label": "Expenses", "total_label": "Total expenses", "children": [
            {"type": "accounts", "label": "Transportation", "classifications": ["expense.transportation"]},
            {"type": "accounts", "label": "Recreation", "classifications": ["expense.recreation"]},
        ]},
        {"id": "surplus", "type": "formula", "label": "Annual surplus", "formula": "rev - exp",
         "style": {"bold": True, "underline": "double"}},
        {"id": "as_open", "type": "accounts", "label": "Accumulated surplus, beginning of year",
         "classifications": ["financial_assets*", "liabilities*", "non_financial_assets*"], "measure": "opening"},
        {"id": "as_close", "type": "formula", "label": "Accumulated surplus, end of year", "formula": "as_open + surplus"},
        {"type": "text", "label": "Surplus of {row:surplus:cy} for {fiscal_year}."},
    ],
}


def _rows(out):
    return {r["label"]: r for r in out["rows"]}


def _v(row, key):
    v = row["values"][key]
    return None if v is None else Decimal(v)


def test_statement_of_operations(db, ds):
    out = generate(db, SO_DEF, ds["fy25"].id)
    assert out["subtitle"] == "Year ended December 31, 2025"
    assert [c["label"] for c in out["columns"]] == ["2025 Budget", "2025", "2024", "Variance"]
    r = _rows(out)
    assert _v(r["Taxation"], "cy") == 900 and _v(r["Taxation"], "py") == 800 and _v(r["Taxation"], "bud") == 950
    assert _v(r["Total revenue"], "cy") == 1000
    assert _v(r["Total revenue"], "var") == -30  # 1000 - 1030
    assert _v(r["Recreation"], "cy") == 200  # 150 + AJE 50
    assert _v(r["Total expenses"], "cy") == 800 and _v(r["Total expenses"], "bud") == 830
    assert _v(r["Annual surplus"], "cy") == 200 and _v(r["Annual surplus"], "py") == 200
    assert _v(r["Annual surplus"], "bud") == 200
    assert _v(r["Accumulated surplus, beginning of year"], "cy") == 1050
    assert _v(r["Accumulated surplus, end of year"], "cy") == 1250
    assert r["Surplus of 200 for 2025."]["values"]["cy"] is None
    assert r["Revenue"]["values"]["cy"] is None  # section header carries no amount
    assert out["warnings"] == []


def test_financial_position_ties_to_operations(db, ds):
    sfp = {
        "version": 2, "title": "SFP",
        "columns": [{"key": "cy", "label": "{fiscal_year}", "source": "actual"}],
        "rows": [
            {"id": "fa", "type": "section", "label": "Financial assets", "total_label": "Total", "children": [
                {"type": "accounts", "label": "Cash", "classifications": ["financial_assets.cash"]},
                {"type": "accounts", "label": "Receivables", "classifications": ["financial_assets.receivables"]}]},
            {"id": "li", "type": "section", "label": "Liabilities", "total_label": "Total", "children": [
                {"type": "accounts", "label": "Liabilities", "classifications": ["liabilities*"], "sign": -1}]},
            {"id": "nfa", "type": "formula", "label": "Net financial assets", "formula": "fa - li"},
            {"id": "nf", "type": "accounts", "label": "TCA", "classifications": ["non_financial_assets*"]},
            {"id": "as", "type": "formula", "label": "Accumulated surplus", "formula": "nfa + nf"},
        ],
    }
    r = _rows(generate(db, sfp, ds["fy25"].id))
    # cash 650, rec 150, liabilities: AP 250+50 AJE, debt 250 => 550
    assert _v(r["Net financial assets"], "cy") == 250
    assert _v(r["Accumulated surplus"], "cy") == 1250  # equals SO closing accumulated surplus


def test_movement_measure_and_period_cutoff(db, ds, users):
    d = {"version": 2, "title": "t", "columns": [{"key": "cy", "label": "x", "source": "actual"}],
         "rows": [{"type": "accounts", "label": "Change in cash", "classifications": ["financial_assets.cash"],
                   "measure": "movement"}]}
    assert _v(_rows(generate(db, d, ds["fy25"].id))["Change in cash"], "cy") == 250
    # period 6 has no TB data and the AJE is in period 12 => nothing to report
    p6 = period_of(ds["fy25"], 6)
    assert _rows(generate(db, d, ds["fy25"].id, p6.id)) == {}


def test_account_detail_merges_years(db, ds):
    d = {"version": 2, "title": "t",
         "columns": [{"key": "cy", "label": "cy", "source": "actual"},
                     {"key": "py", "label": "py", "source": "actual", "year_offset": -1}],
         "rows": [{"type": "accounts", "label": "Total revenue", "classifications": ["revenue*"], "sign": -1,
                   "show_detail": True}]}
    out = generate(db, d, ds["fy25"].id)
    detail = [r for r in out["rows"] if r["type"] == "account"]
    assert [(r["acct_fmtd"], _v(r, "cy"), _v(r, "py")) for r in detail] == [
        ("4-100", 900, 800), ("4-200", 100, 0)]
    assert detail[0]["account_id"] == ds["acc"]["4-100/25"].id
    assert _v(_rows(out)["Total revenue"], "cy") == 1000


def test_account_patterns_and_manual_rows(db, ds):
    d = {"version": 2, "title": "t", "columns": [{"key": "cy", "label": "cy", "source": "actual"}],
         "rows": [{"id": "g", "type": "group", "label": "Six", "total_label": "Total six", "children": [
             {"type": "accounts", "label": "6-series", "accounts": ["6-*"]},
             {"type": "manual", "label": "Gain on disposal", "values": {"cy": "12.50"}}]}]}
    r = _rows(generate(db, d, ds["fy25"].id))
    assert _v(r["6-series"], "cy") == 800
    assert _v(r["Total six"], "cy") == Decimal("812.50")


def test_v1_definition_still_renders(db, ds):
    v1 = {"title": "Old", "report_type": "custom", "comparative": True, "include_account_detail": False,
          "sections": [{"title": "Revenue", "scheme_id": 1, "classification_values": ["revenue.taxation"]},
                       {"title": "Expenses", "scheme_id": 1, "classification_values": ["expense.transportation"],
                        "negate": True}]}
    out = generate(db, v1, ds["fy25"].id)
    r = _rows(out)
    assert _v(r["Total Revenue"], "cy") == 900
    # v1 amounts were credit-positive; "negate" flips expenses to positive
    assert _v(r["Total Expenses"], "cy") == 600
    assert _v(r["Grand Total"], "cy") == 1500 and _v(r["Grand Total"], "py") == 1300
    assert normalize_definition(v1)["version"] == 2


def test_validation_problems():
    bad = {"version": 2, "title": "t",
           "columns": [{"key": "a", "source": "actual"}, {"key": "a", "source": "nope"}],
           "rows": [{"id": "x", "type": "formula", "formula": "y + 1"},
                    {"id": "x", "type": "weird"},
                    {"id": "z", "type": "formula", "formula": "__import__('os')"}]}
    problems = " | ".join(validate_definition(bad))
    for expected in ["unique", "unknown source", "unknown row(s) ['y']", "unknown type", "Unsupported"]:
        assert expected in problems


def test_circular_formula_detected(db, ds):
    d = {"version": 2, "title": "t", "columns": [{"key": "cy", "label": "cy", "source": "actual"}],
         "rows": [{"id": "a", "type": "formula", "formula": "b"}, {"id": "b", "type": "formula", "formula": "a"}]}
    with pytest.raises(ReportDefinitionError, match="Circular"):
        generate(db, d, ds["fy25"].id)


def test_formula_evaluation():
    vals = {"a": Decimal(10), "b": Decimal(4), "z": Decimal(0)}
    assert evaluate_formula("(a - b) * 2 / 3", vals.get) == Decimal(4)
    assert evaluate_formula("pct(a - b, b)", vals.get) == Decimal(150)
    assert evaluate_formula("a / z", vals.get) is None
    assert evaluate_formula("missing - a", vals.get) == Decimal(-10)
    assert evaluate_formula("abs(b - a)", vals.get) == Decimal(6)


def test_format_amount():
    assert format_amount(Decimal("-1234.5")) == "(1,235)"
    assert format_amount(Decimal("1234.5"), {"decimals": 2}, with_symbol=True) == "$1,234.50"
    assert format_amount(Decimal("0")) == "-"
    assert format_amount(None) == ""


def test_exports(db, ds):
    out = generate(db, SO_DEF, ds["fy25"].id)
    xlsx = export_to_excel(out)
    assert xlsx[:2] == b"PK"
    html = report_to_html({**out, "title": "<script>x</script>"})
    assert "<script>x" not in html and "&lt;script&gt;" in html
    assert "(30)" in html  # revenue variance rendered in parentheses
