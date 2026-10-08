"""
Integration test: render every built-in statement against a balanced two-year ledger
and check that the statements articulate with each other.
"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.budget import BudgetLine, BudgetYear
from app.models.mapping import MappingScheme
from app.models.report import Report
from app.services.builtin_templates import PSAB_TAXONOMY, TEMPLATE_VERSION, TEMPLATES, seed_templates
from app.services.report_engine import generate, validate_definition
from tests.conftest import add_je, add_tb, classify, make_account, make_fiscal_year, period_of

ACCOUNTS = {  # code: (description, classification)
    "1-100": ("Cash", "financial_assets.cash"),
    "1-200": ("Property taxes receivable", "financial_assets.taxes_receivable"),
    "1-300": ("Accounts receivable", "financial_assets.receivables"),
    "1-400": ("Investments", "financial_assets.investments"),
    "2-100": ("Accounts payable", "liabilities.payables"),
    "2-200": ("Deferred revenue", "liabilities.deferred_revenue"),
    "2-500": ("Debenture debt", "liabilities.debt"),
    "3-100": ("TCA cost", "non_financial_assets.tca_cost"),
    "3-190": ("TCA accumulated amortization", "non_financial_assets.tca_amortization"),
    "3-300": ("Prepaid expenses", "non_financial_assets.prepaids"),
    "5-000": ("Accumulated surplus", "accumulated_surplus.operating"),
    "4-100": ("Property taxes", "revenue.taxation"),
    "4-200": ("Utility fees", "revenue.sale_of_services"),
    "6-100": ("Roads", "expense.transportation"),
    "6-200": ("Parks", "expense.recreation_culture"),
    "6-300": ("Administration", "expense.general_government"),
}

OPENING_2024 = {"1-100": 500, "1-200": 100, "1-300": 50, "1-400": 300, "2-100": -120, "2-200": -30,
                "2-500": -400, "3-100": 2000, "3-190": -600, "3-300": 20, "5-000": -1820}
MOVES_2024 = {"4-100": -1000, "4-200": -200, "6-100": 500, "6-200": 300, "6-300": 250,
              "3-100": 300, "3-190": -100, "2-500": 50, "2-100": -20, "1-200": 10, "1-300": -5,
              "2-200": 5, "1-100": -90}
MOVES_2025 = {"4-100": -1100, "4-200": -250, "6-100": 600, "6-200": 350, "6-300": 300,
              "3-100": 400, "3-190": -120, "2-500": -200, "2-100": 30, "1-200": -10, "1-300": 15,
              "1-400": -50, "2-200": -10, "3-300": 5, "1-100": 40}


@pytest.fixture()
def ledger(db, users):
    seed_templates(db, users["admin"].id)
    psab = db.scalars(select(MappingScheme).where(MappingScheme.name == "PSAB")).one()
    assert sum(OPENING_2024.values()) == sum(MOVES_2024.values()) == sum(MOVES_2025.values()) == 0

    years = {}
    opening = OPENING_2024
    for year, moves in ((2024, MOVES_2024), (2025, MOVES_2025)):
        fy = make_fiscal_year(db, year)
        accts = {}
        for code, (desc, cls) in ACCOUNTS.items():
            accts[code] = make_account(db, fy, code, desc)
            classify(db, psab, accts[code], cls)
            add_tb(db, period_of(fy, 12), accts[code], opening=opening.get(code, 0), ytd=moves.get(code, 0))
        years[year] = (fy, accts)
        # roll forward: balance sheet closes to opening; revenue/expense close to surplus
        closing = {c: opening.get(c, 0) + moves.get(c, 0) for c in ACCOUNTS}
        surplus = sum(v for c, v in closing.items() if c[0] in "46")
        opening = {c: v for c, v in closing.items() if c[0] not in "46"}
        opening["5-000"] += surplus

    fy25, a25 = years[2025]
    # AJE: accrue $25 roads expense at year end
    add_je(db, period_of(fy25, 12), users["officer"], "adjusting", [(a25["6-100"], 25), (a25["2-100"], -25)])
    by = BudgetYear(fiscal_year_id=fy25.id, label="2025", status="adopted", created_by=users["admin"].id)
    db.add(by)
    db.flush()
    for code, amt in {"4-100": 1080, "4-200": 240, "6-100": 610, "6-200": 340, "6-300": 310}.items():
        db.add(BudgetLine(budget_year_id=by.id, account_id=a25[code].id, approved_amount=amt, budget_type="operating"))
    db.commit()
    return fy25


def render(db, key, fy):
    out = generate(db, TEMPLATES[key]["definition"], fy.id)
    rows = {}
    for r in out["rows"]:
        rows.setdefault(r["label"], r)
    return out, rows


def val(rows, label, col="cy"):
    v = rows[label]["values"][col]
    return None if v is None else Decimal(v)


def test_all_templates_valid():
    for key, tpl in TEMPLATES.items():
        assert validate_definition(tpl["definition"]) == [], key
        assert tpl["definition"]["template_key"] == key


def test_taxonomy_covers_template_classifications():
    tops = {v.split(".")[0] for v in PSAB_TAXONOMY}
    assert tops == {"financial_assets", "liabilities", "non_financial_assets", "revenue", "expense",
                    "accumulated_surplus"}


def test_statement_of_operations(db, ledger):
    out, r = render(db, "psab_so", ledger)
    assert out["warnings"] == []
    assert val(r, "Total revenue") == 1350 and val(r, "Total revenue", "py") == 1200
    assert val(r, "Total expenses") == 1275
    assert val(r, "Annual surplus (deficit)") == 75 and val(r, "Annual surplus (deficit)", "py") == 150
    assert val(r, "Accumulated surplus, beginning of year") == 1970
    assert val(r, "Accumulated surplus, beginning of year", "py") == 1820
    assert val(r, "Accumulated surplus, end of year") == 2045
    # budget column: budgeted surplus (1320 - 1260) on the actual opening surplus
    assert val(r, "Annual surplus (deficit)", "bud") == 60
    assert val(r, "Accumulated surplus, end of year", "bud") == 2030
    assert "Taxation, net" in r and "Public health" not in r  # zero lines suppressed


def test_financial_position_ties_to_operations(db, ledger):
    out, r = render(db, "psab_sfp", ledger)
    assert out["subtitle"] == "As at December 31, 2025"
    assert val(r, "Total financial assets") == 860
    assert val(r, "Total liabilities") == 720
    assert val(r, "Net financial assets (debt)") == 140
    assert val(r, "Tangible capital assets") == 1880
    assert val(r, "Accumulated surplus") == 2045  # = SO closing accumulated surplus
    assert val(r, "Accumulated surplus", "py") == 1970


def test_change_in_net_financial_assets(db, ledger):
    out, r = render(db, "psab_scnfa", ledger)
    assert out["warnings"] == []  # closing NFA agrees to SFP for both years
    assert val(r, "Acquisition of tangible capital assets") == -400
    assert val(r, "Amortization of tangible capital assets") == 120
    assert val(r, "Change in net financial assets (debt)") == -210
    assert val(r, "Net financial assets (debt), end of year") == 140


def test_cash_flow(db, ledger):
    out, r = render(db, "psab_scf", ledger)
    assert out["warnings"] == []  # closing cash agrees to SFP for both years
    assert val(r, "Cash provided by operating transactions") == 190
    assert val(r, "Cash applied to capital transactions") == -400
    assert val(r, "Cash provided by (applied to) financing transactions") == 200
    assert val(r, "Cash and cash equivalents, end of year") == 450
    assert val(r, "Cash and cash equivalents, end of year", "py") == 410
    assert "Revenue" not in r  # hidden helper rows


def test_check_failure_reported(db, ledger):
    d = {**TEMPLATES["psab_scf"]["definition"],
         "checks": [{"label": "deliberately off by one", "formula": "cash_close - cash_sfp + 1"}]}
    out = generate(db, d, ledger.id)
    # one warning per actual column (current and prior year), none for budget columns
    assert len([w for w in out["warnings"] if "deliberately off by one" in w]) == 2


def test_notes_render(db, ledger):
    out, r = render(db, "psab_notes", ledger)
    assert any("prepared by management" in label for label in r)
    assert "Municipality" in next(l for l in r if "prepared by management" in l)
    assert val(r, "Net book value") == 1880


def test_seed_is_idempotent_and_upgrades(db, users):
    seed_templates(db, users["admin"].id)
    seed_templates(db, users["admin"].id)
    reports = db.scalars(select(Report).where(Report.is_template.is_(True))).all()
    assert len(reports) == len(TEMPLATES)
    assert all(r.is_protected for r in reports)
    assert len(db.scalars(select(MappingScheme)).all()) == 1

    so = next(r for r in reports if r.definition["template_key"] == "psab_so")
    so.definition = {**so.definition, "template_version": TEMPLATE_VERSION - 1, "title": "stale"}
    db.commit()
    seed_templates(db, users["admin"].id)
    db.refresh(so)
    assert so.definition["title"] == "Statement of Operations"


def test_clone_and_revert_via_api(client, auth, db, users):
    seed_templates(db, users["admin"].id)
    tpl = next(r for r in db.scalars(select(Report)).all() if r.definition["template_key"] == "psab_sfp")
    clone = client.post(f"/api/v1/reports/{tpl.id}/clone", headers=auth("officer")).json()
    edited = {**clone["definition"], "title": "Our SFP"}
    client.put(f"/api/v1/reports/{clone['id']}", json={"definition": edited}, headers=auth("officer"))
    r = client.post(f"/api/v1/reports/{clone['id']}/revert", headers=auth("officer"))
    assert r.status_code == 200
    assert r.json()["definition"]["title"] == "Statement of Financial Position"
    assert r.json()["definition"]["source_template_key"] == "psab_sfp"
    assert client.post(f"/api/v1/reports/{tpl.id}/revert", headers=auth("officer")).status_code == 400

    tax = client.get("/api/v1/reports/psab-taxonomy", headers=auth("viewer"))
    assert tax.status_code == 200 and {"value", "label", "group"} <= set(tax.json()[0])
