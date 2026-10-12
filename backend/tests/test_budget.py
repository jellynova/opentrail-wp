from decimal import Decimal

import pytest

from app.models.budget import BudgetLine, BudgetYear
from app.services import sql_connector
from tests.conftest import add_tb, classify, make_account, make_fiscal_year, make_scheme, period_of

API = "/api/v1"


@pytest.fixture()
def world(db, users):
    psab = make_scheme(db)
    fy24, fy25 = make_fiscal_year(db, 2024), make_fiscal_year(db, 2025)
    acc = {}
    for fy, y in ((fy24, 24), (fy25, 25)):
        for code, desc, cls, dept in [
            ("4-100", "Property taxes", "revenue.taxation", "Finance"),
            ("6-100", "Parks maintenance", "expense.recreation_culture", "Parks"),
            ("6-200", "Road repairs", "expense.transportation", "Roads"),
            ("6-300", "Snow removal", "expense.transportation", "Roads"),
        ]:
            acc[f"{code}/{y}"] = a = make_account(db, fy, code, desc, dept_code=dept)
            classify(db, psab, a, cls)
    # FY2024 actuals and adopted budget (prior-year figures for requests)
    for code, amt in (("4-100", -1000), ("6-100", 300), ("6-200", 400)):
        add_tb(db, period_of(fy24, 12), acc[f"{code}/24"], ytd=amt)
    by24 = BudgetYear(fiscal_year_id=fy24.id, label="2024", status="adopted", created_by=users["admin"].id)
    db.add(by24)
    db.flush()
    db.add(BudgetLine(budget_year_id=by24.id, account_id=acc["6-100/24"].id, approved_amount=280,
                      budget_type="operating"))
    db.commit()
    return {"fy24": fy24, "fy25": fy25, "acc": acc}


def _by(client, auth, world, **kw):
    r = client.post(f"{API}/budget-years", json={"fiscal_year_id": world["fy25"].id, "label": "2025 Budget", **kw},
                    headers=auth("admin"))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _status(client, auth, by_id, s):
    return client.put(f"{API}/budget-years/{by_id}", json={"status": s}, headers=auth("admin"))


def _request(client, auth, by_id, account, user="parks_mgr", **kw):
    return client.post(f"{API}/budget-years/{by_id}/requests",
                       json={"account_id": account.id, "proposed_amount": "320", **kw}, headers=auth(user))


def test_status_transitions(client, auth, world):
    by_id = _by(client, auth, world)
    assert _status(client, auth, by_id, "approved").status_code == 400
    assert _status(client, auth, by_id, "open").status_code == 200
    assert _status(client, auth, by_id, "under_review").status_code == 200
    assert _status(client, auth, by_id, "approved").status_code == 200
    r = _status(client, auth, by_id, "adopted")
    assert r.status_code == 400 and "no budget lines" in r.json()["detail"]
    assert client.put(f"{API}/budget-years/{by_id}", json={"status": "bogus"}, headers=auth("admin")).status_code == 422
    assert _status(client, auth, by_id, "open").status_code == 400  # two steps back


def test_request_workflow(client, auth, world):
    acc = world["acc"]
    by_id = _by(client, auth, world)
    assert _request(client, auth, by_id, acc["6-100/25"]).status_code == 400  # setup: managers wait
    _status(client, auth, by_id, "open")

    r = _request(client, auth, by_id, acc["6-100/25"])
    assert r.status_code == 201, r.text
    req = r.json()
    assert req["department"] == "Parks"  # defaulted from the user
    assert Decimal(req["prior_year_actual"]) == 300 and Decimal(req["prior_year_budget"]) == 280
    assert _request(client, auth, by_id, acc["6-200/25"], department="Roads").status_code == 403
    assert _request(client, auth, by_id, world["acc"]["6-100/24"]).status_code == 400  # wrong fiscal year

    # a manager cannot approve their own request by editing its status
    r = client.put(f"{API}/budget-requests/{req['id']}", json={"status": "approved", "proposed_amount": "330"},
                   headers=auth("parks_mgr"))
    assert r.status_code == 200 and r.json()["status"] == "draft" and Decimal(r.json()["proposed_amount"]) == 330
    # other managers can't touch it
    assert client.post(f"{API}/budget-requests/{req['id']}/submit", headers=auth("roads_mgr")).status_code == 403

    assert client.post(f"{API}/budget-requests/{req['id']}/submit", headers=auth("parks_mgr")).json()["status"] == "submitted"
    assert client.put(f"{API}/budget-requests/{req['id']}", json={"proposed_amount": "1"},
                      headers=auth("parks_mgr")).status_code == 400
    assert client.post(f"{API}/budget-requests/{req['id']}/approve", json={},
                       headers=auth("parks_mgr")).status_code == 403

    # return for revision, resubmit, approve at a lower amount => modified
    r = client.post(f"{API}/budget-requests/{req['id']}/return", json={"review_comment": "Add detail"},
                    headers=auth("officer"))
    assert r.json()["status"] == "draft" and r.json()["review_comment"] == "Add detail"
    client.post(f"{API}/budget-requests/{req['id']}/submit", headers=auth("parks_mgr"))
    r = client.post(f"{API}/budget-requests/{req['id']}/approve", json={"approved_amount": "300"},
                    headers=auth("officer"))
    assert r.json()["status"] == "modified" and Decimal(r.json()["approved_amount"]) == 300

    # roads manager sees only Roads requests
    roads = _request(client, auth, by_id, acc["6-200/25"], user="roads_mgr", proposed_amount="500").json()
    listed = client.get(f"{API}/budget-years/{by_id}/requests", headers=auth("roads_mgr")).json()
    assert [r["id"] for r in listed] == [roads["id"]]
    assert len(client.get(f"{API}/budget-years/{by_id}/requests", headers=auth("officer")).json()) == 2

    client.post(f"{API}/budget-requests/{roads['id']}/submit", headers=auth("roads_mgr"))
    r = client.post(f"{API}/budget-requests/{roads['id']}/reject", json={"review_comment": "Defer"},
                    headers=auth("admin"))
    assert r.json()["status"] == "rejected"


def test_finance_officer_cannot_review_own_request(client, auth, world):
    by_id = _by(client, auth, world, status="open")
    req = _request(client, auth, by_id, world["acc"]["6-100/25"], user="officer", department="Parks").json()
    client.post(f"{API}/budget-requests/{req['id']}/submit", headers=auth("officer"))
    assert client.post(f"{API}/budget-requests/{req['id']}/approve", json={},
                       headers=auth("officer")).status_code == 403
    assert client.post(f"{API}/budget-requests/{req['id']}/approve", json={},
                       headers=auth("officer2")).json()["status"] == "approved"


@pytest.fixture()
def adopted(client, auth, db, world):
    """2025 budget: requests consolidated, adopted; actuals through period 6 and 12."""
    acc = world["acc"]
    by_id = _by(client, auth, world, status="open")
    for account, user, amount in ((acc["6-100/25"], "parks_mgr", "300"), (acc["6-200/25"], "roads_mgr", "400"),
                                  (acc["6-300/25"], "roads_mgr", "100")):
        rid = _request(client, auth, by_id, account, user=user, proposed_amount=amount).json()["id"]
        client.post(f"{API}/budget-requests/{rid}/submit", headers=auth(user))
        client.post(f"{API}/budget-requests/{rid}/approve", json={}, headers=auth("officer"))
    rid = _request(client, auth, by_id, acc["4-100/25"], user="officer", department="Finance",
                   proposed_amount="1100").json()["id"]
    client.post(f"{API}/budget-requests/{rid}/submit", headers=auth("officer"))
    client.post(f"{API}/budget-requests/{rid}/approve", json={}, headers=auth("admin"))

    r = client.post(f"{API}/budget-years/{by_id}/consolidate", headers=auth("admin"))
    assert r.json() == {"lines": 4, "requests_pending_review": 0}
    for s in ("under_review", "approved", "adopted"):
        assert _status(client, auth, by_id, s).status_code == 200

    fy = world["fy25"]
    for code, amt in (("4-100", -1150), ("6-100", 360), ("6-200", 380), ("6-300", 130)):
        add_tb(db, period_of(fy, 12), acc[f"{code}/25"], ytd=amt)
    add_tb(db, period_of(fy, 6), acc["6-100/25"], ytd=100)
    return by_id


def test_adopted_budget_is_locked(client, auth, adopted, world):
    assert client.post(f"{API}/budget-years/{adopted}/consolidate", headers=auth("admin")).status_code == 400
    r = client.put(f"{API}/budget-years/{adopted}/lines",
                   json=[{"account_id": world["acc"]["6-100/25"].id, "approved_amount": "1"}], headers=auth("admin"))
    assert r.status_code == 400
    lines = client.get(f"{API}/budget-years/{adopted}/lines", headers=auth("viewer")).json()
    assert sorted(Decimal(l["approved_amount"]) for l in lines) == [100, 300, 400, 1100]


def test_variance_signs_and_status(client, auth, adopted):
    rep = client.get(f"{API}/budget-years/{adopted}/variance", headers=auth("viewer")).json()
    rows = {r["acct_fmtd"]: r for r in rep["rows"]}
    tax = rows["4-100"]
    assert tax["kind"] == "revenue" and Decimal(tax["ytd_actual"]) == 1150
    assert Decimal(tax["variance"]) == 50 and tax["status"] == "green"  # revenue above budget is favourable
    parks = rows["6-100"]
    assert Decimal(parks["ytd_actual"]) == 360 and Decimal(parks["variance"]) == -60
    assert Decimal(parks["variance_pct"]) == -20 and parks["status"] == "red"
    assert rows["6-200"]["status"] == "green"
    snow = rows["6-300"]
    assert Decimal(snow["variance_pct"]) == -30 and snow["status"] == "red"
    assert Decimal(rep["total_actual"]) == 1150 - 870 and Decimal(rep["total_budget"]) == 300

    lenient = client.get(f"{API}/budget-years/{adopted}/variance", params={"red_pct": 25},
                         headers=auth("viewer")).json()
    assert {r["acct_fmtd"]: r["status"] for r in lenient["rows"]}["6-100"] == "amber"


def test_variance_grouping_drilldown_and_period(client, auth, adopted, world):
    rep = client.get(f"{API}/budget-years/{adopted}/variance", params={"group_by": "department"},
                     headers=auth("viewer")).json()
    groups = {(g["group"], g["kind"]): g for g in rep["groups"]}
    roads = groups[("Roads", "expense")]
    assert Decimal(roads["amended_budget"]) == 500 and Decimal(roads["ytd_actual"]) == 510 and roads["accounts"] == 2

    drill = client.get(f"{API}/budget-years/{adopted}/variance", params={"department": "Roads"},
                       headers=auth("viewer")).json()
    assert [r["acct_fmtd"] for r in drill["rows"]] == ["6-200", "6-300"]

    p6 = period_of(world["fy25"], 6)
    mid = client.get(f"{API}/budget-years/{adopted}/variance", params={"period_id": p6.id},
                     headers=auth("viewer")).json()
    assert Decimal(mid["percent_of_year"]) == 50
    parks = next(r for r in mid["rows"] if r["acct_fmtd"] == "6-100")
    assert Decimal(parks["ytd_actual"]) == 100 and Decimal(parks["percent_used"]) == Decimal("33.3")

    by_class = client.get(f"{API}/budget-years/{adopted}/variance", params={"group_by": "classification"},
                          headers=auth("viewer")).json()
    assert {g["group"] for g in by_class["groups"]} == {"revenue.taxation", "expense.recreation_culture",
                                                        "expense.transportation"}


def test_amendments(client, auth, adopted, world):
    acc = world["acc"]
    url = f"{API}/budget-years/{adopted}/amendments"
    r = client.post(url, json={"rationale": "Storm damage", "lines": [
        {"account_id": acc["6-300/25"].id, "amount": "50"}, {"account_id": acc["6-200/25"].id, "amount": "-20"}]},
        headers=auth("officer"))
    assert r.status_code == 201, r.text
    am = r.json()
    assert am["amendment_number"] == 1 and am["status"] == "draft"

    # draft amendments don't change the amended budget
    rows = {r["acct_fmtd"]: r for r in client.get(f"{API}/budget-years/{adopted}/variance",
                                                  headers=auth("viewer")).json()["rows"]}
    assert Decimal(rows["6-300"]["amended_budget"]) == 100

    assert client.post(f"{API}/budget-amendments/{am['id']}/approve", json={}, headers=auth("officer")).status_code == 403
    assert client.post(f"{API}/budget-amendments/{am['id']}/approve", json={}, headers=auth("admin")).status_code == 400
    r = client.post(f"{API}/budget-amendments/{am['id']}/approve",
                    json={"approval_reference": "Bylaw 1234, 2025", "approved_date": "2025-07-15"}, headers=auth("admin"))
    assert r.json()["status"] == "approved" and r.json()["approved_date"] == "2025-07-15"
    assert client.delete(f"{API}/budget-amendments/{am['id']}", headers=auth("admin")).status_code == 400

    rows = {r["acct_fmtd"]: r for r in client.get(f"{API}/budget-years/{adopted}/variance",
                                                  headers=auth("viewer")).json()["rows"]}
    snow = rows["6-300"]
    assert Decimal(snow["original_budget"]) == 100 and Decimal(snow["amended_budget"]) == 150
    assert Decimal(snow["variance"]) == 20 and snow["status"] == "green"
    assert Decimal(rows["6-200"]["amended_budget"]) == 380

    second = client.post(url, json={"lines": [{"account_id": acc["6-100/25"].id, "amount": "5"}]},
                         headers=auth("officer")).json()
    assert second["amendment_number"] == 2


def test_amendments_require_adopted_budget(client, auth, world):
    by_id = _by(client, auth, world, status="open")
    r = client.post(f"{API}/budget-years/{by_id}/amendments",
                    json={"lines": [{"account_id": world["acc"]["6-100/25"].id, "amount": "5"}]}, headers=auth("officer"))
    assert r.status_code == 400


def test_statement_of_operations_amended_budget(client, auth, db, adopted, world):
    """The report engine's budget column honours budget_version."""
    from app.services.report_engine import generate

    client.post(f"{API}/budget-years/{adopted}/amendments", json={
        "approval_reference": "Bylaw 9", "lines": [{"account_id": world["acc"]["6-100/25"].id, "amount": "40"}]},
        headers=auth("officer"))
    am_id = client.get(f"{API}/budget-years/{adopted}/amendments", headers=auth("viewer")).json()[0]["id"]
    client.post(f"{API}/budget-amendments/{am_id}/approve", json={}, headers=auth("admin"))
    d = {"version": 2, "title": "t", "columns": [
        {"key": "o", "label": "o", "source": "budget"},
        {"key": "a", "label": "a", "source": "budget", "budget_version": "amended"}],
        "rows": [{"type": "accounts", "label": "Expenses", "classifications": ["expense*"]},
                 {"type": "accounts", "label": "Revenue", "classifications": ["revenue*"], "sign": -1}]}
    rows = {r["label"]: r["values"] for r in generate(db, d, world["fy25"].id)["rows"]}
    assert rows["Expenses"]["o"] == 800 and rows["Expenses"]["a"] == 840
    assert rows["Revenue"]["o"] == 1100


def test_multi_year_and_council_report(client, auth, adopted):
    my = client.get(f"{API}/budget-years/{adopted}/multi-year", params={"group_by": "department"},
                    headers=auth("viewer")).json()
    parks = next(g for g in my["rows"] if g["group"] == "Parks")
    assert Decimal(parks["current_budget"]) == 300 and Decimal(parks["prior_actual"]) == 300
    assert Decimal(parks["prior_budget"]) == 280

    rep = client.get(f"{API}/budget-years/{adopted}/council-report", headers=auth("viewer")).json()
    rows = {r["label"]: r for r in rep["rows"]}
    assert Decimal(rows["Total revenue"]["values"]["current_budget"]) == 1100
    assert Decimal(rows["Recreation and cultural services"]["values"]["change"]) == 20  # 300 vs 280
    assert Decimal(rows["Surplus (deficit) before transfers"]["values"]["current_budget"]) == 300

    for fmt, magic in (("xlsx", b"PK"),):
        r = client.get(f"{API}/budget-years/{adopted}/council-report", params={"format": fmt}, headers=auth("viewer"))
        assert r.content[:2] == magic
        r = client.get(f"{API}/budget-years/{adopted}/variance", params={"format": fmt, "group_by": "department"},
                       headers=auth("viewer"))
        assert r.status_code == 200 and r.content[:2] == magic


def test_budget_line_imports(client, auth, db, world, users, monkeypatch):
    from app.models.connector import ExternalConnector

    by_id = _by(client, auth, world)
    csv_body = b"Account,Amount\n4-100,\"1,200\"\n6-100,300\n6-100,50\n9-999,1\n"
    r = client.post(f"{API}/budget-years/{by_id}/lines/import/csv", files={"file": ("b.csv", csv_body, "text/csv")},
                    headers=auth("admin"))
    assert r.json()["lines"] == 2 and "9-999" in r.json()["errors"][0]
    lines = {l["account_id"]: Decimal(l["approved_amount"])
             for l in client.get(f"{API}/budget-years/{by_id}/lines", headers=auth("viewer")).json()}
    assert lines[world["acc"]["6-100/25"].id] == 350

    conn = ExternalConnector(name="AMAIS", system_type="amais", is_active=True, created_by_user_id=users["admin"].id)
    db.add(conn)
    db.commit()
    rows = [  # ERP sign convention: positive = credit
        {"acct_fmtd": "4-100", "rec_type": "B1", "amount": 1300},
        {"acct_fmtd": "6-100", "rec_type": "B1", "amount": -320},
        {"acct_fmtd": "6-100", "rec_type": "B2", "amount": -999},
    ]
    monkeypatch.setattr(sql_connector, "pull_budget", lambda c, fy: rows)
    r = client.post(f"{API}/budget-years/{by_id}/lines/import/connector",
                    json={"connector_id": conn.id, "fiscal_year": 2025, "rec_type": "B1"}, headers=auth("admin"))
    assert r.json() == {"lines": 2, "errors": []}
    lines = {l["account_id"]: Decimal(l["approved_amount"])
             for l in client.get(f"{API}/budget-years/{by_id}/lines", headers=auth("viewer")).json()}
    assert lines == {world["acc"]["4-100/25"].id: 1300, world["acc"]["6-100/25"].id: 320}
