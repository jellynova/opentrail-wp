"""Phase 7: working paper files, versioning, annotations and the two-level sign-off."""
from __future__ import annotations

import io

import pytest

from app.services import document_manager as doc_mgr


def _upload(client, auth, fy, folder="/current/2025", filename="lead.pdf", username="officer", content=b"%PDF-1.4 test"):
    return client.post(
        "/api/v1/documents/upload",
        data={"fiscal_year_id": str(fy.id), "folder_path": folder, "display_name": filename},
        files={"file": (filename, io.BytesIO(content), "application/pdf")},
        headers=auth(username),
    )


def test_upload_and_list(client, auth, fy2025, documents_dir):
    r = _upload(client, auth, fy2025)
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["version_number"] == 1
    assert doc["folder_path"] == "/current/2025"
    assert doc["sign_off_state"] == "draft"
    assert doc["version_count"] == 1

    listed = client.get("/api/v1/documents", params={"fiscal_year_id": fy2025.id}, headers=auth("viewer"))
    assert listed.status_code == 200
    assert [d["id"] for d in listed.json()] == [doc["id"]]
    assert listed.json()[0]["uploaded_by_username"] == "officer"


def test_upload_rejects_folder_traversal(client, auth, fy2025, documents_dir):
    for folder in ("/../../etc", "/etc", "/current/../../../etc", "/current/2025/../../.."):
        r = _upload(client, auth, fy2025, folder=folder)
        assert r.status_code == 400, folder
        assert "Folder" in r.json()["detail"]


def test_clean_folder_path_allows_binder_folders():
    assert doc_mgr.clean_folder_path("/current/2025") == "/current/2025"
    assert doc_mgr.clean_folder_path("statements") == "/statements"
    assert doc_mgr.clean_folder_path("/") == "/permanent"
    for bad in ("/tmp", "/../secrets", "/permanent/../../../x", "/a/b/c/d/e"):
        try:
            doc_mgr.clean_folder_path(bad)
        except doc_mgr.InvalidFolderPath:
            continue
        raise AssertionError(f"{bad} should have been rejected")


def test_upload_requires_known_fiscal_year(client, auth, fy2025, documents_dir):
    r = _upload(client, auth, fy2025)
    assert r.status_code == 201
    r = client.post(
        "/api/v1/documents/upload",
        data={"fiscal_year_id": "999", "folder_path": "/permanent"},
        files={"file": ("a.pdf", io.BytesIO(b"x"), "application/pdf")},
        headers=auth("officer"),
    )
    assert r.status_code == 404


def test_upload_rejects_disallowed_extension(client, auth, fy2025, documents_dir):
    r = client.post(
        "/api/v1/documents/upload",
        data={"fiscal_year_id": str(fy2025.id), "folder_path": "/permanent"},
        files={"file": ("evil.sh", io.BytesIO(b"rm -rf /"), "text/x-shellscript")},
        headers=auth("officer"),
    )
    assert r.status_code == 400


def test_folder_tree_lists_fiscal_years(client, auth, fy2025, documents_dir):
    _upload(client, auth, fy2025, folder="/current/2025")
    r = client.get("/api/v1/documents/folders", headers=auth("viewer"))
    assert r.status_code == 200
    tree = {node["path"]: node for node in r.json()}
    assert set(tree) == {"/permanent", "/current", "/statements", "/budget"}
    current_children = {c["path"]: c for c in tree["/current"]["children"]}
    assert "/current/2025" in current_children
    assert current_children["/current/2025"]["fiscal_year_id"] == fy2025.id
    assert current_children["/current/2025"]["document_count"] == 1
    assert current_children["/current/2025"]["unsigned_count"] == 1


def test_new_version_supersedes_and_needs_reapproval(client, auth, fy2025, documents_dir):
    doc = _upload(client, auth, fy2025).json()

    # Prepare and review version 1.
    assert client.post(f"/api/v1/documents/{doc['id']}/sign-off/preparer", headers=auth("officer")).status_code == 200
    r = client.post(f"/api/v1/documents/{doc['id']}/sign-off/reviewer", headers=auth("admin"))
    assert r.status_code == 200
    assert r.json()["sign_off_state"] == "approved"

    # A replacement version must be reviewed again.
    r = client.post(
        f"/api/v1/documents/{doc['id']}/versions",
        files={"file": ("lead_v2.pdf", io.BytesIO(b"%PDF-1.4 v2"), "application/pdf")},
        headers=auth("officer"),
    )
    assert r.status_code == 201, r.text
    v2 = r.json()
    assert v2["version_number"] == 2
    assert v2["sign_off_state"] == "reapproval_required"
    assert v2["requires_reapproval"] is True
    assert v2["version_count"] == 2

    versions = client.get(f"/api/v1/documents/{doc['id']}/versions", headers=auth("viewer")).json()
    assert [v["version_number"] for v in versions] == [1, 2]
    assert versions[0]["superseded_at"] is not None
    assert versions[0]["sign_off_state"] == "approved"  # history keeps its own sign-off

    # The listing shows only the latest version.
    listed = client.get("/api/v1/documents", headers=auth("viewer")).json()
    assert [d["version_number"] for d in listed] == [2]


def test_sign_off_workflow_rules(client, auth, fy2025, documents_dir):
    doc = _upload(client, auth, fy2025).json()

    # Reviewer sign-off requires the preparer's first.
    r = client.post(f"/api/v1/documents/{doc['id']}/sign-off/reviewer", headers=auth("admin"))
    assert r.status_code == 400

    # A budget_manager cannot sign off at all.
    assert client.post(f"/api/v1/documents/{doc['id']}/sign-off/preparer", headers=auth("parks_mgr")).status_code == 403

    assert client.post(f"/api/v1/documents/{doc['id']}/sign-off/preparer", headers=auth("officer")).status_code == 200
    state = client.get(f"/api/v1/documents/{doc['id']}", headers=auth("viewer")).json()
    assert state["sign_off_state"] == "prepared"
    assert state["preparer_signed_off_by_username"] == "officer"

    # Reviewer sign-off is a finance_admin action.
    r = client.post(f"/api/v1/documents/{doc['id']}/sign-off/reviewer", headers=auth("officer"))
    assert r.status_code == 403
    assert "finance_admin" in r.json()["detail"]

    # A finance_admin who did not prepare it can.
    r = client.post(
        f"/api/v1/documents/{doc['id']}/sign-off/reviewer",
        json={"note": "agrees to GL"},
        headers=auth("admin"),
    )
    assert r.status_code == 200
    assert r.json()["sign_off_state"] == "approved"

    notes = client.get(f"/api/v1/documents/{doc['id']}/annotations", headers=auth("viewer")).json()
    assert any("Reviewer note: agrees to GL" in n["text"] for n in notes)


def test_admin_cannot_review_their_own_working_paper(client, auth, fy2025, documents_dir):
    doc = _upload(client, auth, fy2025, username="admin").json()
    assert client.post(f"/api/v1/documents/{doc['id']}/sign-off/preparer", headers=auth("admin")).status_code == 200

    r = client.post(f"/api/v1/documents/{doc['id']}/sign-off/reviewer", headers=auth("admin"))
    assert r.status_code == 403
    assert "cannot be reviewed by the person who prepared" in r.json()["detail"]

    # An officer can prepare it, then the admin reviews.
    client.post(f"/api/v1/documents/{doc['id']}/sign-off/preparer", headers=auth("officer"))
    assert client.post(f"/api/v1/documents/{doc['id']}/sign-off/reviewer", headers=auth("admin")).status_code == 200


def test_metadata_edit_voids_sign_off(client, auth, fy2025, documents_dir):
    doc = _upload(client, auth, fy2025).json()
    client.post(f"/api/v1/documents/{doc['id']}/sign-off/preparer", headers=auth("officer"))
    client.post(f"/api/v1/documents/{doc['id']}/sign-off/reviewer", headers=auth("admin"))

    r = client.put(
        f"/api/v1/documents/{doc['id']}",
        json={"display_name": "Lead sheet (revised)"},
        headers=auth("officer"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["display_name"] == "Lead sheet (revised)"
    assert body["sign_off_state"] == "reapproval_required"
    assert body["reviewer_signed_off_at"] is None


def test_sign_off_reset(client, auth, fy2025, documents_dir):
    doc = _upload(client, auth, fy2025).json()
    client.post(f"/api/v1/documents/{doc['id']}/sign-off/preparer", headers=auth("officer"))
    client.post(f"/api/v1/documents/{doc['id']}/sign-off/reviewer", headers=auth("admin"))

    r = client.post(f"/api/v1/documents/{doc['id']}/sign-off/reset", headers=auth("admin"))
    assert r.status_code == 200
    assert r.json()["sign_off_state"] == "reapproval_required"
    # Only a finance_admin can withdraw sign-off.
    assert client.post(f"/api/v1/documents/{doc['id']}/sign-off/reset", headers=auth("officer")).status_code == 403


def test_cannot_sign_off_superseded_version(client, auth, fy2025, documents_dir):
    doc = _upload(client, auth, fy2025).json()
    v2 = client.post(
        f"/api/v1/documents/{doc['id']}/versions",
        files={"file": ("v2.pdf", io.BytesIO(b"%PDF-1.4 v2"), "application/pdf")},
        headers=auth("officer"),
    ).json()

    r = client.post(f"/api/v1/documents/{doc['id']}/sign-off/preparer", headers=auth("officer"))
    assert r.status_code == 400
    assert client.post(f"/api/v1/documents/{v2['id']}/sign-off/preparer", headers=auth("officer")).status_code == 200


def test_annotations_lifecycle(client, auth, fy2025, documents_dir):
    doc = _upload(client, auth, fy2025).json()

    created = client.post(
        f"/api/v1/documents/{doc['id']}/annotations", json={"text": "tie to GL"}, headers=auth("admin")
    )
    assert created.status_code == 201
    annotation = created.json()
    assert annotation["username"] == "admin"
    assert annotation["is_resolved"] is False

    assert client.post(f"/api/v1/documents/{doc['id']}/annotations", json={"text": "  "}, headers=auth("admin")).status_code == 400

    resolved = client.post(
        f"/api/v1/documents/{doc['id']}/annotations/{annotation['id']}/resolve", headers=auth("officer")
    )
    assert resolved.status_code == 200
    assert resolved.json()["is_resolved"] is True
    assert resolved.json()["resolved_by_username"] == "officer"
    assert resolved.json()["resolved_at"] is not None

    reopened = client.post(
        f"/api/v1/documents/{doc['id']}/annotations/{annotation['id']}/resolve",
        params={"resolved": "false"},
        headers=auth("officer"),
    )
    assert reopened.json()["is_resolved"] is False
    assert reopened.json()["resolved_by_user_id"] is None

    unresolved_only = client.get(
        f"/api/v1/documents/{doc['id']}/annotations",
        params={"include_resolved": "false"},
        headers=auth("viewer"),
    ).json()
    assert len(unresolved_only) == 1

    assert client.delete(
        f"/api/v1/documents/{doc['id']}/annotations/{annotation['id']}", headers=auth("admin")
    ).status_code == 204
    assert client.get(f"/api/v1/documents/{doc['id']}/annotations", headers=auth("viewer")).json() == []


def test_download_and_delete_removes_all_versions(client, auth, fy2025, documents_dir):
    doc = _upload(client, auth, fy2025, content=b"%PDF-1.4 v1").json()
    v2 = client.post(
        f"/api/v1/documents/{doc['id']}/versions",
        files={"file": ("v2.pdf", io.BytesIO(b"%PDF-1.4 v2"), "application/pdf")},
        headers=auth("officer"),
    ).json()

    got = client.get(f"/api/v1/documents/{v2['id']}/download", headers=auth("viewer"))
    assert got.status_code == 200
    assert got.content == b"%PDF-1.4 v2"

    # An approved paper is protected from deletion by non-admins.
    client.post(f"/api/v1/documents/{v2['id']}/sign-off/preparer", headers=auth("officer"))
    client.post(f"/api/v1/documents/{v2['id']}/sign-off/reviewer", headers=auth("admin"))
    assert client.delete(f"/api/v1/documents/{v2['id']}", headers=auth("officer")).status_code == 403
    assert client.delete(f"/api/v1/documents/{v2['id']}", headers=auth("admin")).status_code == 204

    assert client.get("/api/v1/documents", headers=auth("viewer")).json() == []
    assert not list(documents_dir.rglob("*.pdf")), "files should be removed from disk"


@pytest.mark.parametrize("name", ["Rapport “final” — 2025.pdf", 'quote"d.pdf', "Bank rec\r\nX-Injected: 1.pdf"])
def test_download_header_safe_for_any_display_name(client, auth, fy2025, documents_dir, name):
    r = client.post(
        "/api/v1/documents/upload", headers=auth("officer"),
        data={"fiscal_year_id": str(fy2025.id), "folder_path": "/current/2025", "display_name": name},
        files={"file": ("x.pdf", b"%PDF", "application/pdf")},
    )
    assert r.status_code == 201, r.text
    dl = client.get(f"/api/v1/documents/{r.json()['id']}/download", headers=auth("viewer"))
    assert dl.status_code == 200 and dl.content == b"%PDF"
    assert "x-injected" not in dl.headers
    assert dl.headers["content-disposition"].startswith('attachment; filename="')
