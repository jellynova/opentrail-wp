"""Phase 7.3: period close, balance snapshot, reopen and fiscal-year roll forward."""
from __future__ import annotations

import io

from tests.conftest import add_je, add_tb, classify, make_account, make_scheme, period_of


def _upload(client, auth, fy, folder="/current/2025", username="officer"):
    return client.post(
        "/api/v1/documents/upload",
        data={"fiscal_year_id": str(fy.id), "folder_path": folder, "display_name": "cash.xlsx"},
        files={"file": ("cash.xlsx", io.BytesIO(b"xlsx"), "application/vnd.ms-excel")},
        headers=auth(username),
    )


def _signed_document(client, auth, fy):
    doc = _upload(client, auth, fy).json()
    client.post(f"/api/v1/documents/{doc['id']}/sign-off/preparer", headers=auth("officer"))
    client.post(f"/api/v1/documents/{doc['id']}/sign-off/reviewer", headers=auth("admin"))
    return doc


def test_close_blocked_by_unposted_journal_entry(client, auth, fy2025, users, db, documents_dir):
    period = period_of(fy2025, 3)
    account = make_account(db, fy2025, "1000", "Cash")
    add_tb(db, period, account, ytd=100)
    add_je(db, period, users["officer"], "adjusting", [(account, 5)], status="draft")

    r = client.post(f"/api/v1/periods/{period.id}/close", headers=auth("officer"))
    assert r.status_code == 400
    assert "not posted" in r.json()["detail"]["message"]


def test_close_blocked_by_unsigned_working_paper_and_force(client, auth, fy2025, users, db, documents_dir):
    period = period_of(fy2025, 3)
    account = make_account(db, fy2025, "1000", "Cash")
    add_tb(db, period, account, ytd=100)
    _upload(client, auth, fy2025)  # unsigned working paper for the current year

    r = client.post(f"/api/v1/periods/{period.id}/close", headers=auth("officer"))
    assert r.status_code == 400
    assert "not signed off" in r.json()["detail"]["message"]

    # An officer may not force the close...
    r = client.post(f"/api/v1/periods/{period.id}/close", json={"force": True}, headers=auth("officer"))
    assert r.status_code == 403

    # ...a finance_admin may, and the override is recorded.
    r = client.post(f"/api/v1/periods/{period.id}/close", json={"force": True, "notes": "audit agreed"}, headers=auth("admin"))
    assert r.status_code == 200, r.text
    assert r.json()["overrides"] and "cash.xlsx" in r.json()["overrides"]


def test_close_snapshots_closing_balances(client, auth, fy2025, users, db, documents_dir):
    period = period_of(fy2025, 3)
    cash = make_account(db, fy2025, "1000", "Cash")
    revenue = make_account(db, fy2025, "4000", "Revenue")
    add_tb(db, period, cash, opening=1000, ytd=500)
    add_tb(db, period, revenue, opening=-1000, ytd=-500)

    # AJE: debit cash 200 / credit revenue 200; RJE: move 50 back.
    add_je(db, period, users["officer"], "adjusting", [(cash, 200), (revenue, -200)])
    add_je(db, period, users["officer"], "reclassifying", [(cash, -50), (revenue, 50)])
    _signed_document(client, auth, fy2025)

    r = client.post(f"/api/v1/periods/{period.id}/close", headers=auth("officer"))
    assert r.status_code == 200, r.text
    close = r.json()
    assert close["is_balanced"] is True
    assert close["journal_entry_count"] == 2
    assert close["closed_by_username"] == "officer"

    balances = {b["acct_fmtd"]: b for b in close["balances"]}
    # Cash: 1000 opening + 500 YTD + 200 AJE − 50 RJE = 1650
    assert float(balances["1000"]["closing"]) == 1650.0
    assert float(balances["1000"]["aje_debit"]) == 200.0
    assert float(balances["1000"]["rje_credit"]) == 50.0
    assert float(balances["4000"]["closing"]) == -1650.0

    # The snapshot is readable afterwards and the period is closed.
    snapshot = client.get(f"/api/v1/periods/{period.id}/close", headers=auth("viewer"))
    assert snapshot.status_code == 200
    assert snapshot.json()["id"] == close["id"]
    periods = client.get(f"/api/v1/fiscal-years/{fy2025.id}/periods", headers=auth("viewer")).json()
    assert next(p for p in periods if p["id"] == period.id)["is_closed"] is True

    # Closing twice is refused.
    assert client.post(f"/api/v1/periods/{period.id}/close", headers=auth("officer")).status_code == 400


def test_closed_period_freezes_trial_balance(client, auth, fy2025, users, db, documents_dir):
    period = period_of(fy2025, 3)
    account = make_account(db, fy2025, "1000", "Cash")
    add_tb(db, period, account, ytd=100)
    _signed_document(client, auth, fy2025)
    assert client.post(f"/api/v1/periods/{period.id}/close", headers=auth("officer")).status_code == 200

    entry = client.get("/api/v1/trial-balance", params={"period_id": period.id}, headers=auth("officer")).json()[0]
    r = client.put(
        f"/api/v1/trial-balance/{entry['id']}",
        json={"ytd_debit": "999", "version": entry["version"]},
        headers=auth("officer"),
    )
    assert r.status_code == 400
    assert "closed" in r.json()["detail"]

    # Reopen (admin only), then the edit goes through and bumps the version.
    assert client.post(f"/api/v1/periods/{period.id}/reopen", headers=auth("officer")).status_code == 403
    reopened = client.post(
        f"/api/v1/periods/{period.id}/reopen", json={"reason": "late invoice"}, headers=auth("admin")
    )
    assert reopened.status_code == 200
    assert reopened.json()["is_closed"] is False

    r = client.put(
        f"/api/v1/trial-balance/{entry['id']}",
        json={"ytd_debit": "999", "version": entry["version"]},
        headers=auth("officer"),
    )
    assert r.status_code == 200
    assert r.json()["version"] == entry["version"] + 1


def test_close_fiscal_year_closes_every_period(client, auth, fy2025, users, db, documents_dir):
    account = make_account(db, fy2025, "1000", "Cash")
    add_tb(db, period_of(fy2025, 1), account, opening=1000, ytd=100)
    _signed_document(client, auth, fy2025)

    r = client.post(f"/api/v1/fiscal-years/{fy2025.id}/close", headers=auth("admin"))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "closed"

    periods = client.get(f"/api/v1/fiscal-years/{fy2025.id}/periods", headers=auth("viewer")).json()
    assert all(p["is_closed"] for p in periods)


def test_roll_forward_copies_coa_and_opens_with_prior_closing(client, auth, fy2025, users, db, documents_dir):
    cash = make_account(db, fy2025, "1000", "Cash", dept_code="FIN")
    revenue = make_account(db, fy2025, "4000", "Revenue")
    scheme = make_scheme(db, "PSAB")
    classify(db, scheme, cash, "financial_assets")
    classify(db, scheme, revenue, "revenue")

    period = period_of(fy2025, 12)
    add_tb(db, period, cash, opening=1000, ytd=500)
    add_tb(db, period, revenue, opening=-1000, ytd=-500)
    add_je(db, period, users["officer"], "adjusting", [(cash, 250), (revenue, -250)])
    _signed_document(client, auth, fy2025)
    assert client.post(f"/api/v1/fiscal-years/{fy2025.id}/close", headers=auth("admin")).status_code == 200

    r = client.post(f"/api/v1/fiscal-years/{fy2025.id}/roll-forward", headers=auth("admin"))
    assert r.status_code == 200, r.text
    summary = r.json()
    assert summary["fiscal_year"]["label"] == "2026"
    assert summary["periods_created"] == 12
    assert summary["accounts_copied"] == 2
    assert summary["classifications_copied"] == 2
    assert summary["opening_balances_posted"] == 2
    assert summary["balanced"] is True

    new_fy_id = summary["fiscal_year"]["id"]
    periods = client.get(f"/api/v1/fiscal-years/{new_fy_id}/periods", headers=auth("viewer")).json()
    first = next(p for p in periods if p["period_number"] == 1)
    assert first["is_closed"] is False

    accounts = client.get("/api/v1/accounts", params={"fiscal_year_id": new_fy_id}, headers=auth("viewer")).json()
    by_code = {a["acct_fmtd"]: a for a in accounts}
    assert set(by_code) == {"1000", "4000"}
    assert by_code["1000"]["dept_code"] == "FIN"

    entries = client.get("/api/v1/trial-balance", params={"period_id": first["id"]}, headers=auth("officer")).json()
    # Cash closing 1000 + 500 + 250 = 1750 as an opening debit; revenue is the credit side.
    cash_entry = next(e for e in entries if e["account_id"] == by_code["1000"]["id"])
    assert float(cash_entry["opening_debit"]) == 1750.0
    assert float(cash_entry["opening_credit"]) == 0.0
    assert cash_entry["source"] == "roll_forward"

    # Rolling forward again would collide with the new year.
    again = client.post(f"/api/v1/fiscal-years/{fy2025.id}/roll-forward", headers=auth("admin"))
    assert again.status_code == 400

    # Only a finance_admin may roll forward, and only a closed year.
    assert client.post(f"/api/v1/fiscal-years/{new_fy_id}/roll-forward", headers=auth("admin")).status_code == 400
    assert client.post(f"/api/v1/fiscal-years/{fy2025.id}/roll-forward", headers=auth("officer")).status_code == 403


def test_close_check_endpoint_reports_blockers(client, auth, fy2025, users, db, documents_dir):
    period = period_of(fy2025, 4)
    account = make_account(db, fy2025, "1000", "Cash")
    add_tb(db, period, account, ytd=10)
    add_je(db, period, users["officer"], "adjusting", [(account, 1)], status="draft")
    _upload(client, auth, fy2025)

    r = client.get(f"/api/v1/periods/{period.id}/close-check", headers=auth("officer"))
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is False
    assert len(body["unposted_journal_entries"]) == 1
    assert [d["state"] for d in body["unsigned_documents"]] == ["draft"]
