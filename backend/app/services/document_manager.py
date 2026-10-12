"""
Document manager: file system operations and folder/version helpers for working papers.
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
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


def shared_drive_enabled() -> bool:
    """True once an admin has configured SHARED_DRIVE_PATH; drives the app-wide switch."""
    return bool(settings.SHARED_DRIVE_PATH.strip())


def _shared_drive_root() -> Path:
    if not shared_drive_enabled():
        raise InvalidFolderPath("No shared drive is configured (SHARED_DRIVE_PATH is empty)")
    return Path(settings.SHARED_DRIVE_PATH)


def _root_for(storage_backend: str) -> Path:
    return _shared_drive_root() if storage_backend == "shared_drive" else _base_path()


_SAFE_RELATIVE_SEGMENT = re.compile(r"^[^/\\\0]+$")


def clean_relative_path(relative_path: str) -> str:
    """
    Normalise and validate a path relative to a storage root (shared drive or managed).

    Rejects '..' traversal and absolute paths; this is what keeps a crafted shared-drive
    path (typed by a user picking an "existing file") from escaping SHARED_DRIVE_PATH.
    """
    raw = (relative_path or "").strip().replace("\\", "/").strip("/")
    if not raw:
        raise InvalidFolderPath("A path is required")
    parts = [p for p in raw.split("/") if p != ""]
    if any(p in (".", "..") for p in parts):
        raise InvalidFolderPath("Paths may not contain '.' or '..'")
    for p in parts:
        if not _SAFE_RELATIVE_SEGMENT.match(p):
            raise InvalidFolderPath(f"Invalid path segment: '{p}'")
    return "/".join(parts)


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


def save_file(file_content: bytes, folder_path: str, filename: str, *, storage_backend: str = "managed") -> str:
    """
    Save file bytes to <root>/<folder_path>/<filename>, where <root> is the managed
    documents volume or the configured shared drive depending on ``storage_backend``.

    Creates intermediate directories as needed. Returns the path relative to the root for
    storage in the DB. The folder path is validated (binder roots only, no traversal) and
    the file name is reduced to its base name, so a crafted upload cannot escape the
    storage volume.
    """
    folder_clean = relative_folder(folder_path)
    safe_name = os.path.basename(filename or "").strip() or "upload"
    dest_dir = _root_for(storage_backend) / folder_clean
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_file = dest_dir / safe_name
    # Never follow a symlink out of the storage volume.
    if dest_file.is_symlink():
        dest_file.unlink()
    dest_file.write_bytes(file_content)

    return str(Path(folder_clean) / safe_name)


def default_storage_backend() -> str:
    """
    Which backend a brand-new upload should land on. Once a shared drive is configured
    it is used for everything new (PLAN: no more copies drifting from the org's existing
    filing system) -- "managed" survives only for documents uploaded before that happened.
    """
    return "shared_drive" if shared_drive_enabled() else "managed"


def delete_file(file_path: str, *, storage_backend: str = "managed") -> None:
    """
    Delete a stored file. Accepts either an absolute path (as returned by
    ``get_file_path``) or one relative to the storage root. Missing files are ignored.
    """
    path = Path(file_path)
    if not path.is_absolute():
        path = _root_for(storage_backend) / file_path.lstrip("/")
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def get_file_path(document: WorkingPaper) -> str:
    """Absolute filesystem path for a WorkingPaper document, on its own storage backend."""
    root = _root_for(document.storage_backend)
    if document.storage_backend == "shared_drive" and "/" in document.filename:
        # A linked document's `filename` is its full path relative to the shared drive
        # root (it may live anywhere in the org's existing structure); `folder_path` is
        # only where it's organized in OpenTrail's own binder tree, not its real location.
        return str(root / document.filename)
    folder_clean = relative_folder(document.folder_path)
    return str(root / folder_clean / os.path.basename(document.filename))


def get_file_bytes(document: WorkingPaper) -> bytes:
    """Read the file content for a WorkingPaper. Raises FileNotFoundError if missing."""
    path = Path(get_file_path(document))
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_bytes()


def overwrite_file(document: WorkingPaper, content: bytes) -> None:
    """
    Write ``content`` to exactly where ``get_file_path(document)`` says this document's
    bytes live -- the one path-resolution rule, used for both the regular binder layout
    and a linked document's (possibly deep, binder-independent) real shared-drive path.
    """
    path = Path(get_file_path(document))
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    path.write_bytes(content)


def file_exists(document: WorkingPaper) -> bool:
    """Check whether the underlying file exists on disk."""
    return Path(get_file_path(document)).exists()


# --------------------------------------------------------------------------------------
# Shared-drive specifics: hashing, drift detection, browsing, versioned backups
# --------------------------------------------------------------------------------------


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stamp_from_bytes(document: WorkingPaper, content: bytes) -> None:
    """Record content_hash/source_mtime for ``document`` after writing ``content``."""
    document.content_hash = sha256_of(content)
    path = Path(get_file_path(document))
    document.source_mtime = path.stat().st_mtime if path.exists() else None
    document.missing_since = None


def check_drift(document: WorkingPaper) -> dict:
    """
    Compare the live file on disk against what was last recorded for a shared-drive
    document. Cheap by default (just a stat): only re-hashes when the mtime or size has
    moved, since someone editing the file directly on the network drive is the whole
    point of this storage mode and OpenTrail has no other way to find out.

    Returns {"status": "ok" | "missing" | "modified", "checked_at": ...}. Mutates
    ``document``'s missing_since (caller is responsible for committing).
    """
    if document.storage_backend != "shared_drive":
        return {"status": "ok"}

    path = Path(get_file_path(document))
    if not path.exists():
        if document.missing_since is None:
            document.missing_since = datetime.now(timezone.utc)
        return {"status": "missing"}

    stat = path.stat()
    if document.missing_since is not None:
        document.missing_since = None  # it came back; a hash check below confirms content

    mtime_matches = document.source_mtime is not None and abs(stat.st_mtime - document.source_mtime) < 1.0
    size_matches = stat.st_size == document.file_size
    if mtime_matches and size_matches:
        return {"status": "ok"}

    # mtime or size moved -- confirm with an actual hash before flagging, since some
    # network filesystems round-trip mtimes imprecisely.
    actual_hash = sha256_of(path.read_bytes())
    if actual_hash == document.content_hash:
        document.source_mtime = stat.st_mtime
        document.file_size = stat.st_size
        return {"status": "ok"}
    return {"status": "modified"}


def backup_before_overwrite(document: WorkingPaper) -> Optional[str]:
    """
    Copy a shared-drive document's CURRENT live bytes into a dated backup file next to
    it, before a new version overwrites the canonical path in place. Returns the backup's
    path relative to SHARED_DRIVE_PATH, or None if there was nothing to back up (first
    version, or the live file is already missing).

    The backup lives in a ``.opentrail-versions`` sub-folder alongside the document on the
    SAME shared drive -- it is version history, not a second filing system.
    """
    if document.storage_backend != "shared_drive":
        return None
    live_path = Path(get_file_path(document))
    if not live_path.exists():
        return None

    folder_clean = relative_folder(document.folder_path)
    backup_dir = _shared_drive_root() / folder_clean / ".opentrail-versions"
    backup_dir.mkdir(parents=True, exist_ok=True)

    base = os.path.splitext(os.path.basename(document.filename))[0]
    ext = os.path.splitext(document.filename)[1]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_name = f"{base}__v{document.version_number}_{timestamp}{ext}"
    backup_path = backup_dir / backup_name
    backup_path.write_bytes(live_path.read_bytes())

    return str(Path(folder_clean) / ".opentrail-versions" / backup_name)


def browse_shared_drive(relative_path: str = "") -> List[dict]:
    """
    List immediate children (folders then files) of a path under the shared drive root,
    for the "link an existing file" picker -- so staff can point OpenTrail at a document
    already sitting in the organization's normal filing system without uploading a
    redundant copy through the browser.
    """
    root = _shared_drive_root()
    rel = clean_relative_path(relative_path) if relative_path.strip("/") else ""
    target = (root / rel) if rel else root
    if not target.exists() or not target.is_dir():
        raise InvalidFolderPath(f"'{relative_path or '/'}' is not a folder on the shared drive")

    entries = []
    try:
        children = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        raise InvalidFolderPath(f"Permission denied reading '{relative_path or '/'}' on the shared drive")

    for child in children:
        if child.name.startswith(".") or child.name == ".opentrail-versions":
            continue  # hide dotfiles and our own backup folders from the picker
        try:
            stat = child.stat()
        except OSError:
            continue
        entries.append(
            {
                "name": child.name,
                "path": str(Path(rel) / child.name) if rel else child.name,
                "is_dir": child.is_dir(),
                "size": stat.st_size if child.is_file() else None,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    return entries


def stat_shared_drive_file(relative_path: str) -> dict:
    """Metadata for a file on the shared drive, for linking it without copying bytes."""
    root = _shared_drive_root()
    rel = clean_relative_path(relative_path)
    target = root / rel
    if not target.exists() or not target.is_file():
        raise InvalidFolderPath(f"'{relative_path}' is not a file on the shared drive")
    stat = target.stat()
    return {
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "content_hash": sha256_of(target.read_bytes()),
    }
