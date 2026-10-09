"""Leadsheet-to-document account links and fiscal-year reopen (phases 7-8)."""
from __future__ import annotations

import io

import pytest

from app.models.document_links import DocumentAccountLink
from app.services.audit import snapshot
from tests.conftest import add_tb, make_account, period_of


def _upload(client, auth, fy, display="cash lead.pdf", folder="/current/2025", username="officer"):
    return client.post(
        "/api/v1/documents/upload",
        data={"fiscal_year_id": str(fy.id), "folder_path": folder, "display_name": display},
        files={"file": ("cash lead.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf")},
        headers=auth(username),
    )


# ── Account links CRUD ───────────────────────────────────────────────────────


def test_add_list_and_remove_account_link(client, auth, fy2025, users, db, documents_dir):
    doc = _upload(client, auth, fy2025).json()

    r = client.post(
        f"/api/v1/working-papers/{doc['id']}/account-links",
        json={"account_code": "1-100", "fiscal_year_id": fy2025.id},
        headers=auth("officer"),
    )
    assert r.status_code == 201, r.text
    link = r.json()
    assert link["account_code"] == "1-100"
    assert link["working_paper_id"] == doc["id"]
    assert link["fiscal_year_id"] == fy2025.id
    assert link["created_by_username"] == "officer"
    assert link["document_display_name"] == "cash lead.pdf"

    # Listing works for any authenticated user.
    listed = client.get(f"/api/v1/working-papers/{doc['id']}/account-links", headers=auth("viewer"))
    assert listed.status_code == 200
    assert [l["id"] for l in listed.json()] == [link["id"]]

    # Duplicate (working_paper_id, account_code) is rejected.
    dup = client.post(
        f"/api/v1/working-papers/{doc['id']}/account-links",
        json={"account_code": "1-100", "fiscal_year_id": fy2025.id},
        headers=auth("admin"),
    )
    assert dup.status_code == 409

    # A second code on the same document is fine.
    r2 = client.post(
        f"/api/v1/working-papers/{doc['id']}/account-links",
        json={"account_code": "2-100", "fiscal_year_id": fy2025.id},
        headers=auth("admin"),
    )
    assert r2.status_code == 201

    # Remove requires officer and above.
    forbidden = client.delete(
        f"/api/v1/working-papers/{doc['id']}/account-links/{r2.json()['id']}", headers=auth("viewer")
    )
    assert forbidden.status_code == 403

    removed = client.delete(
        f"/api/v1/working-papers/{doc['id']}/account-links/{r2.json()['id']}", headers=auth("officer")
    )
    assert removed.status_code == 204
    remaining = client.get(f"/api/v1/working-papers/{doc['id']}/account-links", headers=auth("viewer")).json()
    assert [l["account_code"] for l in remaining] == ["1-100"]


def test_account_link_role_checks(client, auth, fy2025, documents_dir):
    doc = _upload(client, auth, fy2025).json()
    r = client.post(
        f"/api/v1/working-papers/{doc['id']}/account-links",
        json={"account_code": "1-100", "fiscal_year_id": fy2025.id},
        headers=auth("viewer"),
    )
    assert r.status_code == 403
    r = client.post(
        f"/api/v1/working-papers/{doc['id']}/account-links",
        json={"account_code": "1-100", "fiscal_year_id": fy2025.id},
        headers=auth("parks_mgr"),
    )
    assert r.status_code == 403


def test_account_link_validation(client, auth, fy2025, documents_dir):
    doc = _upload(client, auth, fy2025).json()
    # Unknown working paper
    r = client.post(
        "/api/v1/working-papers/99999/account-links",
        json={"account_code": "1-100", "fiscal_year_id": fy2025.id},
        headers=auth("officer"),
    )
    assert r.status_code == 404
    # Unknown fiscal year
    r = client.post(
        f"/api/v1/working-papers/{doc['id']}/account-links",
        json={"account_code": "1-100", "fiscal_year_id": 99999},
        headers=auth("officer"),
    )
    assert r.status_code == 404
    # Blank code
    r = client.post(
        f"/api/v1/working-papers/{doc['id']}/account-links",
        json={"account_code": "   ", "fiscal_year_id": fy2025.id},
        headers=auth("officer"),
    )
    assert r.status_code == 400


def test_remove_account_link_wrong_document_404(client, auth, fy2025, documents_dir):
    d1 = _upload(client, auth, fy2025, display="one.pdf").json()
    d2 = _upload(client, auth, fy2025, display="two.pdf").json()
    link = client.post(
        f"/api/v1/working-papers/{d1['id']}/account-links",
        json={"account_code": "1-100", "fiscal_year_id": fy2025.id},
        headers=auth("officer"),
    ).json()
    r = client.delete(f"/api/v1/working-papers/{d2['id']}/account-links/{link['id']}", headers=auth("officer"))
    assert r.status_code == 404


def test_by_account_lookup(client, auth, fy2025, db, documents_dir):
    d1 = _upload(client, auth, fy2025, display="bank rec").json()
    d2 = _upload(client, auth, fy2025, display="ap listing").json()
    for doc, code in ((d1, "1-100"), (d2, "1-100"), (d2, "2-100")):
        r = client.post(
            f"/api/v1/working-papers/{doc['id']}/account-links",
            json={"account_code": code, "fiscal_year_id": fy2025.id},
            headers=auth("officer"),
        )
        assert r.status_code == 201, r.text

    r = client.get("/api/v1/working-papers/by-account/1-100", headers=auth("viewer"))
    assert r.status_code == 200
    docs = {l["working_paper_id"] for l in r.json()}
    assert docs == {d1["id"], d2["id"]}
    assert all(l["account_code"] == "1-100" for l in r.json())

    # Scoped to the fiscal year, and empty for unknown codes.
    scoped = client.get(
        "/api/v1/working-papers/by-account/1-100", params={"fiscal_year_id": fy2025.id}, headers=auth("viewer")
    )
    assert scoped.status_code == 200 and len(scoped.json()) == 2
    none = client.get("/api/v1/working-papers/by-account/9-999", headers=auth("viewer"))
    assert none.status_code == 200 and none.json() == []


def test_account_links_are_audited(client, auth, fy2025, documents_dir):
    doc = _upload(client, auth, fy2025).json()
    link = client.post(
        f"/api/v1/working-papers/{doc['id']}/account-links",
        json={"account_code": "1-100", "fiscal_year_id": fy2025.id},
        headers=auth("officer"),
    ).json()
    client.delete(f"/api/v1/working-papers/{doc['id']}/account-links/{link['id']}", headers=auth("officer"))

    r = client.get(
        "/api/v1/audit-logs",
        params={"resource_type": "document_account_link"},
        headers=auth("admin"),
    )
    assert r.status_code == 200
    actions = [e["action"] for e in r.json()["items"]]
    assert "create" in actions and "delete" in actions


# ── Fiscal-year reopen ───────────────────────────────────────────────────────


def _close_year(client, auth, fy):
    # Signed document so the close checks pass.
    doc = _upload(client, auth, fy, display="fy sign off.pdf").json()
    client.post(f"/api/v1/documents/{doc['id']}/sign-off/preparer", headers=auth("officer"))
    client.post(f"/api/v1/documents/{doc['id']}/sign-off/reviewer", headers=auth("admin"))
    r = client.post(f"/api/v1/fiscal-years/{fy.id}/close", headers=auth("admin"))
    assert r.status_code == 200, r.text


def test_reopen_fiscal_year_happy_path(client, auth, fy2025, users, db, documents_dir):
    _close_year(client, auth, fy2025)
    periods = client.get(f"/api/v1/fiscal-years/{fy2025.id}/periods", headers=auth("viewer")).json()
    assert all(p["is_closed"] for p in periods)

    r = client.post(
        f"/api/v1/fiscal-years/{fy2025.id}/reopen",
        json={"reason": "Late adjusting entry found"},
        headers=auth("admin"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "open"
    assert body["forced"] is False
    # Periods are NOT automatically reopened...
    assert body["periods_still_closed"] == 12
    assert len(body["closed_periods"]) == 12
    still = client.get(f"/api/v1/fiscal-years/{fy2025.id}/periods", headers=auth("viewer")).json()
    assert all(p["is_closed"] for p in still)

    # ...but each can now be reopened individually via the existing endpoint.
    first = next(p for p in body["closed_periods"] if p["period_number"] == 1)
    r = client.post(f"/api/v1/periods/{first['id']}/reopen", json={"reason": "fix Q1"}, headers=auth("admin"))
    assert r.status_code == 200, r.text
    assert r.json()["is_closed"] is False


def test_reopen_fiscal_year_requires_reason_and_admin(client, auth, fy2025, documents_dir):
    _close_year(client, auth, fy2025)

    # Wrong role.
    r = client.post(
        f"/api/v1/fiscal-years/{fy2025.id}/reopen", json={"reason": "x"}, headers=auth("officer")
    )
    assert r.status_code == 403

    # Missing reason is a validation error.
    r = client.post(f"/api/v1/fiscal-years/{fy2025.id}/reopen", json={}, headers=auth("admin"))
    assert r.status_code == 422


def test_reopen_fiscal_year_open_year_blocked(client, auth, fy2025, documents_dir):
    r = client.post(
        f"/api/v1/fiscal-years/{fy2025.id}/reopen", json={"reason": "why"}, headers=auth("admin")
    )
    assert r.status_code == 400
    assert "already open" in r.json()["detail"]["message"]


def test_reopen_locked_year_requires_force(client, auth, fy2025, db, documents_dir):
    _close_year(client, auth, fy2025)
    fy2025.status = "locked"
    db.commit()

    # Without force: blocked.
    r = client.post(
        f"/api/v1/fiscal-years/{fy2025.id}/reopen", json={"reason": "audit adjustment"}, headers=auth("admin")
    )
    assert r.status_code == 400
    assert "locked" in r.json()["detail"]["message"]

    # With force: reopens, and the force flag lands in the audit trail.
    r = client.post(
        f"/api/v1/fiscal-years/{fy2025.id}/reopen",
        json={"reason": "audit adjustment", "force": True},
        headers=auth("admin"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "open"
    assert r.json()["forced"] is True

    from sqlalchemy import select

    from app.models.connector import AuditLog

    entries = db.scalars(
        select(AuditLog).where(AuditLog.resource_type == "fiscal_year", AuditLog.action == "reopen")
    ).all()
    assert entries, "reopen must be audited"
    new_values = [snapshot(e.new_values) if isinstance(e.new_values, dict) else (e.new_values or {}) for e in entries]
    assert any(v.get("forced") is True for v in new_values)


def test_reopen_fiscal_year_unknown_404(client, auth):
    r = client.post("/api/v1/fiscal-years/99999/reopen", json={"reason": "x"}, headers=auth("admin"))
    assert r.status_code == 404
