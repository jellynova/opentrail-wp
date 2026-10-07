"""
Shared pytest fixtures.

Tests run against an in-memory SQLite database (no PostgreSQL required) with the
FastAPI `get_db` dependency overridden. The app lifespan (which seeds an admin user
against the real DATABASE_URL) is not triggered because TestClient is not used as a
context manager.
"""
from __future__ import annotations

from datetime import date
from typing import Callable, Dict

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — register all models on Base.metadata
from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import app as fastapi_app
from app.models.account import Account
from app.models.period import FiscalYear, Period
from app.models.user import User


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine) -> Session:
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    yield session
    session.close()


@pytest.fixture()
def client(engine) -> TestClient:
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def _override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()


@pytest.fixture()
def users(db) -> Dict[str, User]:
    """One user per role, plus a second finance officer (for segregation-of-duties tests)."""
    specs = [
        ("admin", "finance_admin", None),
        ("officer", "finance_officer", None),
        ("officer2", "finance_officer", None),
        ("parks_mgr", "budget_manager", "Parks"),
        ("roads_mgr", "budget_manager", "Roads"),
        ("viewer", "viewer", None),
    ]
    created = {}
    for username, role, dept in specs:
        u = User(
            username=username,
            email=f"{username}@town.example.ca",
            hashed_password=hash_password("pw"),
            role=role,
            department=dept,
            is_active=True,
        )
        db.add(u)
        created[username] = u
    db.commit()
    for u in created.values():
        db.refresh(u)
    return created


@pytest.fixture()
def auth(users) -> Callable[[str], Dict[str, str]]:
    """auth("officer") -> Authorization header dict for that user."""

    def _headers(username: str) -> Dict[str, str]:
        token = create_access_token({"sub": str(users[username].id)})
        return {"Authorization": f"Bearer {token}"}

    return _headers


def make_fiscal_year(db: Session, year: int) -> FiscalYear:
    fy = FiscalYear(label=str(year), start_date=date(year, 1, 1), end_date=date(year, 12, 31), status="open")
    db.add(fy)
    db.flush()
    for n in range(1, 13):
        start = date(year, n, 1)
        end = date(year, 12, 31) if n == 12 else date(year, n + 1, 1).replace(day=1)
        if n != 12:
            from datetime import timedelta

            end = end - timedelta(days=1)
        db.add(
            Period(
                fiscal_year_id=fy.id,
                period_number=n,
                name=start.strftime("%B"),
                start_date=start,
                end_date=end,
                is_closed=False,
            )
        )
    db.commit()
    db.refresh(fy)
    return fy


def make_account(db: Session, fy: FiscalYear, acct_fmtd: str, description: str, **kw) -> Account:
    acct = Account(fiscal_year_id=fy.id, acct_fmtd=acct_fmtd, description=description, is_active=True, **kw)
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return acct


def period_of(fy: FiscalYear, n: int) -> Period:
    return next(p for p in fy.periods if p.period_number == n)


@pytest.fixture()
def fy2025(db) -> FiscalYear:
    return make_fiscal_year(db, 2025)
