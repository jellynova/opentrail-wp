"""Shared helpers for endpoints that return a tabular report as JSON, Excel or PDF."""
from decimal import Decimal
from typing import Any, Dict, Literal

from fastapi import HTTPException, Response, status
from fastapi.encoders import jsonable_encoder

from app.services.report_generator import export_to_excel, export_to_pdf, safe_filename

ExportFormat = Literal["json", "xlsx", "pdf"]
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def money_json(obj: Any) -> Any:
    """JSON-encode with Decimals as exact strings (as Pydantic responses do), not floats."""
    return jsonable_encoder(obj, custom_encoder={Decimal: str})


def tabular_response(report: Dict[str, Any], fmt: str, filename: str) -> Any:
    if fmt == "json":
        return money_json(report)
    try:
        if fmt == "xlsx":
            content, media, ext = export_to_excel(report), XLSX_MEDIA_TYPE, "xlsx"
        else:
            content, media, ext = export_to_pdf(report), "application/pdf", "pdf"
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{safe_filename(filename)}.{ext}"'},
    )
