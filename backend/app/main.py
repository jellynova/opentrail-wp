import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, engine, SessionLocal
from app.core.schema_sync import sync_columns
from app.core.security import hash_password
logger = logging.getLogger(__name__)

from app.api.v1 import (
    audit,
    auth,
    users,
    periods,
    accounts,
    trial_balance,
    journal_entries,
    reports,
    documents,
    budget,
    connectors,
    working_papers,
    sofi,
    events,
)


def _init_db() -> None:
    """
    Create all tables, add any columns an existing installation is missing, seed a default
    admin user if none exist, and seed built-in report templates.
    """
    import app.models  # noqa: F401 — ensures all models are registered with Base.metadata
    Base.metadata.create_all(bind=engine)

    # create_all does not add columns to tables that already exist, so an upgrade would
    # otherwise fail at query time on any newly introduced column.
    added = sync_columns(engine)
    if added:
        # Warning level on purpose: this only happens on an upgrade, and the operator
        # should be able to see it in the container logs.
        logger.warning("Schema sync added %d column(s): %s", len(added), ", ".join(added))

    db = SessionLocal()
    try:
        from app.models.user import User
        from sqlalchemy import select
        if not db.scalars(select(User)).first():
            db.add(User(
                username="admin",
                email="admin@opentrail.local",
                hashed_password=hash_password("admin123"),
                role="finance_admin",
                is_active=True,
                created_at=datetime.now(timezone.utc),
            ))
            db.commit()

        from app.services.builtin_templates import seed_templates
        admin = db.scalars(select(User).where(User.role == "finance_admin").order_by(User.id)).first()
        seed_templates(db, admin.id if admin else db.scalars(select(User)).first().id)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_db()
    # The SSE broker publishes from sync request handlers running in a threadpool, so it
    # needs a handle on this loop (PLAN §8.2).
    from app.services import events as events_svc

    events_svc.set_loop(asyncio.get_running_loop())
    try:
        yield
    finally:
        events_svc.set_loop(None)

app = FastAPI(
    lifespan=lifespan,
    title="OpenTrail WP",
    description="BC Municipal Government Financial Reporting & Working Paper System",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])

# Users
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])

# Fiscal Years & Periods — router handles its own full paths
app.include_router(periods.router, prefix="/api/v1", tags=["periods"])

# Accounts, Mapping Schemes, Segment Definitions
app.include_router(accounts.router, prefix="/api/v1", tags=["accounts"])

# Trial Balance
app.include_router(trial_balance.router, prefix="/api/v1", tags=["trial-balance"])

# Journal Entries
app.include_router(journal_entries.router, prefix="/api/v1", tags=["journal-entries"])

# Working papers (working TB, leadsheets, AJE/RJE schedules)
app.include_router(working_papers.router, prefix="/api/v1", tags=["working-papers"])

# Connectors
app.include_router(connectors.router, prefix="/api/v1", tags=["connectors"])

# Budget
app.include_router(budget.router, prefix="/api/v1", tags=["budget"])

# Reports
app.include_router(reports.router, prefix="/api/v1", tags=["reports"])

# Statement of Financial Information schedules
app.include_router(sofi.router, prefix="/api/v1", tags=["sofi"])

# Documents / Working Papers
app.include_router(documents.router, prefix="/api/v1", tags=["documents"])

# Live activity notifications (SSE)
app.include_router(events.router, prefix="/api/v1", tags=["events"])

# Audit trail / activity log
app.include_router(audit.router, prefix="/api/v1", tags=["audit"])


@app.get("/health", tags=["health"])
def health():
    """Health check endpoint."""
    return {"status": "ok", "app": "OpenTrail WP", "version": "0.1.0"}
