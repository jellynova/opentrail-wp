"""
Real-time notifications over Server-Sent Events (PLAN §8.2).

A small in-process broker: subscribers get an ``asyncio.Queue``, publishers push
notification dicts onto every queue. SSE was chosen over WebSockets because the scale
(4–10 users on a LAN) does not justify connection-management complexity.

Sync request handlers run in a threadpool, so ``publish`` marshals onto the event loop
captured at application startup (``set_loop``) with ``call_soon_threadsafe``. The last
``HISTORY_SIZE`` notifications are kept in a ring buffer so a client that connects (or
reconnects) immediately sees recent activity without waiting for the next event.

Notifications raised inside a transaction are held on the SQLAlchemy session and
published only when it commits (``publish_on_commit``), so a request that fails after
recording its audit entry never announces a change that was rolled back. Budget managers
only receive budget workflow events (``visible_to``).
"""
from __future__ import annotations

import asyncio
import logging
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

from sqlalchemy import event
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

HISTORY_SIZE = 50
QUEUE_SIZE = 200

_loop: Optional[asyncio.AbstractEventLoop] = None
_subscribers: "set[asyncio.Queue]" = set()
_history: Deque[Dict[str, Any]] = deque(maxlen=HISTORY_SIZE)
_next_id = 1
_id_lock = threading.Lock()  # publishers run on threadpool threads
_PENDING_KEY = "pending_notifications"


def set_loop(loop: Optional[asyncio.AbstractEventLoop]) -> None:
    """Remember the running event loop (called from the FastAPI lifespan)."""
    global _loop
    _loop = loop


def subscribe() -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_SIZE)
    _subscribers.add(queue)
    return queue


def unsubscribe(queue: asyncio.Queue) -> None:
    _subscribers.discard(queue)


def subscriber_count() -> int:
    return len(_subscribers)


def visible_to(notification: Dict[str, Any], role: Optional[str]) -> bool:
    """Budget managers submit and track budget requests only (PLAN §1.2)."""
    if role == "budget_manager":
        return str(notification.get("resource_type") or "").startswith("budget")
    return True


def history(role: Optional[str] = None) -> List[Dict[str, Any]]:
    """Recent notifications visible to ``role`` (all when None), oldest first."""
    return [n for n in _history if visible_to(n, role)]


def make_notification(
    *,
    action: str,
    resource_type: str,
    resource_id: Optional[int] = None,
    message: str = "",
    user_id: Optional[int] = None,
    username: Optional[str] = None,
) -> Dict[str, Any]:
    global _next_id
    with _id_lock:
        notification_id = _next_id
        _next_id += 1
    notification = {
        "id": notification_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "message": message,
        "user_id": user_id,
        "username": username,
    }
    return notification


def publish(notification: Dict[str, Any]) -> None:
    """Queue a notification for every connected client. Never raises."""
    _history.append(notification)
    if not _subscribers:
        return

    def _deliver() -> None:
        for queue in list(_subscribers):
            try:
                queue.put_nowait(notification)
            except asyncio.QueueFull:
                # A stalled client must not block the publisher: drop the oldest event.
                try:
                    queue.get_nowait()
                    queue.put_nowait(notification)
                except Exception:
                    pass

    if _loop is None or _loop.is_closed():
        # No event loop (tests, CLI use): the ring buffer still holds the notification.
        return
    try:
        _loop.call_soon_threadsafe(_deliver)
    except RuntimeError:  # pragma: no cover - loop closed between check and call
        logger.debug("Event loop unavailable; notification %s not delivered", notification.get("id"))


def publish_on_commit(db: Optional[Session], notification: Dict[str, Any]) -> None:
    """Publish now if ``db`` has nothing uncommitted, otherwise when it commits."""
    if db is None or not db.in_transaction():
        publish(notification)
    else:
        db.info.setdefault(_PENDING_KEY, []).append(notification)


@event.listens_for(Session, "after_commit")
def _publish_pending(session: Session) -> None:
    for notification in session.info.pop(_PENDING_KEY, []):
        publish(notification)


@event.listens_for(Session, "after_soft_rollback")
def _discard_pending(session: Session, previous_transaction) -> None:
    if not previous_transaction.nested:
        session.info.pop(_PENDING_KEY, None)


def publish_from_audit(
    entry: Any, user: Any, summary: Optional[str] = None, db: Optional[Session] = None
) -> None:
    """Publish a notification derived from an AuditLog row (after ``db`` commits)."""
    from app.services.audit import describe

    username = getattr(user, "username", None)
    publish_on_commit(
        db,
        make_notification(
            action=entry.action,
            resource_type=entry.resource_type,
            resource_id=entry.resource_id,
            message=summary or describe(entry, username),
            user_id=entry.user_id,
            username=username,
        )
    )


def format_sse(notification: Dict[str, Any]) -> str:
    """Render a notification as an SSE frame."""
    import json

    return f"id: {notification['id']}\nevent: notification\ndata: {json.dumps(notification, default=str)}\n\n"


def reset() -> None:
    """Clear subscribers and history (used by tests)."""
    global _next_id
    _subscribers.clear()
    _history.clear()
    _next_id = 1
