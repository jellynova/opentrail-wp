"""Materiality thresholds and unsupported-material-account flagging."""
from __future__ import annotations

from decimal import Decimal

from tests.conftest import add_tb, make_account, make_scheme, period_of


def test_set_and_get_materiality(client, auth, fy2025):
    r = client.put(
        f"/api/v1/materiality/{fy2025.id}",
        json={"overall_materiality": "50000", "performance_materiality": "37500", "basis": "2% of total revenue"},
        headers=auth("officer"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert Decimal(body["overall_materiality"]) == 50000
    assert Decimal(body["performance_materiality"]) == 37500
    assert Decimal(body["flagging_threshold"]) == 37500  # performance wins when set
    assert body["set_by_username"] == "officer"

    fetched = client.get(f"/api/v1/materiality/{fy2025.id}", headers=auth("viewer"))
    assert fetched.status_code == 200
    assert Decimal(fetched.json()["overall_materiality"]) == 50000


def test_get_materiality_404_when_unset(client, auth, fy2025):
    r = client.get(f"/api/v1/materiality/{fy2025.id}", headers=auth("viewer"))
    assert r.status_code == 404


def test_flagging_threshold_falls_back_to_overall(client, auth, fy2025):
    r = client.put(
        f"/api/v1/materiality/{fy2025.id}", json={"overall_materiality": "10000"}, headers=auth("officer")
    )
    assert r.status_code == 200
    assert Decimal(r.json()["flagging_threshold"]) == 10000


def test_set_materiality_rejects_performance_over_overall(client, auth, fy2025):
    r = client.put(
        f"/api/v1/materiality/{fy2025.id}",
        json={"overall_materiality": "10000", "performance_materiality": "20000"},
        headers=auth("officer"),
    )
    assert r.status_code == 400


def test_set_materiality_rejects_non_positive_overall(client, auth, fy2025):
    r = client.put(f"/api/v1/materiality/{fy2025.id}", json={"overall_materiality": "0"}, headers=auth("officer"))
    assert r.status_code == 422


def test_set_materiality_role_check_and_404(client, auth, fy2025):
    forbidden = client.put(
        f"/api/v1/materiality/{fy2025.id}", json={"overall_materiality": "1000"}, headers=auth("viewer")
    )
    assert forbidden.status_code == 403
    unknown_fy = client.put("/api/v1/materiality/99999", json={"overall_materiality": "1000"}, headers=auth("officer"))
    assert unknown_fy.status_code == 404


def test_set_materiality_updates_in_place_and_audits(client, auth, fy2025, db):
    client.put(f"/api/v1/materiality/{fy2025.id}", json={"overall_materiality": "10000"}, headers=auth("officer"))
    r2 = client.put(f"/api/v1/materiality/{fy2025.id}", json={"overall_materiality": "25000"}, headers=auth("admin"))
    assert r2.status_code == 200
    assert Decimal(r2.json()["overall_materiality"]) == 25000
    # One row per fiscal year, not two.
    from app.models.materiality import Materiality
    rows = db.query(Materiality).filter(Materiality.fiscal_year_id == fy2025.id).all()
    assert len(rows) == 1

    audit = client.get("/api/v1/audit-logs", params={"resource_type": "materiality"}, headers=auth("admin"))
    actions = [e["action"] for e in audit.json()["items"]]
    assert "create" in actions and "update" in actions


def test_unsupported_material_accounts_flags_only_unlinked_material_balances(client, auth, fy2025, db):
    make_scheme(db)
    big_unlinked = make_account(db, fy2025, "1-100", "Cash")
    big_linked = make_account(db, fy2025, "4-100", "Taxation")
    small_unlinked = make_account(db, fy2025, "6-100", "Office supplies")
    p1 = period_of(fy2025, 1)
    add_tb(db, p1, big_unlinked, ytd=100000)
    add_tb(db, p1, big_linked, ytd=90000)
    add_tb(db, p1, small_unlinked, ytd=500)

    client.put(f"/api/v1/materiality/{fy2025.id}", json={"overall_materiality": "50000"}, headers=auth("officer"))

    # Link a supporting document to the "big_linked" account only.
    doc = client.post(
        "/api/v1/documents/upload",
        data={"fiscal_year_id": str(fy2025.id), "folder_path": "/current"},
        files={"file": ("tax.pdf", b"%PDF-1.4 x", "application/pdf")},
        headers=auth("officer"),
    ).json()
    client.post(
        f"/api/v1/working-papers/{doc['id']}/account-links",
        json={"account_code": "4-100", "fiscal_year_id": fy2025.id},
        headers=auth("officer"),
    )

    r = client.get(
        f"/api/v1/materiality/{fy2025.id}/unsupported-accounts",
        params={"period_id": p1.id},
        headers=auth("viewer"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert Decimal(body["threshold"]) == 50000
    assert body["threshold_basis"] == "overall_materiality"
    codes = [a["acct_fmtd"] for a in body["accounts"]]
    assert codes == ["1-100"]  # only the big, unlinked account -- linked and small ones excluded
    assert Decimal(body["accounts"][0]["excess"]) == 50000


def test_unsupported_material_accounts_empty_when_materiality_unset(client, auth, fy2025, db):
    make_account(db, fy2025, "1-100", "Cash")
    p1 = period_of(fy2025, 1)
    r = client.get(
        f"/api/v1/materiality/{fy2025.id}/unsupported-accounts", params={"period_id": p1.id}, headers=auth("viewer")
    )
    assert r.status_code == 200
    body = r.json()
    assert body["threshold"] is None
    assert body["accounts"] == []


def test_unsupported_material_accounts_uses_performance_materiality_when_set(client, auth, fy2025, db):
    make_scheme(db)
    account = make_account(db, fy2025, "1-100", "Cash")
    p1 = period_of(fy2025, 1)
    add_tb(db, p1, account, ytd=40000)

    client.put(
        f"/api/v1/materiality/{fy2025.id}",
        json={"overall_materiality": "50000", "performance_materiality": "37500"},
        headers=auth("officer"),
    )
    r = client.get(
        f"/api/v1/materiality/{fy2025.id}/unsupported-accounts", params={"period_id": p1.id}, headers=auth("viewer")
    )
    body = r.json()
    # $40,000 is below overall (50k) but above performance materiality (37.5k) -- flagged.
    assert body["threshold_basis"] == "performance_materiality"
    assert [a["acct_fmtd"] for a in body["accounts"]] == ["1-100"]


def test_unsupported_material_accounts_excludes_accounts_with_a_comment(client, auth, fy2025, db):
    """A comment explaining the variance counts as support, same as a document link."""
    make_scheme(db)
    commented = make_account(db, fy2025, "1-100", "Cash")
    uncommented = make_account(db, fy2025, "6-100", "Office supplies")
    p1 = period_of(fy2025, 1)
    add_tb(db, p1, commented, ytd=100000)
    add_tb(db, p1, uncommented, ytd=90000)

    client.put(f"/api/v1/materiality/{fy2025.id}", json={"overall_materiality": "50000"}, headers=auth("officer"))
    client.post(
        "/api/v1/working-papers/by-account/1-100/comments",
        json={"fiscal_year_id": fy2025.id, "text": "Variance due to the Q1 grant reimbursement, no document needed."},
        headers=auth("officer"),
    )

    r = client.get(
        f"/api/v1/materiality/{fy2025.id}/unsupported-accounts", params={"period_id": p1.id}, headers=auth("viewer")
    )
    codes = [a["acct_fmtd"] for a in r.json()["accounts"]]
    assert codes == ["6-100"]  # the commented account is excluded; the other remains flagged
