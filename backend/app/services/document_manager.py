"""
Document manager: file system operations for working papers.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.models.document import WorkingPaper


def _base_path() -> Path:
    return Path(settings.DOCUMENTS_PATH)


def save_file(file_content: bytes, folder_path: str, filename: str) -> str:
    """
    Save file bytes to DOCUMENTS_PATH/folder_path/filename.

    Creates intermediate directories as needed.
    Returns the relative path (folder_path/filename) for storage in the DB.
    """
    # Strip leading slash to make it relative
    folder_clean = folder_path.lstrip("/").rstrip("/")
    dest_dir = _base_path() / folder_clean
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_file = dest_dir / filename
    dest_file.write_bytes(file_content)

    return str(Path(folder_clean) / filename)


def delete_file(file_path: str) -> None:
    """
    Delete a file at DOCUMENTS_PATH/file_path.
    Silently ignores missing files.
    """
    full_path = _base_path() / file_path.lstrip("/")
    try:
        full_path.unlink(missing_ok=True)
    except Exception:
        pass


def get_file_path(document: WorkingPaper) -> str:
    """
    Return the absolute filesystem path for a WorkingPaper document.
    """
    folder_clean = document.folder_path.lstrip("/").rstrip("/")
    return str(_base_path() / folder_clean / document.filename)


def get_file_bytes(document: WorkingPaper) -> bytes:
    """
    Read and return the file content for a WorkingPaper.
    Raises FileNotFoundError if the file does not exist on disk.
    """
    path = Path(get_file_path(document))
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_bytes()


def file_exists(document: WorkingPaper) -> bool:
    """Check whether the underlying file exists on disk."""
    return Path(get_file_path(document)).exists()
