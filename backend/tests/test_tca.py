"""PS 3150 tangible capital asset schedule: continuity, CSV import, roll-forward, reconciliation."""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.tca import TcaScheduleLine
from tests.conftest import (
    add_tb, classify, make_account, make_fiscal_year, make_scheme, period_of,
)

CSV = (
    "Asset class,Cost opening,Additions,Disposals,Accumulated amortization opening,"
    "Amortization,Amortization disposals\n"
    'Land,1000000,0,0,0,0,0\n'
    'Buildings,2500000,"50,000",0,900000,"62,500",0\n'
    "Machinery & equipment,300000,\"(10,000)\",\"5,000\",120000,45000,2000\n"
)


def lines(client, auth, fy, **kw):
    return client.get("/api/v1/tca/lines", headers=auth("viewer"), params={"fiscal_year_id": fy.id, **kw}).json()


def test_manual_lines_compute_continuity(client, auth, fy2025):
    body = {"lines": [
        {"asset_class": "Buildings", "cost_opening": "2500000", "cost_additions": "50000",
         "amort_opening": "900000", "amort_expense": "62500"},
        {"asset_class": "Land", "cost_opening": "1000000"},
    ]}
    r = client.put(f"/api/v1/tca/lines?fiscal_year_id={fy2025.id}", headers=auth("officer"), json=body)
    assert r.status_code == 200, r.text
    assert r.json()["lines_saved"] == 2
    assert Decimal(r.json()["totals"]["cost_closing"]) == Decimal("3550000")
    assert Decimal(r.json()["totals"]["nbv_closing"]) == Decimal("2587500")  # 3550000 - 962500

    rows = {line["asset_class"]: line for line in lines(client, auth, fy2025)}
    b = rows["Buildings"]
    assert Decimal(b["cost_closing"]) == Decimal("2550000")
    assert Decimal(b["amort_closing"]) == Decimal("962500")
    assert Decimal(b["nbv_opening"]) == Decimal("1600000")
    assert Decimal(b["nbv_closing"]) == Decimal("1587500")
    assert b["source"] == "manual"

    # Duplicate asset classes are rejected rather than silently merged
    dup = {"lines": [{"asset_class": "Land"}, {"asset_class": " land "}]}
    r = client.put(f"/api/v1/tca/lines?fiscal_year_id={fy2025.id}", headers=auth("officer"), json=dup)
    assert r.status_code == 400 and "Duplicate" in r.json()["detail"]


def test_csv_import_handles_money_formats(client, auth, fy2025, db):
    r = client.post(
        f"/api/v1/tca/lines/import?fiscal_year_id={fy2025.id}", headers=auth("officer"),
        files={"file": ("tca.csv", CSV.encode(), "text/csv")},
    )
    assert r.status_code == 200 and r.json() == {"records_imported": 3, "errors": []}
    rows = {line["asset_class"]: line for line in lines(client, auth, fy2025)}
    assert set(rows) == {"Land", "Buildings", "Machinery & equipment"}
    m = rows["Machinery & equipment"]
    assert Decimal(m["cost_additions"]) == Decimal("-10000")  # (10,000) is negative
    assert Decimal(m["cost_disposals"]) == Decimal("5000")
    assert Decimal(m["amort_expense"]) == Decimal("45000")
    assert all(line["source"] == "csv" for line in rows.values())

    # Merge mode adds to what is already there
    again = client.post(
        f"/api/v1/tca/lines/import?fiscal_year_id={fy2025.id}&replace=false", headers=auth("officer"),
        files={"file": ("tca.csv", b"Asset class,Cost opening\nLand,500\nNew class,10\n", "text/csv")},
    )
    assert again.json()["records_imported"] == 2
    rows = {line["asset_class"]: line for line in lines(client, auth, fy2025)}
    assert Decimal(rows["Land"]["cost_opening"]) == Decimal("1000500") and "New class" in rows


def test_csv_import_reports_bad_rows(client, auth, fy2025):
    r = client.post(
        f"/api/v1/tca/lines/import?fiscal_year_id={fy2025.id}", headers=auth("officer"),
        files={"file": ("tca.csv", b"Asset class,Cost opening\nBuildings,not-a-number\n,500\n", "text/csv")},
    )
    assert r.json()["records_imported"] == 0
    assert len(r.json()["errors"]) == 2

    r = client.post(
        f"/api/v1/tca/lines/import?fiscal_year_id={fy2025.id}", headers=auth("officer"),
        files={"file": ("tca.csv", b"Wrong,Header\n1,2\n", "text/csv")},
    )
    assert r.json()["records_imported"] == 0 and "No asset class column" in r.json()["errors"][0]


def test_schedule_report_layouts_and_export(client, auth, fy2025):
    client.post(
        f"/api/v1/tca/lines/import?fiscal_year_id={fy2025.id}", headers=auth("officer"),
        files={"file": ("tca.csv", CSV.encode(), "text/csv")},
    )
    report = client.get("/api/v1/tca/schedule", headers=auth("viewer"),
                        params={"fiscal_year_id": fy2025.id}).json()
    assert report["title"] == "Schedule of Tangible Capital Assets" and "PS 3150" in report["subtitle"]
    assert [c["key"] for c in report["columns"]][:4] == [
        "cost_opening", "cost_additions", "cost_disposals", "cost_closing"]
    assert [r["label"] for r in report["rows"]][:3] == ["Land", "Buildings", "Machinery & equipment"]
    total = report["rows"][-1]
    assert total["label"] == "Total" and total["style"]["bold"] is True
    assert Decimal(str(total["values"]["cost_closing"])) == Decimal("3835000")  # 1000k + 2550k + 285k

    summary = client.get("/api/v1/tca/schedule", headers=auth("viewer"),
                         params={"fiscal_year_id": fy2025.id, "layout": "summary"}).json()
    assert [c["key"] for c in summary["columns"]] == ["cost_closing", "amort_closing", "nbv_closing"]

    xlsx = client.get("/api/v1/tca/schedule", headers=auth("viewer"),
                      params={"fiscal_year_id": fy2025.id, "format": "xlsx"})
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    assert "TCA_Schedule_2025.xlsx" in xlsx.headers["content-disposition"]
    pdf = client.get("/api/v1/tca/schedule", headers=auth("viewer"),
                     params={"fiscal_year_id": fy2025.id, "format": "pdf"})
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_reconciliation_against_gl(client, auth, fy2025, db):
    scheme = make_scheme(db, "PSAB")
    cost = make_account(db, fy2025, "1-800", "Tangible capital assets — cost")
    amort = make_account(db, fy2025, "1-810", "Accumulated amortization")
    classify(db, scheme, cost, "non_financial_assets.tca_cost")
    classify(db, scheme, amort, "non_financial_assets.tca_amortization")
    period = period_of(fy2025, 12)
    add_tb(db, period, cost, opening=1000000, ytd=50000)     # opening cost + additions
    add_tb(db, period, amort, opening=-900000, ytd=-45000)   # opening accumulated amortization + amortization

    client.put(f"/api/v1/tca/lines?fiscal_year_id={fy2025.id}", headers=auth("officer"), json={"lines": [
        {"asset_class": "Buildings", "cost_opening": "1000000", "cost_additions": "50000",
         "amort_opening": "900000", "amort_expense": "45000"},
    ]})
    report = client.get("/api/v1/tca/schedule", headers=auth("viewer"),
                        params={"fiscal_year_id": fy2025.id}).json()
    rec = report["reconciliation"]
    assert rec["available"] is True and rec["agrees"] is True
    assert Decimal(rec["gl_cost"]) == Decimal("1050000")
    assert Decimal(rec["gl_accumulated_amortization"]) == Decimal("945000")

    # A schedule that does not agree with the GL is reported, not hidden
    client.put(f"/api/v1/tca/lines?fiscal_year_id={fy2025.id}", headers=auth("officer"), json={"lines": [
        {"asset_class": "Buildings", "cost_opening": "1000000", "cost_additions": "60000",
         "amort_opening": "900000", "amort_expense": "40000"},
    ]})
    rec = client.get("/api/v1/tca/schedule", headers=auth("viewer"),
                     params={"fiscal_year_id": fy2025.id}).json()["reconciliation"]
    assert rec["agrees"] is False
    assert Decimal(rec["cost_difference"]) == Decimal("10000")        # 1060000 vs 1050000
    assert Decimal(rec["amortization_difference"]) == Decimal("-5000")  # 940000 vs 945000


def test_reconciliation_unavailable_without_classifications(client, auth, fy2025, db):
    make_account(db, fy2025, "1-800", "Capital")
    report = client.get("/api/v1/tca/schedule", headers=auth("viewer"),
                        params={"fiscal_year_id": fy2025.id}).json()
    assert report["reconciliation"]["available"] is False


def test_roll_forward_carries_prior_year_closing(client, auth, fy2025, db, users):
    client.post(
        f"/api/v1/tca/lines/import?fiscal_year_id={fy2025.id}", headers=auth("officer"),
        files={"file": ("tca.csv", CSV.encode(), "text/csv")},
    )
    fy2026 = make_fiscal_year(db, 2026)
    # Nothing to carry forward into the year after next
    empty = client.post(f"/api/v1/tca/lines/roll-forward?fiscal_year_id={fy2025.id}", headers=auth("officer")).json()
    assert empty["prior_year"] is None and empty["warnings"]

    r = client.post(f"/api/v1/tca/lines/roll-forward?fiscal_year_id={fy2026.id}", headers=auth("officer"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["prior_year"] == "2025" and body["applied"] == 3 and body["created"] == 3 and body["warnings"] == []

    rows = {line["asset_class"]: line for line in lines(client, auth, fy2026)}
    b = rows["Buildings"]
    # Openings equal last year's closings, so net book value carries straight over
    assert Decimal(b["cost_opening"]) == Decimal("2550000")
    assert Decimal(b["amort_opening"]) == Decimal("962500")
    assert Decimal(b["nbv_opening"]) == Decimal("1587500") and Decimal(b["nbv_closing"]) == Decimal("1587500")
    assert b["source"] == "roll_forward"
    assert Decimal(lines(client, auth, fy2025)[0]["nbv_closing"]) >= 0  # prior year untouched


def test_locked_year_and_roles(client, auth, fy2025, db):
    assert client.get("/api/v1/tca/lines", headers=auth("viewer"), params={"fiscal_year_id": fy2025.id}).status_code == 200
    assert client.put(f"/api/v1/tca/lines?fiscal_year_id={fy2025.id}", headers=auth("viewer"),
                      json={"lines": []}).status_code == 403
    assert client.post(f"/api/v1/tca/lines/roll-forward?fiscal_year_id={fy2025.id}",
                       headers=auth("budget_manager" if False else "parks_mgr")).status_code == 403

    fy2025.status = "locked"
    db.commit()
    assert client.put(f"/api/v1/tca/lines?fiscal_year_id={fy2025.id}", headers=auth("admin"),
                      json={"lines": []}).status_code == 400
    assert client.post(f"/api/v1/tca/lines/roll-forward?fiscal_year_id={fy2025.id}",
                       headers=auth("admin")).status_code == 400
    assert client.get("/api/v1/tca/schedule", headers=auth("viewer"),
                      params={"fiscal_year_id": fy2025.id}).status_code == 200  # still readable
    assert client.put("/api/v1/tca/lines?fiscal_year_id=999", headers=auth("admin"),
                      json={"lines": []}).status_code == 404


def test_tca_changes_are_audited(client, auth, fy2025, db):
    from app.models.connector import AuditLog

    client.put(f"/api/v1/tca/lines?fiscal_year_id={fy2025.id}", headers=auth("officer"), json={"lines": [
        {"asset_class": "Land", "cost_opening": "100"},
    ]})
    entry = db.scalars(select(AuditLog).where(AuditLog.resource_type == "tca_schedule")).one()
    assert entry.action == "update" and entry.user_id is not None
    assert entry.resource_id == fy2025.id
    assert entry.new_values["lines"] == 1 and Decimal(str(entry.new_values["cost_closing"])) == Decimal("100.00")
