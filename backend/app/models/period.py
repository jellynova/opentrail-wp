from datetime import date, datetime, timezone
from sqlalchemy import String, Boolean, Date, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class FiscalYear(Base):
    __tablename__ = "fiscal_years"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. "2024"
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")  # open / closed / locked

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
