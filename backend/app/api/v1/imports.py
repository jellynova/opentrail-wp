"""
Import preview (Caseware-style mapping dialog, PLAN phase 7/8).

The mapping dialog needs to see the raw upload before committing to an import:
which sheets exist, what the first rows actually contain, where the header row
landed and which canonical fields the auto-detector would guess. Nothing here
touches the database — preview only.

The column_map form-parsing helpers here are shared with the four import
endpoints so a bad mapping is rejected with the same 422 shape everywhere:
``{"detail": {"message": ..., "missing_fields": [...]}}``.
"""
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from app.core.security import get_current_active_user, require_role
from app.models.user import User
from app.services import import_parsers

router = APIRouter()

PREVIEW_ROWS = 25


def column_map_or_422(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    """Parse the column_map multipart field (a JSON object) or raise a 422."""
    if raw is None or raw.strip() == "":
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": f"column_map must be a JSON object mapping canonical fields to columns: {exc}",
                    "missing_fields": []},
        )
    if not isinstance(parsed, dict) or not all(isinstance(k, str) for k in parsed):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "column_map must be a JSON object mapping canonical field names to column indexes or letters",
                    "missing_fields": []},
        )
    return parsed


def mapping_error_422(exc: import_parsers.ImportMappingError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"message": str(exc), "missing_fields": list(getattr(exc, "missing", []))},
    )


def _grid_rows(grid: List[List[str]], limit: int) -> List[List[str]]:
    width = max((len(row) for row in grid), default=0)
    padded = [[(row[i] if i < len(row) else "") for i in range(width)] for row in grid]
    return padded[:limit]


@router.post("/imports/preview")
async def preview_import(
    file: UploadFile = File(...),
    sheet: Optional[str] = Query(None, description="Excel sheet name (default: first non-empty sheet)"),
    rows: int = Query(PREVIEW_ROWS, ge=1, le=100, description="How many raw rows to return"),
    current_user: User = Depends(require_role("finance_admin", "finance_officer", "viewer")),
):
    """
    Inspect an upload for the column-mapping dialog: file type, sheet names, the
    first rows of raw values, the auto-detected header row and column guesses.

    No data is written — preview only.
    """
    content = await file.read()
    try:
        file_type, grid = import_parsers.load_grid(content, file.filename or "", sheet)
    except import_parsers.ImportParseError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    header_index = import_parsers.find_header_row(grid)
    header_cells = [str(c) for c in grid[header_index]] if grid else []
    guesses: Dict[str, Dict[str, Any]] = import_parsers.guess_columns(header_cells)

    return {
        "file_type": file_type,
        "file_name": file.filename or "",
        "sheet_names": import_parsers.list_sheets(content, file.filename or ""),
        "selected_sheet": sheet,
        "total_rows": len(grid),
        "rows": _grid_rows(grid, rows),
        "header_row": header_index,
        "column_guesses": guesses,
    }
