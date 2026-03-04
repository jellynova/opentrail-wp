from datetime import date, datetime, timezone
from typing import Optional
from sqlalchemy import String, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class BudgetYear(Base):
    __tablename__ = "budget_years"

    id: Mapped[int] = mapped_column(primary_key=True)
    fiscal_year_id: Mapped[int] = mapped_column(Integer, ForeignKey("fiscal_years.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    submission_deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="setup"
    )  # setup / open / under_review / approved / adopted
    instructions_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)


class BudgetRequest(Base):
    __tablename__ = "budget_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    budget_year_id: Mapped[int] = mapped_column(Integer, ForeignKey("budget_years.id"), nullable=False, index=True)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("accounts.id"), nullable=False)
    department: Mapped[str] = mapped_column(String(200), nullable=False)
    prior_year_actual: Mapped[Optional[float]] = mapped_column(Numeric(15, 2), nullable=True)
    prior_year_budget: Mapped[Optional[float]] = mapped_column(Numeric(15, 2), nullable=True)
    proposed_amount: Mapped[Optional[float]] = mapped_column(Numeric(15, 2), nullable=True)
    justification_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    supporting_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    submitted_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    review_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="draft"
    )  # draft / submitted / approved / modified / rejected
    approved_amount: Mapped[Optional[float]] = mapped_column(Numeric(15, 2), nullable=True)


class BudgetLine(Base):
    __tablename__ = "budget_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    budget_year_id: Mapped[int] = mapped_column(Integer, ForeignKey("budget_years.id"), nullable=False, index=True)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("accounts.id"), nullable=False)
    approved_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    budget_type: Mapped[str] = mapped_column(String(20), nullable=False)  # operating / capital
