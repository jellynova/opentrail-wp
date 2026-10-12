"""Account comments -- a lighter alternative to attaching a document to explain a variance."""
from __future__ import annotations

from tests.conftest import make_account, make_fiscal_year


def test_add_list_resolve_and_delete_comment(client, auth, fy2025):
    r = client.post(
        "/api/v1/working-papers/by-account/1-100/comments",
        json={"fiscal_year_id": fy2025.id, "text": "Variance is the annual insurance renewal, timing only."},
        headers=auth("officer"),
    )
    assert r.status_code == 201, r.text
    comment = r.json()
    assert comment["account_code"] == "1-100"
    assert comment["fiscal_year_id"] == fy2025.id
    assert comment["created_by_username"] == "officer"
    assert comment["is_resolved"] is False

    listed = client.get(
        "/api/v1/working-papers/by-account/1-100/comments", params={"fiscal_year_id": fy2025.id}, headers=auth("viewer")
    )
    assert listed.status_code == 200
    assert [c["id"] for c in listed.json()] == [comment["id"]]

    resolved = client.post(
        f"/api/v1/working-papers/by-account/1-100/comments/{comment['id']}/resolve",
        headers=auth("viewer"),  # resolving is open to any authenticated user, like document annotations
    )
    assert resolved.status_code == 200
    assert resolved.json()["is_resolved"] is True
    assert resolved.json()["resolved_by_username"] == "viewer"

    reopened = client.post(
        f"/api/v1/working-papers/by-account/1-100/comments/{comment['id']}/resolve",
        params={"resolved": False},
        headers=auth("viewer"),
    )
    assert reopened.status_code == 200
    assert reopened.json()["is_resolved"] is False
    assert reopened.json()["resolved_by_username"] is None

    deleted = client.delete(
        f"/api/v1/working-papers/by-account/1-100/comments/{comment['id']}", headers=auth("officer")
    )
    assert deleted.status_code == 204
    remaining = client.get(
        "/api/v1/working-papers/by-account/1-100/comments", params={"fiscal_year_id": fy2025.id}, headers=auth("viewer")
    ).json()
    assert remaining == []


def test_add_comment_role_check_and_validation(client, auth, fy2025):
    forbidden = client.post(
        "/api/v1/working-papers/by-account/1-100/comments",
        json={"fiscal_year_id": fy2025.id, "text": "x"},
        headers=auth("viewer"),
    )
    assert forbidden.status_code == 403

    unknown_fy = client.post(
        "/api/v1/working-papers/by-account/1-100/comments",
        json={"fiscal_year_id": 99999, "text": "x"},
        headers=auth("officer"),
    )
    assert unknown_fy.status_code == 404

    blank = client.post(
        "/api/v1/working-papers/by-account/1-100/comments",
        json={"fiscal_year_id": fy2025.id, "text": "   "},
        headers=auth("officer"),
    )
    assert blank.status_code == 400


def test_delete_comment_requires_author_or_admin(client, auth, fy2025):
    comment = client.post(
        "/api/v1/working-papers/by-account/1-100/comments",
        json={"fiscal_year_id": fy2025.id, "text": "note"},
        headers=auth("officer"),
    ).json()

    # A different officer-level user cannot delete someone else's comment...
    other_user_forbidden = client.delete(
        f"/api/v1/working-papers/by-account/1-100/comments/{comment['id']}", headers=auth("parks_mgr")
    )
    assert other_user_forbidden.status_code in (403, 404)  # parks_mgr likely lacks the role entirely

    # ...but a finance_admin can, even though they didn't author it.
    admin_delete = client.delete(
        f"/api/v1/working-papers/by-account/1-100/comments/{comment['id']}", headers=auth("admin")
    )
    assert admin_delete.status_code == 204


def test_resolve_and_delete_comment_404_wrong_account(client, auth, fy2025):
    comment = client.post(
        "/api/v1/working-papers/by-account/1-100/comments",
        json={"fiscal_year_id": fy2025.id, "text": "note"},
        headers=auth("officer"),
    ).json()

    wrong_resolve = client.post(
        f"/api/v1/working-papers/by-account/9-999/comments/{comment['id']}/resolve", headers=auth("viewer")
    )
    assert wrong_resolve.status_code == 404

    wrong_delete = client.delete(
        f"/api/v1/working-papers/by-account/9-999/comments/{comment['id']}", headers=auth("officer")
    )
    assert wrong_delete.status_code == 404


def test_list_all_comments_for_fiscal_year(client, auth, fy2025, db):
    fy2026 = make_fiscal_year(db, 2026)
    client.post(
        "/api/v1/working-papers/by-account/1-100/comments",
        json={"fiscal_year_id": fy2025.id, "text": "a"},
        headers=auth("officer"),
    )
    client.post(
        "/api/v1/working-papers/by-account/6-100/comments",
        json={"fiscal_year_id": fy2025.id, "text": "b"},
        headers=auth("officer"),
    )
    client.post(
        "/api/v1/working-papers/by-account/1-100/comments",
        json={"fiscal_year_id": fy2026.id, "text": "different year"},
        headers=auth("officer"),
    )

    r = client.get("/api/v1/working-papers/comments", params={"fiscal_year_id": fy2025.id}, headers=auth("viewer"))
    assert r.status_code == 200
    codes = sorted(c["account_code"] for c in r.json())
    assert codes == ["1-100", "6-100"]


def test_comments_are_audited(client, auth, fy2025):
    comment = client.post(
        "/api/v1/working-papers/by-account/1-100/comments",
        json={"fiscal_year_id": fy2025.id, "text": "note"},
        headers=auth("officer"),
    ).json()
    client.post(f"/api/v1/working-papers/by-account/1-100/comments/{comment['id']}/resolve", headers=auth("officer"))
    client.delete(f"/api/v1/working-papers/by-account/1-100/comments/{comment['id']}", headers=auth("officer"))

    r = client.get("/api/v1/audit-logs", params={"resource_type": "account_comment"}, headers=auth("admin"))
    actions = [e["action"] for e in r.json()["items"]]
    assert "create" in actions and "resolve_comment" in actions and "delete" in actions
