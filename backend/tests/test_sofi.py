from decimal import Decimal

import pytest

URL = "/api/v1/sofi"

SUPPLIERS_CSV = b"""Vendor Name,Amount
Acme Paving Ltd,"20,000.00"
ACME  PAVING LTD,"10,000.00"
BC Hydro,"$24,999.99"
Zed Consulting,"25,000.00"
Big Truck Co,"(1,000.00)"
Big Truck Co,"90,000"
,5
"""

PAYROLL_CSV = b"""Employee,Title,Remuneration,Expenses,Elected
Mayor Smith,Mayor,"40,000",1200,Y
Councillor Lee,Councillor,"18,000",300,yes
J. Doe,CAO,"165,000",4000,
A. Roe,Clerk,"75,000",500,
B. Poe,Operator,"60,000",0,
C. Koe,Director of Finance,"120,500.50",950,
"""


def _import(client, auth, fy, schedule_type, content, replace=True):
    return client.post(
        f"{URL}/entries/import",
        params={"fiscal_year_id": fy.id, "schedule_type": schedule_type, "replace": replace},
        files={"file": ("data.csv", content, "text/csv")},
        headers=auth("officer"),
    )


def _rows(sched):
    return {r["label"]: r for r in sched["rows"]}


def test_supplier_schedule(client, auth, fy2025):
    r = _import(client, auth, fy2025, "supplier_payment", SUPPLIERS_CSV)
    assert r.json()["records_imported"] == 6
    assert r.json()["errors"] == ["Row 8: missing name"]

    s = client.get(f"{URL}/schedules/supplier_payment", params={"fiscal_year_id": fy2025.id},
                   headers=auth("viewer")).json()
    rows = _rows(s)
    # same supplier aggregates across case/whitespace; exactly $25,000 is not "more than"
    assert Decimal(rows["Acme Paving Ltd"]["values"]["amount"]) == 30000
    assert Decimal(rows["Big Truck Co"]["values"]["amount"]) == 89000
    assert "Zed Consulting" not in rows and "BC Hydro" not in rows
    consolidated = next(r for r in s["rows"] if r["label"].startswith("Consolidated"))
    assert Decimal(consolidated["values"]["amount"]) == Decimal("49999.99")
    assert "(2 suppliers)" in consolidated["label"]
    assert Decimal(s["summary"]["total"]) == Decimal("168999.99")

    lowered = client.get(f"{URL}/schedules/supplier_payment",
                         params={"fiscal_year_id": fy2025.id, "threshold": 20000}, headers=auth("viewer")).json()
    assert "Zed Consulting" in _rows(lowered)


def test_import_replace_vs_append(client, auth, fy2025):
    _import(client, auth, fy2025, "supplier_payment", SUPPLIERS_CSV)
    _import(client, auth, fy2025, "supplier_payment", b"Supplier,Amount\nOnly One,100\n")
    entries = client.get(f"{URL}/entries", params={"fiscal_year_id": fy2025.id}, headers=auth("viewer")).json()
    assert [e["name"] for e in entries] == ["Only One"]
    _import(client, auth, fy2025, "supplier_payment", b"Supplier,Amount\nAnother,100\n", replace=False)
    assert len(client.get(f"{URL}/entries", params={"fiscal_year_id": fy2025.id}, headers=auth("viewer")).json()) == 2


def test_remuneration_schedule(client, auth, fy2025):
    _import(client, auth, fy2025, "employee_remuneration", PAYROLL_CSV)
    s = client.get(f"{URL}/schedules/employee_remuneration", params={"fiscal_year_id": fy2025.id},
                   headers=auth("viewer")).json()
    labels = [r["label"] for r in s["rows"]]
    # elected officials listed regardless of amount; staff only above $75,000
    assert labels.index("Councillor Lee") < labels.index("Mayor Smith") < labels.index("C. Koe") < labels.index("J. Doe")
    assert "A. Roe" not in labels and "B. Poe" not in labels
    rows = _rows(s)
    assert rows["J. Doe"]["text"]["position"] == "CAO"
    other = next(r for r in s["rows"] if r["label"].startswith("Consolidated"))
    assert Decimal(other["values"]["remuneration"]) == 135000 and Decimal(other["values"]["expenses"]) == 500
    total = rows["Total remuneration and expenses"]
    assert Decimal(total["values"]["remuneration"]) == Decimal("478500.50")
    assert s["summary"] == {"threshold": "75000", "elected_officials": 2, "employees_listed": 2,
                            "employees_consolidated": 2}


def test_guarantee_schedule_and_exports(client, auth, fy2025):
    empty = client.get(f"{URL}/schedules/guarantee_indemnity", params={"fiscal_year_id": fy2025.id},
                       headers=auth("viewer")).json()
    assert "has not given any guarantees" in empty["rows"][0]["label"]

    r = client.post(f"{URL}/entries", json={
        "fiscal_year_id": fy2025.id, "schedule_type": "guarantee_indemnity", "name": "Curling Club loan guarantee",
        "amount": "150000", "description": "Guarantee of club's credit union loan"}, headers=auth("officer"))
    assert r.status_code == 201
    x = client.get(f"{URL}/schedules/guarantee_indemnity",
                   params={"fiscal_year_id": fy2025.id, "format": "xlsx"}, headers=auth("viewer"))
    assert x.status_code == 200 and x.content[:2] == b"PK"
    assert "SOFI_guarantee_indemnity_2025.xlsx" in x.headers["content-disposition"]
    assert client.delete(f"{URL}/entries/{r.json()['id']}", headers=auth("viewer")).status_code == 403
    assert client.delete(f"{URL}/entries/{r.json()['id']}", headers=auth("officer")).status_code == 204


def test_pdf_export(client, auth, fy2025):
    pytest.importorskip("weasyprint")
    _import(client, auth, fy2025, "employee_remuneration", PAYROLL_CSV)
    r = client.get(f"{URL}/schedules/employee_remuneration",
                   params={"fiscal_year_id": fy2025.id, "format": "pdf"}, headers=auth("viewer"))
    assert r.status_code == 200 and r.content[:4] == b"%PDF"


def test_bad_input(client, auth, fy2025):
    assert _import(client, auth, fy2025, "supplier_payment", b"Foo,Bar\n1,2\n").json()["records_imported"] == 0
    assert client.get(f"{URL}/schedules/supplier_payment", params={"fiscal_year_id": 999},
                      headers=auth("viewer")).status_code == 404
    assert client.get(f"{URL}/schedules/nope", params={"fiscal_year_id": fy2025.id},
                      headers=auth("viewer")).status_code == 422
