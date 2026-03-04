from datetime import date, datetime, timezone
from typing import Optional
from sqlalchemy import String, Date, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    period_id: Mapped[int] = mapped_column(Integer, ForeignKey("periods.id"), nullable=False, index=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    entry_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # adjusting / reclassifying / elimination / budget_variance
    prepared_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    reviewed_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")  # draft / posted / approved
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    lines: Mapped[list["JournalLine"]] = relationship(
        "JournalLine", back_populates="journal_entry", cascade="all, delete-orphan"
    )


class JournalLine(Base):
    __tablename__ = "journal_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    journal_entry_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("journal_entries.id"), nullable=False, index=True
    )
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("accounts.id"), nullable=False)
    debit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    credit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    gl_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    journal_entry: Mapped["JournalEntry"] = relationship("JournalEntry", back_populates="lines")
