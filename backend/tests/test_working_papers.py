from decimal import Decimal

import pytest

from app.models.trial_balance import TrialBalanceEntry
from app.services import sql_connector
from app.services import trial_balance as tb_svc
from tests.conftest import (
    add_je, add_tb, classify, make_account, make_fiscal_year, make_scheme, period_of,
)


@pytest.fixture()
def data(db, users):
    fy24 = make_fiscal_year(db, 2024)
    fy25 = make_fiscal_year(db, 2025)
    psab = make_scheme(db)
    a = {}
    for fy, tag in ((fy24, "24"), (fy25, "25")):
        a["cash" + tag] = make_account(db, fy, "1-100", "Cash")
        a["ap" + tag] = make_account(db, fy, "2-100", "Accounts payable")
        a["rev" + tag] = make_account(db, fy, "4-100", "Property taxes")
        a["exp" + tag] = make_account(db, fy, "6-100", "Roads maintenance")
        classify(db, psab, a["cash" + tag], "financial_assets.cash")
        classify(db, psab, a["ap" + tag], "liabilities.payables")
        classify(db, psab, a["rev" + tag], "revenue.taxation")
        classify(db, psab, a["exp" + tag], "expense.transportation")
    a["misc25"] = make_account(db, fy25, "9-999", "Suspense")  # unclassified

    # FY2024 final (period 12)
    p12 = period_of(fy24, 12)
    add_tb(db, p12, a["cash24"], ytd=500, opening=1000)
    add_tb(db, p12, a["ap24"], ytd=-200, opening=-300)

    # FY2025: period 1 and period 3 entries (YTD cumulative)
    p1, p3 = period_of(fy25, 1), period_of(fy25, 3)
    add_tb(db, p1, a["cash25"], opening=1300, ytd=100)
    add_tb(db, p3, a["cash25"], opening=1300, ytd=400, period_amt=150)
    add_tb(db, p3, a["ap25"], opening=-500, ytd=-50)
    add_tb(db, p3, a["rev25"], ytd=-1000)
    add_tb(db, p3, a["exp25"], ytd=650)
    add_tb(db, p3, a["misc25"], ytd=0)

    u = users["officer"]
    p2 = period_of(fy25, 2)
    # AJE in period 2: accrue $80 roads expense
    add_je(db, p2, u, "adjusting", [(a["exp25"], 80), (a["ap25"], -80)], reference="AJE-001")
    # RJE in period 3: reclass $30 from AP to suspense
    add_je(db, p3, u, "reclassifying", [(a["ap25"], 30), (a["misc25"], -30)], reference="RJE-001")
    # Excluded from the working TB
    add_je(db, p2, u, "adjusting", [(a["exp25"], 999), (a["ap25"], -999)], status="draft", reference="AJE-002")
    add_je(db, p2, u, "elimination", [(a["rev25"], 10), (a["exp25"], -10)])
    add_je(db, p2, u, "budget_variance", [(a["rev25"], 10), (a["exp25"], -10)])
    return {"fy24": fy24, "fy25": fy25, "p1": p1, "p3": p3, **a}


def _by_code(rows):
    return {r["acct_fmtd"]: r for r in rows}


def test_working_trial_balance_through_period(client, auth, data):
    r = client.get("/api/v1/working-papers/trial-balance",
                   params={"period_id": data["p3"].id, "scheme": "PSAB"}, headers=auth("viewer"))
    assert r.status_code == 200, r.text
    rows = _by_code(r.json())

    cash = rows["1-100"]
    assert Decimal(cash["unadjusted_balance"]) == 1700  # opening 1300 + ytd 400 (period 3 entry wins)
    assert Decimal(cash["period_debit"]) == 150
    assert cash["classification"] == "financial_assets.cash"

    ap = rows["2-100"]
    assert Decimal(ap["unadjusted_balance"]) == -550
    assert Decimal(ap["aje_credit"]) == 80  # draft AJE-002 excluded
    assert Decimal(ap["adjusted_balance"]) == -630
    assert Decimal(ap["rje_debit"]) == 30
    assert Decimal(ap["final_balance"]) == -600
    assert Decimal(ap["closing_credit"]) == 600 and Decimal(ap["closing_debit"]) == 0

    exp = rows["6-100"]
    assert Decimal(exp["final_balance"]) == 730  # elimination & budget_variance excluded
    rev = rows["4-100"]
    assert Decimal(rev["final_balance"]) == -1000

    # balanced adjustments don't change the trial balance total
    assert sum(Decimal(r["final_balance"]) for r in rows.values()) == sum(
        Decimal(r["unadjusted_balance"]) for r in rows.values()
    )


def test_wtb_period_one_excludes_later_adjustments(client, auth, data):
    rows = _by_code(client.get("/api/v1/working-papers/trial-balance",
                               params={"period_id": data["p1"].id}, headers=auth("viewer")).json())
    assert Decimal(rows["1-100"]["unadjusted_balance"]) == 1400
    assert "6-100" not in rows  # no TB data and no adjustments by period 1


def test_legacy_working_tb_endpoint_delegates(client, auth, data):
    r = client.get("/api/v1/trial-balance/working", params={"period_id": data["p3"].id}, headers=auth("viewer"))
    assert r.status_code == 200, r.text
    assert Decimal(_by_code(r.json())["2-100"]["final_balance"]) == -600


def test_leadsheets(client, auth, data):
    r = client.get("/api/v1/working-papers/leadsheets", params={"period_id": data["p3"].id}, headers=auth("viewer"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fiscal_year"] == "2025" and body["prior_fiscal_year"] == "2024"
    sheets = {g["classification"]: g for g in body["leadsheets"]}
    assert list(sheets)[-1] == "unclassified"

    cash = sheets["financial_assets.cash"]["accounts"][0]
    assert Decimal(cash["prior_year"]) == 1500  # 2024 opening 1000 + ytd 500
    assert Decimal(cash["change"]) == 200

    ap = sheets["liabilities.payables"]["totals"]
    assert Decimal(ap["prior_year"]) == -500
    assert Decimal(ap["aje"]) == -80 and Decimal(ap["rje"]) == 30 and Decimal(ap["final"]) == -600

    assert Decimal(sheets["unclassified"]["totals"]["final"]) == -30


def test_leadsheets_unknown_scheme(client, auth, data):
    r = client.get("/api/v1/working-papers/leadsheets",
                   params={"period_id": data["p3"].id, "scheme": "Nope"}, headers=auth("viewer"))
    assert r.status_code == 404


def test_je_schedules(client, auth, data):
    fy = data["fy25"].id
    aje = client.get("/api/v1/working-papers/je-schedule", params={"fiscal_year_id": fy}, headers=auth("viewer")).json()
    assert [e["reference"] for e in aje["entries"]] == ["AJE-001"]
    assert Decimal(aje["total_debit"]) == Decimal(aje["total_credit"]) == 80
    assert aje["entries"][0]["lines"][0]["acct_fmtd"] == "6-100"

    with_drafts = client.get("/api/v1/working-papers/je-schedule",
                             params={"fiscal_year_id": fy, "include_drafts": True}, headers=auth("viewer")).json()
    assert len(with_drafts["entries"]) == 2

    rje = client.get("/api/v1/working-papers/je-schedule",
                     params={"fiscal_year_id": fy, "entry_type": "reclassifying"}, headers=auth("viewer")).json()
    assert [e["reference"] for e in rje["entries"]] == ["RJE-001"]


def test_connector_import_computes_ytd(db, fy2025, monkeypatch):
    from app.models.connector import ExternalConnector

    conn = ExternalConnector(name="AMAIS", system_type="amais", is_active=True, created_by_user_id=1)
    db.add(conn)
    db.commit()
    acct = make_account(db, fy2025, "1-100", "Cash")
    rows = [
        {"acct_fmtd": "1-100", "fisc_prd": 0, "amount": -1000},  # opening
        {"acct_fmtd": "1-100", "fisc_prd": 1, "amount": 100},
        {"acct_fmtd": "1-100", "fisc_prd": 2, "amount": 50},
        {"acct_fmtd": "1-100", "fisc_prd": 2, "amount": 25},  # duplicate rows sum
        {"acct_fmtd": "1-100", "fisc_prd": 3, "amount": 999},  # after target period
        {"acct_fmtd": "X-404", "fisc_prd": 1, "amount": 1},
    ]
    monkeypatch.setattr(sql_connector, "pull_trial_balance", lambda c, fy, prd: rows)
    p2 = period_of(fy2025, 2)

    imported, updated, errors = tb_svc.import_from_connector(db, conn.id, fy2025.id, p2.id, 2025, 2)
    assert (imported, updated) == (1, 0)
    assert any("X-404" in e for e in errors)
    e = db.query(TrialBalanceEntry).filter_by(account_id=acct.id, period_id=p2.id).one()
    assert Decimal(e.period_credit) == 75
    assert Decimal(e.ytd_credit) == 175
    assert Decimal(e.opening_debit) == 1000

    imported, updated, _ = tb_svc.import_from_connector(db, conn.id, fy2025.id, p2.id, 2025, 2)
    assert (imported, updated) == (0, 1)


@pytest.mark.parametrize("path,params", [
    ("trial-balance", {}), ("leadsheets", {}), ("je-schedule", {"entry_type": "reclassifying"}),
])
def test_working_paper_excel_exports(client, auth, data, path, params):
    p = {"format": "xlsx", **params}
    p["fiscal_year_id" if path == "je-schedule" else "period_id"] = (
        data["fy25"].id if path == "je-schedule" else data["p3"].id)
    r = client.get(f"/api/v1/working-papers/{path}", params=p, headers=auth("viewer"))
    assert r.status_code == 200, r.text
    assert r.content[:2] == b"PK"


def test_money_is_exact_in_json(client, auth, data):
    rows = client.get("/api/v1/working-papers/trial-balance", params={"period_id": data["p3"].id},
                      headers=auth("viewer")).json()
    assert isinstance(rows[0]["final_balance"], str)


def test_working_paper_package(client, auth, db, users, data):
    import io
    import zipfile

    from app.services.builtin_templates import seed_templates

    seed_templates(db, users["admin"].id)
    r = client.get("/api/v1/working-papers/package", params={"period_id": data["p3"].id}, headers=auth("viewer"))
    assert r.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "01_Working_Trial_Balance.xlsx" in names and "README.txt" in names
    assert any(n.startswith("Statements/") and "Financial_Position" in n for n in names)
    assert client.get("/api/v1/working-papers/package", params={"period_id": 999},
                      headers=auth("viewer")).status_code == 404
