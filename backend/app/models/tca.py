from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

ZERO = Decimal("0")


class TcaScheduleLine(Base):
    """
    One asset class in the tangible capital asset continuity schedule (PS 3150).

    The schedule is a continuity statement by asset class: cost and accumulated
    amortization each roll from opening to closing through additions/amortization and
    disposals, and net book value is the difference. Municipalities keep it in a
    spreadsheet (PLAN §3.2 — the AMAIS `fa-hdr` module is empty at the reference
    installation), so rows arrive by CSV import or manual entry rather than from the GL.

    Closing and net-book-value figures are derived, never stored, so the schedule can
    never disagree with itself.
    """

    __tablename__ = "tca_schedule_lines"
    __table_args__ = (UniqueConstraint("fiscal_year_id", "asset_class", name="uq_tca_year_class"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fiscal_year_id: Mapped[int] = mapped_column(Integer, ForeignKey("fiscal_years.id"), nullable=False, index=True)
    asset_class: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    cost_opening: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    cost_additions: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    cost_disposals: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)

    amort_opening: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    amort_expense: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    amort_disposals: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)

    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")  # csv / manual
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def _d(self, value) -> Decimal:
        return Decimal(str(value)) if value is not None else ZERO

    @property
    def cost_closing(self) -> Decimal:
        return self._d(self.cost_opening) + self._d(self.cost_additions) - self._d(self.cost_disposals)

    @property
    def amort_closing(self) -> Decimal:
        return self._d(self.amort_opening) + self._d(self.amort_expense) - self._d(self.amort_disposals)

    @property
    def nbv_opening(self) -> Decimal:
        return self._d(self.cost_opening) - self._d(self.amort_opening)

    @property
    def nbv_closing(self) -> Decimal:
        return self.cost_closing - self.amort_closing
