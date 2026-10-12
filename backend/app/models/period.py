from datetime import date, datetime, timezone
from typing import Optional
from sqlalchemy import String, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class FiscalYear(Base):
    __tablename__ = "fiscal_years"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. "2024"
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")  # open / closed / locked
    # Set when this year was created by rolling a prior year forward (PLAN §7.3).
    source_fiscal_year_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("fiscal_years.id"), nullable=True
    )

    periods: Mapped[list["Period"]] = relationship("Period", back_populates="fiscal_year", cascade="all, delete-orphan")


class Period(Base):
    __tablename__ = "periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    fiscal_year_id: Mapped[int] = mapped_column(Integer, ForeignKey("fiscal_years.id"), nullable=False, index=True)
    period_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-12
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    fiscal_year: Mapped["FiscalYear"] = relationship("FiscalYear", back_populates="periods")


class PeriodClose(Base):
    """
    Immutable record of a period close (PLAN §7.3).

    The closing balance snapshot deliberately does **not** overwrite
    ``TrialBalanceEntry``: those rows hold *unadjusted* ERP figures, and the balance engine
    adds posted journal adjustments on top of them (see ``app.services.balances``). Writing
    adjusted figures back into the trial balance would double-count every AJE/RJE. The
    snapshot therefore lives here, one ``PeriodCloseBalance`` row per account, and is the
    authoritative record of what the books showed at close.
    """

    __tablename__ = "period_closes"

    id: Mapped[int] = mapped_column(primary_key=True)
    period_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("periods.id"), nullable=False, unique=True, index=True
    )
    closed_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    closed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    journal_entry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    account_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_debits: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    total_credits: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    is_balanced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Pre-close checks the closer had to override (finance_admin only), for the audit trail.
    overrides: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Set when the period was reopened for corrections; the snapshot below is replaced
    # if the period is closed again.
    reopened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reopened_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    balances: Mapped[list["PeriodCloseBalance"]] = relationship(
        "PeriodCloseBalance", back_populates="period_close", cascade="all, delete-orphan"
    )


class PeriodCloseBalance(Base):
    """Closing balance for one account at period close (signed debit-positive)."""

    __tablename__ = "period_close_balances"

    id: Mapped[int] = mapped_column(primary_key=True)
    period_close_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("period_closes.id"), nullable=False, index=True
    )
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    acct_fmtd: Mapped[str] = mapped_column(String(30), nullable=False)  # denormalised: survives COA edits
    opening: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    ytd_debit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    ytd_credit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    period_debit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    period_credit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    aje_debit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    aje_credit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    rje_debit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    rje_credit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    closing: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)

    period_close: Mapped["PeriodClose"] = relationship("PeriodClose", back_populates="balances")
