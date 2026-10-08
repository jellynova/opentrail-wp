"""
Server-Sent Events endpoint for live activity notifications (PLAN §8.2).

``EventSource`` cannot set an Authorization header, so the stream accepts the access
token as a ``token`` query parameter. That is acceptable for this deployment (locally
hosted, single municipality, TLS optional) and is documented in the deployment guide;
everything else in the app still authenticates with the Bearer header.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token, get_current_active_user, require_role
from app.models.user import User
from app.services import events as events_svc

logger = logging.getLogger(__name__)

router = APIRouter()

HEARTBEAT_SECONDS = 15


def _user_from_token(token: str, db: Session) -> User:
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    subject = payload.get("sub")
    if subject is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    user = db.get(User, int(subject))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


@router.get("/events/recent")
def recent_events(
    limit: int = Query(20, ge=1, le=events_svc.HISTORY_SIZE),
    current_user: User = Depends(get_current_active_user),
) -> List[Dict[str, Any]]:
    """The most recent notifications (newest first), used to populate the bell on load."""
    return list(reversed(events_svc.history(current_user.role)))[:limit]


@router.get("/events/stream")
async def stream_events(
    request: Request,
    token: Optional[str] = Query(None, description="Access token (EventSource cannot send headers)"),
    db: Session = Depends(get_db),
):
    """Live notification stream. One SSE frame per notification, heartbeat every 15s."""
    header_token = None
    authorization = request.headers.get("authorization") or ""
    if authorization.lower().startswith("bearer "):
        header_token = authorization[7:].strip()
    raw_token = token or header_token
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token required")
    user = _user_from_token(raw_token, db)
    username, role = user.username, user.role
    # Release the pooled connection now: the stream can stay open for hours, and an
    # un-closed session would sit "idle in transaction" holding it the whole time.
    db.close()

    queue = events_svc.subscribe()

    async def event_stream():
        try:
            # Replay recent activity so a fresh page shows context immediately.
            recent = events_svc.history(role)
            yield f"event: ready\ndata: {json.dumps({'user': username, 'recent': recent}, default=str)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    notification = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if events_svc.visible_to(notification, role):
                    yield events_svc.format_sse(notification)
        except asyncio.CancelledError:  # client went away mid-write
            raise
        finally:
            events_svc.unsubscribe(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # tells nginx not to buffer the stream
        },
    )
