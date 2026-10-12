"""
Shared drive storage for working papers (CaseWare-style single filing system).

When SHARED_DRIVE_PATH is configured, new uploads land on the mounted drive instead of
OpenTrail's own volume; existing files on that drive can be linked without copying bytes;
edits made directly on the drive (outside the app) are detected and void sign-off; new
versions overwrite the canonical file in place with a dated backup kept on the same drive.
"""
from __future__ import annotations

import io

from app.services import document_manager as doc_mgr
from tests.conftest import add_tb, make_account, make_scheme, period_of


def _upload(client, auth, fy, content=b"%PDF-1.4 x", display="report.pdf", folder="/current/2025", username="officer"):
    return client.post(
        "/api/v1/documents/upload",
        data={"fiscal_year_id": str(fy.id), "folder_path": folder, "display_name": display},
        files={"file": ("report.pdf", io.BytesIO(content), "application/pdf")},
        headers=auth(username),
    )


# ── App-wide switch ──────────────────────────────────────────────────────────


def test_shared_drive_disabled_by_default(client, auth, fy2025, documents_dir):
    status = client.get("/api/v1/documents/shared-drive/status", headers=auth("viewer")).json()
    assert status["enabled"] is False

    doc = _upload(client, auth, fy2025).json()
    assert doc["storage_backend"] == "managed"


def test_shared_drive_enabled_routes_new_uploads_there(client, auth, fy2025, shared_drive_dir):
    status = client.get("/api/v1/documents/shared-drive/status", headers=auth("viewer")).json()
    assert status["enabled"] is True

    doc = _upload(client, auth, fy2025, content=b"hello world").json()
    assert doc["storage_backend"] == "shared_drive"

    # The bytes are really on the shared drive, under the binder folder, not OpenTrail's
    # own managed volume.
    on_disk = list((shared_drive_dir / "current" / "2025").glob("*.pdf"))
    assert len(on_disk) == 1
    assert on_disk[0].read_bytes() == b"hello world"


def test_view_and_download_work_for_shared_drive_documents(client, auth, fy2025, shared_drive_dir):
    doc = _upload(client, auth, fy2025, content=b"the content").json()
    dl = client.get(f"/api/v1/documents/{doc['id']}/download", headers=auth("viewer"))
    assert dl.status_code == 200
    assert dl.content == b"the content"
    view = client.get(f"/api/v1/documents/{doc['id']}/view", headers=auth("viewer"))
    assert view.status_code == 200
    assert "inline" in view.headers["content-disposition"]


# ── Linking an existing file (no byte copy) ──────────────────────────────────


def test_browse_and_link_existing_shared_drive_file(client, auth, fy2025, shared_drive_dir):
    sub = shared_drive_dir / "Council Minutes"
    sub.mkdir()
    (sub / "2025-03 minutes.pdf").write_bytes(b"minutes content")

    browse_root = client.get("/api/v1/documents/shared-drive/browse", headers=auth("officer")).json()
    assert {"name": "Council Minutes", "is_dir": True}.items() <= browse_root[0].items()

    browse_sub = client.get(
        "/api/v1/documents/shared-drive/browse", params={"path": "Council Minutes"}, headers=auth("officer")
    ).json()
    assert browse_sub[0]["name"] == "2025-03 minutes.pdf"
    assert browse_sub[0]["is_dir"] is False
    assert browse_sub[0]["size"] == len(b"minutes content")

    link = client.post(
        "/api/v1/documents/link",
        json={
            "fiscal_year_id": fy2025.id,
            "folder_path": "/permanent",
            "shared_drive_path": "Council Minutes/2025-03 minutes.pdf",
            "display_name": "March council minutes",
        },
        headers=auth("officer"),
    )
    assert link.status_code == 201, link.text
    doc = link.json()
    assert doc["storage_backend"] == "shared_drive"
    assert doc["display_name"] == "March council minutes"

    # No copy was made -- download still reads directly from the original path.
    dl = client.get(f"/api/v1/documents/{doc['id']}/download", headers=auth("viewer"))
    assert dl.content == b"minutes content"


def test_link_requires_shared_drive_enabled(client, auth, fy2025, documents_dir):
    r = client.post(
        "/api/v1/documents/link",
        json={"fiscal_year_id": fy2025.id, "shared_drive_path": "x.pdf"},
        headers=auth("officer"),
    )
    assert r.status_code == 400


def test_link_rejects_path_traversal(client, auth, fy2025, shared_drive_dir):
    r = client.post(
        "/api/v1/documents/link",
        json={"fiscal_year_id": fy2025.id, "shared_drive_path": "../../etc/passwd"},
        headers=auth("officer"),
    )
    assert r.status_code == 400


def test_link_requires_editor_role(client, auth, fy2025, shared_drive_dir):
    (shared_drive_dir / "x.pdf").write_bytes(b"x")
    r = client.post(
        "/api/v1/documents/link",
        json={"fiscal_year_id": fy2025.id, "shared_drive_path": "x.pdf"},
        headers=auth("viewer"),
    )
    assert r.status_code == 403


# ── Delete never touches the organization's real file ────────────────────────


def test_delete_shared_drive_document_leaves_the_real_file_alone(client, auth, fy2025, shared_drive_dir):
    live = shared_drive_dir / "important.pdf"
    live.write_bytes(b"do not delete me")
    link = client.post(
        "/api/v1/documents/link",
        json={"fiscal_year_id": fy2025.id, "shared_drive_path": "important.pdf"},
        headers=auth("officer"),
    ).json()

    r = client.delete(f"/api/v1/documents/{link['id']}", headers=auth("officer"))
    assert r.status_code == 204
    assert live.exists()
    assert live.read_bytes() == b"do not delete me"


def test_delete_managed_document_does_remove_the_file(client, auth, fy2025, documents_dir):
    doc = _upload(client, auth, fy2025).json()
    on_disk = list(documents_dir.rglob("*.pdf"))
    assert len(on_disk) == 1

    client.delete(f"/api/v1/documents/{doc['id']}", headers=auth("officer"))
    assert not on_disk[0].exists()


# ── New version: overwrite in place + dated backup on the same drive ────────


def test_new_version_overwrites_in_place_with_backup(client, auth, fy2025, shared_drive_dir):
    doc = _upload(client, auth, fy2025, content=b"version one").json()
    original_path = shared_drive_dir / "current" / "2025" / doc["filename"]
    assert original_path.read_bytes() == b"version one"

    v2 = client.post(
        f"/api/v1/documents/{doc['id']}/versions",
        data={},
        files={"file": ("report.pdf", io.BytesIO(b"version two"), "application/pdf")},
        headers=auth("officer"),
    )
    assert v2.status_code == 201, v2.text
    v2_body = v2.json()

    # Same canonical path, new content -- not a second file.
    assert original_path.read_bytes() == b"version two"
    assert v2_body["filename"] == doc["filename"]

    # The old content was backed up on the SAME shared drive, not inside OpenTrail.
    assert v2_body["backup_path"] is not None
    backup_full_path = shared_drive_dir / v2_body["backup_path"]
    assert backup_full_path.exists()
    assert backup_full_path.read_bytes() == b"version one"
    assert ".opentrail-versions" in v2_body["backup_path"]


def test_new_version_requires_reapproval_same_as_managed(client, auth, fy2025, shared_drive_dir):
    """A new version of a previously-approved document needs re-review, same rule as managed storage."""
    doc = _upload(client, auth, fy2025).json()
    client.post(f"/api/v1/documents/{doc['id']}/sign-off/preparer", headers=auth("officer"))
    client.post(f"/api/v1/documents/{doc['id']}/sign-off/reviewer", headers=auth("admin"))

    v2 = client.post(
        f"/api/v1/documents/{doc['id']}/versions",
        data={},
        files={"file": ("report.pdf", io.BytesIO(b"new content"), "application/pdf")},
        headers=auth("officer"),
    ).json()
    assert v2["sign_off_state"] == "reapproval_required"
    assert v2["requires_reapproval"] is True


def test_new_version_rejects_folder_change_for_shared_drive(client, auth, fy2025, shared_drive_dir):
    doc = _upload(client, auth, fy2025).json()
    r = client.post(
        f"/api/v1/documents/{doc['id']}/versions",
        data={"folder_path": "/permanent"},
        files={"file": ("report.pdf", io.BytesIO(b"x"), "application/pdf")},
        headers=auth("officer"),
    )
    assert r.status_code == 400


# ── Drift detection: someone edits/removes the file outside the app ─────────


def test_external_edit_is_detected_and_voids_sign_off(client, auth, fy2025, shared_drive_dir):
    doc = _upload(client, auth, fy2025, content=b"original").json()
    client.post(f"/api/v1/documents/{doc['id']}/sign-off/preparer", headers=auth("officer"))
    client.post(f"/api/v1/documents/{doc['id']}/sign-off/reviewer", headers=auth("admin"))

    # Someone edits the file directly on the shared drive, bypassing OpenTrail entirely.
    live_path = shared_drive_dir / "current" / "2025" / doc["filename"]
    live_path.write_bytes(b"edited outside the app")

    refreshed = client.get(f"/api/v1/documents/{doc['id']}", headers=auth("viewer")).json()
    assert refreshed["sign_off_state"] == "reapproval_required"
    assert refreshed["requires_reapproval"] is True
    assert refreshed["is_missing"] is False


def test_external_deletion_is_flagged_without_touching_sign_off(client, auth, fy2025, shared_drive_dir):
    doc = _upload(client, auth, fy2025).json()
    client.post(f"/api/v1/documents/{doc['id']}/sign-off/preparer", headers=auth("officer"))
    client.post(f"/api/v1/documents/{doc['id']}/sign-off/reviewer", headers=auth("admin"))

    live_path = shared_drive_dir / "current" / "2025" / doc["filename"]
    live_path.unlink()

    refreshed = client.get(f"/api/v1/documents/{doc['id']}", headers=auth("viewer")).json()
    assert refreshed["is_missing"] is True
    # Being merely missing (e.g. VPN down) must not itself void a prior review.
    assert refreshed["sign_off_state"] == "approved"

    download = client.get(f"/api/v1/documents/{doc['id']}/download", headers=auth("viewer"))
    assert download.status_code == 404


def test_untouched_file_reports_ok_on_every_check(client, auth, fy2025, shared_drive_dir):
    doc = _upload(client, auth, fy2025).json()
    for _ in range(3):
        refreshed = client.get(f"/api/v1/documents/{doc['id']}", headers=auth("viewer")).json()
        assert refreshed["is_missing"] is False
        assert refreshed["sign_off_state"] == "draft"


def test_drift_shows_up_in_list_documents(client, auth, fy2025, shared_drive_dir):
    doc = _upload(client, auth, fy2025, content=b"original").json()
    live_path = shared_drive_dir / "current" / "2025" / doc["filename"]
    live_path.write_bytes(b"changed")

    listed = client.get(
        "/api/v1/documents", params={"fiscal_year_id": fy2025.id}, headers=auth("viewer")
    ).json()
    assert len(listed) == 1
    assert listed[0]["file_size"] == len(b"changed")


# ── materiality integration still works with shared-drive documents ─────────


def test_shared_drive_document_counts_as_materiality_support(client, auth, fy2025, shared_drive_dir, db):
    make_scheme(db)
    account = make_account(db, fy2025, "1-100", "Cash")
    p1 = period_of(fy2025, 1)
    add_tb(db, p1, account, ytd=100000)
    client.put(f"/api/v1/materiality/{fy2025.id}", json={"overall_materiality": "50000"}, headers=auth("officer"))

    doc = _upload(client, auth, fy2025, folder="/current/2025").json()
    client.post(
        f"/api/v1/working-papers/{doc['id']}/account-links",
        json={"account_code": "1-100", "fiscal_year_id": fy2025.id},
        headers=auth("officer"),
    )

    r = client.get(
        f"/api/v1/materiality/{fy2025.id}/unsupported-accounts", params={"period_id": p1.id}, headers=auth("viewer")
    )
    assert r.json()["accounts"] == []
