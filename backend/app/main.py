from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1 import (
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
)

app = FastAPI(
    title="OpenTrail WP",
    description="BC Municipal Government Financial Reporting & Working Paper System",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
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

# Connectors
app.include_router(connectors.router, prefix="/api/v1", tags=["connectors"])

# Budget
app.include_router(budget.router, prefix="/api/v1", tags=["budget"])

# Reports
app.include_router(reports.router, prefix="/api/v1", tags=["reports"])

# Documents / Working Papers
app.include_router(documents.router, prefix="/api/v1", tags=["documents"])


@app.get("/health", tags=["health"])
def health():
    """Health check endpoint."""
    return {"status": "ok", "app": "OpenTrail WP", "version": "0.1.0"}
