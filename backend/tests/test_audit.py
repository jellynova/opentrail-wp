"""Phase 8: audit trail, activity feed and optimistic locking."""
from __future__ import annotations

import io

from tests.conftest import add_tb, make_account, period_of


def _create_je(client, auth, period, account_id, username="officer", amount=100):
    return client.post(
        "/api/v1/journal-entries",
        json={
            "period_id": period.id,
            "entry_date": str(period.end_date),
            "entry_type": "adjusting",
            "description": "accrual",
            "lines": [
                {"account_id": account_id, "debit": str(amount)},
                {"account_id": account_id, "credit": str(amount)},
            ],
        },
        headers=auth(username),
    )


def test_journal_entry_lifecycle_is_audited(client, auth, fy2025, users, db):
    period = period_of(fy2025, 3)
    account = client.post(
        "/api/v1/accounts",
        json={"fiscal_year_id": fy2025.id, "acct_fmtd": "1000", "description": "Cash"},
        headers=auth("officer"),
    ).json()

    entry = _create_je(client, auth, period, account['id'], amount=50).json()
    assert client.post(f"/api/v1/journal-entries/{entry['id']}/post", headers=auth("officer")).status_code == 200
    assert client.post(f"/api/v1/journal-entries/{entry['id']}/approve", headers=auth("admin")).status_code == 200
    assert client.post(f"/api/v1/journal-entries/{entry['id']}/unpost", headers=auth("admin")).status_code == 200
    assert client.delete(f"/api/v1/journal-entries/{entry['id']}", headers=auth("admin")).status_code == 204

    logs = client.get(
        "/api/v1/audit-logs",
        params={"resource_type": "journal_entry", "resource_id": entry["id"]},
        headers=auth("admin"),
    ).json()
    assert [item["action"] for item in logs["items"]] == ["delete", "unpost", "approve", "post", "create"]
    assert all(item["username"] for item in logs["items"])
    assert logs["items"][0]["description"].startswith("admin delete journal entry")
    # Line detail is captured, not just the header fields.
    created = next(i for i in logs["items"] if i["action"] == "create")
    assert created["new_values"]["lines"][0]["debit"] == "50.00"
    assert logs["has_more"] is False


def test_audit_log_filters_and_roles(client, auth, fy2025, users, db):
    period = period_of(fy2025, 3)
    account = client.post(
        "/api/v1/accounts",
        json={"fiscal_year_id": fy2025.id, "acct_fmtd": "1000", "description": "Cash"},
        headers=auth("officer"),
    ).json()
    _create_je(client, auth, period, account['id'])

    # Viewers cannot read the audit trail.
    assert client.get("/api/v1/audit-logs", headers=auth("viewer")).status_code == 403

    by_action = client.get("/api/v1/audit-logs", params={"action": "create"}, headers=auth("officer")).json()
    assert {i["resource_type"] for i in by_action["items"]} == {"account", "journal_entry"}

    by_user = client.get("/api/v1/audit-logs", params={"user_id": users["officer"].id}, headers=auth("officer")).json()
    assert by_user["items"] and all(i["user_id"] == users["officer"].id for i in by_user["items"])

    by_date = client.get(
        "/api/v1/audit-logs", params={"date_from": "2000-01-01", "date_to": "2000-01-02"}, headers=auth("officer")
    ).json()
    assert by_date["items"] == []

    page = client.get("/api/v1/audit-logs", params={"limit": 1}, headers=auth("officer")).json()
    assert len(page["items"]) == 1
    assert page["has_more"] is True

    csv = client.get("/api/v1/audit-logs/export", headers=auth("officer"))
    assert csv.status_code == 200
    assert csv.headers["content-type"].startswith("text/csv")
    body = csv.text
    assert "Timestamp,User,Action,Resource type,Resource id,IP address,Description" in body
    assert "journal_entry" in body


def test_password_change_is_audited_without_secrets(client, auth, fy2025, users, db):
    r = client.put(
        f"/api/v1/users/{users['officer'].id}/password",
        json={"new_password": "s3cret-new-pw"},
        headers=auth("admin"),
    )
    assert r.status_code == 204

    logs = client.get("/api/v1/audit-logs", params={"action": "password_change"}, headers=auth("admin")).json()
    assert logs["items"]
    dumped = str(logs["items"][0])
    assert "s3cret-new-pw" not in dumped
    assert "hashed_password" not in dumped


def test_audit_values_are_json_safe(client, auth, fy2025, users, db, documents_dir):
    client.post(
        "/api/v1/documents/upload",
        data={"fiscal_year_id": str(fy2025.id), "folder_path": "/permanent"},
        files={"file": ("bylaw.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
        headers=auth("officer"),
    )
    logs = client.get("/api/v1/audit-logs", params={"resource_type": "document"}, headers=auth("admin")).json()
    item = logs["items"][0]
    assert item["action"] == "upload"
    assert item["new_values"]["folder_path"] == "/permanent"


def test_optimistic_locking_on_trial_balance(client, auth, fy2025, users, db):
    period = period_of(fy2025, 3)
    account = make_account(db, fy2025, "1000", "Cash")
    add_tb(db, period, account, ytd=100)

    entry = client.get("/api/v1/trial-balance", params={"period_id": period.id}, headers=auth("officer")).json()[0]
    first = client.put(
        f"/api/v1/trial-balance/{entry['id']}",
        json={"ytd_debit": "150", "version": entry["version"]},
        headers=auth("officer"),
    )
    assert first.status_code == 200
    assert first.json()["version"] == 2

    stale = client.put(
        f"/api/v1/trial-balance/{entry['id']}",
        json={"ytd_debit": "999", "version": entry["version"]},
        headers=auth("officer2"),
    )
    assert stale.status_code == 409
    assert "changed by someone else" in stale.json()["detail"]
    assert stale.headers["x-conflict-reason"] == "stale-version"

    # Omitting the version keeps the old last-write-wins behaviour (backwards compatible).
    no_version = client.put(
        f"/api/v1/trial-balance/{entry['id']}", json={"ytd_debit": "160"}, headers=auth("officer")
    )
    assert no_version.status_code == 200


def test_optimistic_locking_on_budget_request(client, auth, fy2025, users, db):
    scheme = client.get("/api/v1/mapping-schemes", headers=auth("admin")).json()
    assert scheme == []
    account = client.post(
        "/api/v1/accounts",
        json={"fiscal_year_id": fy2025.id, "acct_fmtd": "5100", "description": "Supplies"},
        headers=auth("officer"),
    ).json()
    by = client.post(
        "/api/v1/budget-years",
        json={"fiscal_year_id": fy2025.id, "label": "2025 Budget"},
        headers=auth("admin"),
    ).json()
    client.put(f"/api/v1/budget-years/{by['id']}", json={"status": "open"}, headers=auth("admin"))

    req = client.post(
        f"/api/v1/budget-years/{by['id']}/requests",
        json={"account_id": account["id"], "department": "Parks", "proposed_amount": "1000"},
        headers=auth("admin"),
    ).json()
    assert req["version"] == 1

    first = client.put(
        f"/api/v1/budget-requests/{req['id']}",
        json={"proposed_amount": "1200", "version": 1},
        headers=auth("admin"),
    )
    assert first.status_code == 200
    assert first.json()["version"] == 2

    stale = client.put(
        f"/api/v1/budget-requests/{req['id']}",
        json={"proposed_amount": "5000", "version": 1},
        headers=auth("admin"),
    )
    assert stale.status_code == 409
    # The stale write did not land.
    assert client.get(f"/api/v1/budget-years/{by['id']}/requests", headers=auth("admin")).json()[0][
        "proposed_amount"
    ] == "1200.00"


def test_concurrent_writers_cannot_both_win(engine, fy2025, db):
    """Both writers load version 1 and pass the application check; the database-level
    version condition makes the second UPDATE fail instead of silently overwriting."""
    import pytest
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.orm.exc import StaleDataError

    from app.models.trial_balance import TrialBalanceEntry
    from app.services import locking

    add_tb(db, period_of(fy2025, 1), make_account(db, fy2025, "1000", "Cash"), ytd=100)
    entry_id = db.query(TrialBalanceEntry).one().id

    S = sessionmaker(bind=engine)
    a, b = S(), S()
    ea, eb = a.get(TrialBalanceEntry, entry_id), b.get(TrialBalanceEntry, entry_id)
    for session, entry, amount in ((a, ea, 150), (b, eb, 175)):
        locking.check_version(entry, 1, "trial balance entry")
        entry.ytd_debit = amount
        locking.bump(entry)
    a.commit()
    with pytest.raises(StaleDataError):
        b.commit()
    a.close(), b.close()
    db.expire_all()
    assert float(db.get(TrialBalanceEntry, entry_id).ytd_debit) == 150


def test_stale_write_maps_to_409(client):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm.exc import StaleDataError

    from app.main import app

    @app.get("/__test_stale")
    def _boom():
        raise StaleDataError("simulated")

    try:
        r = TestClient(app).get("/__test_stale")
        assert r.status_code == 409 and r.headers["x-conflict-reason"] == "stale-version"
    finally:
        app.router.routes = [rt for rt in app.router.routes if getattr(rt, "path", "") != "/__test_stale"]
