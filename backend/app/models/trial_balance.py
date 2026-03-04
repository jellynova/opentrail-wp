from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class TrialBalanceEntry(Base):
    __tablename__ = "trial_balance_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    period_id: Mapped[int] = mapped_column(Integer, ForeignKey("periods.id"), nullable=False, index=True)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    opening_debit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    opening_credit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    period_debit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    period_credit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    ytd_debit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    ytd_credit: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    source: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # connector_pull / csv_import / manual
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    connector_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("external_connectors.id"), nullable=True
    )
