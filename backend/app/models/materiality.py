"""
Materiality (PSAB/GAAS planning concept, PLAN gap vs. CaseWare): the dollar threshold
above which a gap or misstatement matters enough to flag for a reviewer. Kept
deliberately narrow here — not a full risk-assessment module — specifically so leadsheet
accounts with a material balance and zero supporting documents can be surfaced first.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Materiality(Base):
    __tablename__ = "materiality"

    id: Mapped[int] = mapped_column(primary_key=True)
    fiscal_year_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("fiscal_years.id"), nullable=False, unique=True, index=True
    )
    overall_materiality: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    # Typically 50-75% of overall; when set, used as the flagging threshold instead of
    # overall, since it's the more conservative figure auditors actually test against.
    performance_materiality: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    # Below this, gaps are clearly trivial and not worth flagging at all (not currently
    # enforced in the flagging query itself, but surfaced for the UI/rationale record).
    trivial_threshold: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    basis: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # e.g. "2% of total revenue"
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    set_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    set_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
