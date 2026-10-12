"""Phase 8.2: the SSE notification broker and stream endpoint."""
from __future__ import annotations

import asyncio
import json

import pytest

from app.core.security import create_access_token
from app.services import events as events_svc
from tests.conftest import period_of


@pytest.fixture(autouse=True)
def clean_broker():
    events_svc.reset()
    yield
    events_svc.reset()


class _StubRequest:
    """Minimal Request stand-in: only what the stream endpoint touches."""

    def __init__(self):
        self.headers = {}

    async def is_disconnected(self) -> bool:
        return False


def test_broker_publish_history_and_format():
    assert events_svc.history() == []
    note = events_svc.make_notification(
        action="post", resource_type="journal_entry", resource_id=7, message="posted AJE-001", username="officer"
    )
    events_svc.publish(note)

    assert events_svc.history() == [note]
    frame = events_svc.format_sse(note)
    assert frame.startswith(f"id: {note['id']}\nevent: notification\ndata: ")
    assert frame.endswith("\n\n")
    payload = json.loads(frame.split("data: ", 1)[1].strip())
    assert payload["message"] == "posted AJE-001"
    assert payload["username"] == "officer"


def test_publish_reaches_subscribers_without_a_loop():
    queue = events_svc.subscribe()
    assert events_svc.subscriber_count() == 1
    events_svc.publish(events_svc.make_notification(action="create", resource_type="report", message="x"))
    events_svc.unsubscribe(queue)
    assert events_svc.subscriber_count() == 0


def test_activity_is_published_as_notifications(client, auth, fy2025, users, db):
    period = period_of(fy2025, 3)
    account = client.post(
        "/api/v1/accounts",
        json={"fiscal_year_id": fy2025.id, "acct_fmtd": "1000", "description": "Cash"},
        headers=auth("officer"),
    ).json()
    entry = client.post(
        "/api/v1/journal-entries",
        json={
            "period_id": period.id,
            "entry_date": str(period.end_date),
            "entry_type": "adjusting",
            "lines": [
                {"account_id": account["id"], "debit": "10"},
                {"account_id": account["id"], "credit": "10"},
            ],
        },
        headers=auth("officer"),
    ).json()
    client.post(f"/api/v1/journal-entries/{entry['id']}/post", headers=auth("officer"))

    recent = client.get("/api/v1/events/recent", headers=auth("viewer"))
    assert recent.status_code == 200
    messages = [n["message"] for n in recent.json()]
    assert any("posted journal entry" in m for m in messages)
    newest = recent.json()[0]
    assert newest["username"] == "officer"
    assert newest["resource_type"] == "journal_entry"

    limited = client.get("/api/v1/events/recent", params={"limit": 1}, headers=auth("viewer")).json()
    assert len(limited) == 1


def test_stream_requires_a_valid_token(client, users, db):
    assert client.get("/api/v1/events/stream").status_code == 401
    assert client.get("/api/v1/events/stream", params={"token": "not-a-token"}).status_code == 401


def test_stream_sends_ready_frame_with_recent_activity(client, auth, users, db, engine):
    from sqlalchemy.orm import sessionmaker

    from app.api.v1.events import stream_events

    events_svc.publish(
        events_svc.make_notification(action="close", resource_type="period", resource_id=1, message="closed March")
    )

    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()
    try:
        token = create_access_token({"sub": str(users["viewer"].id)})
        response = asyncio.run(stream_events(request=_StubRequest(), token=token, db=session))
        assert response.media_type == "text/event-stream"
        assert response.headers["x-accel-buffering"] == "no"

        async def first_frame():
            iterator = response.body_iterator
            return await anext(iterator)

        frame = asyncio.run(first_frame())
        assert frame.startswith("event: ready\ndata: ")
        payload = json.loads(frame.split("data: ", 1)[1].strip())
        assert payload["user"] == "viewer"
        assert payload["recent"][0]["message"] == "closed March"
    finally:
        session.close()


def test_notifications_wait_for_commit_and_drop_on_rollback(db, users):
    from app.services import audit as audit_svc

    audit_svc.record(db, user=users["officer"], action="post", resource_type="journal_entry",
                     resource_id=1, summary="officer posted AJE-001")
    assert events_svc.history() == []  # flushed, not yet committed
    db.rollback()
    assert events_svc.history() == []

    audit_svc.record(db, user=users["officer"], action="post", resource_type="journal_entry",
                     resource_id=2, summary="officer posted AJE-002")
    db.commit()
    assert [n["message"] for n in events_svc.history()] == ["officer posted AJE-002"]


def test_budget_managers_only_see_budget_events(client, auth):
    for rtype in ("journal_entry", "budget_request", "document"):
        events_svc.publish(events_svc.make_notification(action="update", resource_type=rtype, message=rtype))
    assert [n["message"] for n in client.get("/api/v1/events/recent", headers=auth("parks_mgr")).json()] == [
        "budget_request"
    ]
    assert len(client.get("/api/v1/events/recent", headers=auth("viewer")).json()) == 3


def test_stream_releases_its_db_session(users, engine):
    from sqlalchemy.orm import sessionmaker

    from app.api.v1.events import stream_events

    session = sessionmaker(bind=engine)()
    token = create_access_token({"sub": str(users["parks_mgr"].id)})
    events_svc.publish(events_svc.make_notification(action="post", resource_type="journal_entry", message="je"))
    response = asyncio.run(stream_events(request=_StubRequest(), token=token, db=session))
    assert not session.in_transaction()  # connection returned to the pool before streaming

    frame = asyncio.run(anext(response.body_iterator))
    assert json.loads(frame.split("data: ", 1)[1])["recent"] == []  # filtered for budget managers
