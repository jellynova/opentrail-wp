from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class SofiEntry(Base):
    """
    Source rows for the Statement of Financial Information (Financial Information Act)
    schedules. One row per payment/payee (supplier payments), per person (employee
    remuneration) or per agreement (guarantees and indemnities). Rows are imported
    from CSV (e.g. an AP vendor-payment or payroll export) or entered manually.
    """

    __tablename__ = "sofi_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    fiscal_year_id: Mapped[int] = mapped_column(Integer, ForeignKey("fiscal_years.id"), nullable=False, index=True)
    schedule_type: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True
    )  # supplier_payment / employee_remuneration / guarantee_indemnity
    name: Mapped[str] = mapped_column(String(300), nullable=False)  # supplier, employee or agreement
    position: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # employee title / office
    is_elected_official: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)  # payment / remuneration
    expenses: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)  # employee expenses
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")  # csv / manual
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
