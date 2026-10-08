"""
Document manager: file system operations and folder/version helpers for working papers.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import WorkingPaper
from app.models.period import FiscalYear

# Folder roots that mirror a municipal audit binder (PLAN §7.1).
FOLDER_ROOTS = [
    ("/permanent", "Permanent File"),
    ("/current", "Current Period"),
    ("/statements", "Financial Statements"),
    ("/budget", "Budget Working Papers"),
]

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._&()-]{0,99}$")
MAX_DEPTH = 4


class InvalidFolderPath(ValueError):
    """Raised when a folder path is outside the allowed binder structure."""


def _base_path() -> Path:
    return Path(settings.DOCUMENTS_PATH)


def clean_folder_path(folder_path: Optional[str]) -> str:
    """
    Normalise and validate a folder path such as ``/current/2025``.

    Only paths inside the binder roots (permanent / current / statements / budget) are
    accepted, at most ``MAX_DEPTH`` levels deep. Segments may not be ``.``/``..`` and are
    limited to a conservative character set, which is what keeps a crafted
    ``folder_path`` from writing outside ``DOCUMENTS_PATH``.
    """
    raw = (folder_path or "/").strip().replace("\\", "/")
    if not raw.startswith("/"):
        raw = "/" + raw
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise InvalidFolderPath("Folder paths may not contain '..'")
    if not parts:
        # "/" itself is not a binder folder; default to the permanent file.
        return "/permanent"
    if len(parts) > MAX_DEPTH:
        raise InvalidFolderPath(f"Folder path may be at most {MAX_DEPTH} levels deep")
    for part in parts:
        if not _SAFE_SEGMENT.match(part):
            raise InvalidFolderPath(f"Invalid folder name: '{part}'")
    root = f"/{parts[0]}"
    if root not in {r for r, _ in FOLDER_ROOTS}:
        allowed = ", ".join(r for r, _ in FOLDER_ROOTS)
        raise InvalidFolderPath(f"Folder must be inside one of: {allowed}")
    return "/" + "/".join(parts)


def relative_folder(folder_path: str) -> str:
    """Path relative to DOCUMENTS_PATH ('' for a root folder)."""
    return clean_folder_path(folder_path).strip("/")


def folder_tree(db: Session, counts: Optional[Dict[str, Dict[str, int]]] = None) -> List[dict]:
    """
    The binder structure for the UI: the four roots, with a sub-folder per fiscal year
    under ``/current`` (created from the fiscal years on file rather than hard-coded).

    ``counts`` optionally maps folder path -> {"documents": n, "unsigned": n}.
    """
    counts = counts or {}
    years = db.scalars(select(FiscalYear).order_by(FiscalYear.start_date.desc())).all()

    tree: List[dict] = []
    for path, label in FOLDER_ROOTS:
        node = {
            "path": path,
            "label": label,
            "document_count": counts.get(path, {}).get("documents", 0),
            "unsigned_count": counts.get(path, {}).get("unsigned", 0),
            "children": [],
        }
        if path == "/current":
            for fy in years:
                child_path = f"/current/{fy.label}"
                node["children"].append(
                    {
                        "path": child_path,
                        "label": fy.label,
                        "fiscal_year_id": fy.id,
                        "fiscal_year_status": fy.status,
                        "document_count": counts.get(child_path, {}).get("documents", 0),
                        "unsigned_count": counts.get(child_path, {}).get("unsigned", 0),
                        "children": [],
                    }
                )
        tree.append(node)
    return tree


def latest_versions(
    db: Session,
    *,
    fiscal_year_id: Optional[int] = None,
    folder_path: Optional[str] = None,
    folder_prefix: Optional[str] = None,
    include_versions: bool = False,
) -> List[WorkingPaper]:
    """
    Working paper rows, newest upload first.

    By default only the latest version of each document is returned: versions of the same
    document are rows sharing a root (``parent_version_id`` or the row's own id). With
    ``include_versions=True`` every version is returned.
    """
    stmt = select(WorkingPaper)
    if fiscal_year_id is not None:
        stmt = stmt.where(WorkingPaper.fiscal_year_id == fiscal_year_id)
    if folder_path is not None:
        stmt = stmt.where(WorkingPaper.folder_path == clean_folder_path(folder_path))
    if folder_prefix is not None:
        prefix = clean_folder_path(folder_prefix).rstrip("/")
        stmt = stmt.where(WorkingPaper.folder_path.like(f"{prefix}%"))

    rows = list(db.scalars(stmt.order_by(WorkingPaper.uploaded_at.desc(), WorkingPaper.id.desc())).all())
    if include_versions:
        return rows

    latest: Dict[int, WorkingPaper] = {}
    for row in rows:
        root = row.root_id
        current = latest.get(root)
        if current is None or (row.version_number, row.id) > (current.version_number, current.id):
            latest[root] = row
    return sorted(latest.values(), key=lambda r: (r.uploaded_at, r.id), reverse=True)


def document_versions(db: Session, document_id: int) -> List[WorkingPaper]:
    """Every version of a document, oldest first. ``document_id`` may be any version id."""
    row = db.get(WorkingPaper, document_id)
    if row is None:
        return []
    root = row.root_id
    rows = db.scalars(
        select(WorkingPaper)
        .where((WorkingPaper.id == root) | (WorkingPaper.parent_version_id == root))
        .order_by(WorkingPaper.version_number, WorkingPaper.id)
    ).all()
    return list(rows)


def sign_off_status(versions: Iterable[WorkingPaper], latest: WorkingPaper) -> dict:
    """
    Sign-off state for a document given all of its versions (oldest first).

    A document whose latest version is not reviewer-signed-off but an earlier version was
    has been modified after sign-off and needs re-approval (PLAN §7.2).
    """
    versions = list(versions)
    earlier_signed = any(v.reviewer_signed_off_at is not None for v in versions if v.id != latest.id)
    needs_reapproval = latest.reviewer_signed_off_at is None and (
        bool(latest.requires_reapproval) or earlier_signed
    )
    if latest.reviewer_signed_off_at is not None:
        state = "approved"
    elif needs_reapproval:
        state = "reapproval_required"
    elif latest.preparer_signed_off_at is not None:
        state = "prepared"
    else:
        state = "draft"
    return {
        "sign_off_state": state,
        "requires_reapproval": needs_reapproval,
        "version_count": len(versions) or 1,
        "is_latest_version": True,
    }


def save_file(file_content: bytes, folder_path: str, filename: str) -> str:
    """
    Save file bytes to DOCUMENTS_PATH/<folder_path>/<filename>.

    Creates intermediate directories as needed. Returns the path relative to
    DOCUMENTS_PATH for storage in the DB. The folder path is validated (binder roots only,
    no traversal) and the file name is reduced to its base name, so a crafted upload
    cannot escape the documents volume.
    """
    folder_clean = relative_folder(folder_path)
    safe_name = os.path.basename(filename or "").strip() or "upload"
    dest_dir = _base_path() / folder_clean
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_file = dest_dir / safe_name
    # Never follow a symlink out of the documents volume.
    if dest_file.is_symlink():
        dest_file.unlink()
    dest_file.write_bytes(file_content)

    return str(Path(folder_clean) / safe_name)


def delete_file(file_path: str) -> None:
    """
    Delete a stored file. Accepts either an absolute path (as returned by
    ``get_file_path``) or one relative to DOCUMENTS_PATH. Missing files are ignored.
    """
    path = Path(file_path)
    if not path.is_absolute():
        path = _base_path() / file_path.lstrip("/")
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def get_file_path(document: WorkingPaper) -> str:
    """Absolute filesystem path for a WorkingPaper document."""
    folder_clean = relative_folder(document.folder_path)
    return str(_base_path() / folder_clean / os.path.basename(document.filename))


def get_file_bytes(document: WorkingPaper) -> bytes:
    """Read the file content for a WorkingPaper. Raises FileNotFoundError if missing."""
    path = Path(get_file_path(document))
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_bytes()


def file_exists(document: WorkingPaper) -> bool:
    """Check whether the underlying file exists on disk."""
    return Path(get_file_path(document)).exists()
