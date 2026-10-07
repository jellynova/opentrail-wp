import pytest

from app.core.config import settings
from tests.conftest import make_account, make_fiscal_year, period_of

URL = "/api/v1/journal-entries"


@pytest.fixture()
def setup(db, fy2025):
    cash = make_account(db, fy2025, "1-100", "Cash")
    rev = make_account(db, fy2025, "4-100", "Taxation revenue")
    return {"fy": fy2025, "p3": period_of(fy2025, 3), "cash": cash, "rev": rev}


def _payload(s, debit="100.00", credit="100.00", **kw):
    body = {
        "period_id": s["p3"].id,
        "entry_date": "2025-03-31",
        "entry_type": "adjusting",
        "description": "Accrue tax revenue",
        "lines": [
            {"account_id": s["cash"].id, "debit": debit, "credit": "0"},
            {"account_id": s["rev"].id, "debit": "0", "credit": credit},
        ],
    }
    body.update(kw)
    return body


def test_create_assigns_sequential_reference_and_totals(client, auth, setup):
    r1 = client.post(URL, json=_payload(setup), headers=auth("officer"))
    r2 = client.post(URL, json=_payload(setup), headers=auth("officer"))
    r3 = client.post(URL, json=_payload(setup, entry_type="reclassifying"), headers=auth("officer"))
    assert r1.status_code == 201, r1.text
    assert r1.json()["reference"] == "AJE-001"
    assert r2.json()["reference"] == "AJE-002"
    assert r3.json()["reference"] == "RJE-001"
    body = r1.json()
    assert body["is_balanced"] is True
    assert float(body["total_debit"]) == 100.0


def test_explicit_reference_kept(client, auth, setup):
    r = client.post(URL, json=_payload(setup, reference="YE-ACCR-1"), headers=auth("officer"))
    assert r.json()["reference"] == "YE-ACCR-1"


@pytest.mark.parametrize(
    "line",
    [
        {"debit": "-5", "credit": "0"},
        {"debit": "5", "credit": "5"},
        {"debit": "0", "credit": "0"},
    ],
)
def test_invalid_lines_rejected(client, auth, setup, line):
    body = _payload(setup)
    body["lines"][0].update(line)
    assert client.post(URL, json=body, headers=auth("officer")).status_code == 422


def test_invalid_entry_type_rejected(client, auth, setup):
    assert client.post(URL, json=_payload(setup, entry_type="bogus"), headers=auth("officer")).status_code == 422


def test_unknown_or_cross_year_account_rejected(client, auth, db, setup):
    body = _payload(setup)
    body["lines"][0]["account_id"] = 9999
    assert client.post(URL, json=body, headers=auth("officer")).status_code == 400

    fy24 = make_fiscal_year(db, 2024)
    old = make_account(db, fy24, "1-100", "Cash (2024)")
    body = _payload(setup)
    body["lines"][0]["account_id"] = old.id
    r = client.post(URL, json=body, headers=auth("officer"))
    assert r.status_code == 400
    assert "fiscal year" in r.json()["detail"]


def test_closed_period_rejected(client, auth, db, setup):
    setup["p3"].is_closed = True
    db.commit()
    r = client.post(URL, json=_payload(setup), headers=auth("officer"))
    assert r.status_code == 400
    assert "closed" in r.json()["detail"]


def test_viewer_cannot_create(client, auth, setup):
    assert client.post(URL, json=_payload(setup), headers=auth("viewer")).status_code == 403


def test_unbalanced_blocked_by_default(client, auth, setup):
    jid = client.post(URL, json=_payload(setup, credit="90"), headers=auth("officer")).json()["id"]
    r = client.post(f"{URL}/{jid}/post", headers=auth("officer"))
    assert r.status_code == 400
    assert "not balanced" in r.json()["detail"]


def test_unbalanced_allowed_in_warn_mode(client, auth, setup, monkeypatch):
    monkeypatch.setattr(settings, "JE_BALANCE_ENFORCEMENT", "warn")
    jid = client.post(URL, json=_payload(setup, credit="90"), headers=auth("officer")).json()["id"]
    r = client.post(f"{URL}/{jid}/post", headers=auth("officer"))
    assert r.status_code == 200
    assert r.json()["status"] == "posted"
    assert r.json()["is_balanced"] is False


def test_full_lifecycle(client, auth, setup):
    jid = client.post(URL, json=_payload(setup), headers=auth("officer")).json()["id"]
    assert client.post(f"{URL}/{jid}/post", headers=auth("officer")).json()["status"] == "posted"
    # preparer cannot approve own entry
    assert client.post(f"{URL}/{jid}/approve", headers=auth("officer")).status_code == 403
    r = client.post(f"{URL}/{jid}/approve", headers=auth("officer2"))
    assert r.json()["status"] == "approved"
    # posted/approved entries can't be edited or deleted
    assert client.put(f"{URL}/{jid}", json={"description": "x"}, headers=auth("officer")).status_code == 400
    assert client.delete(f"{URL}/{jid}", headers=auth("officer")).status_code == 400
    # only admin can reopen an approved entry
    assert client.post(f"{URL}/{jid}/unpost", headers=auth("officer")).status_code == 403
    r = client.post(f"{URL}/{jid}/unpost", headers=auth("admin"))
    assert r.json()["status"] == "draft"
    assert r.json()["reviewed_by_user_id"] is None
    assert client.delete(f"{URL}/{jid}", headers=auth("officer")).status_code == 204
    assert client.get(f"{URL}/{jid}", headers=auth("officer")).status_code == 404


def test_update_replaces_lines(client, auth, setup):
    jid = client.post(URL, json=_payload(setup), headers=auth("officer")).json()["id"]
    new_lines = [
        {"account_id": setup["cash"].id, "debit": "250", "credit": "0"},
        {"account_id": setup["rev"].id, "debit": "0", "credit": "250"},
    ]
    r = client.put(f"{URL}/{jid}", json={"lines": new_lines}, headers=auth("officer"))
    assert r.status_code == 200
    assert len(r.json()["lines"]) == 2
    assert float(r.json()["total_credit"]) == 250.0


def test_list_filters(client, auth, setup):
    client.post(URL, json=_payload(setup), headers=auth("officer"))
    rje = client.post(URL, json=_payload(setup, entry_type="reclassifying"), headers=auth("officer")).json()
    client.post(f"{URL}/{rje['id']}/post", headers=auth("officer"))

    def ids(**params):
        return [e["id"] for e in client.get(URL, params=params, headers=auth("viewer")).json()]

    assert ids(entry_type="reclassifying") == [rje["id"]]
    assert ids(status="posted") == [rje["id"]]
    assert len(ids(fiscal_year_id=setup["fy"].id)) == 2
    assert ids(fiscal_year_id=9999) == []
