"""
Account-level comments (PLAN gap: explain a variance without needing a document).

Lighter-weight than a DocumentAccountLink -- a reviewer who just needs to say "variance
is the Q3 rate increase, no document needed" can do that directly on the account instead
of being forced to attach a file. Counts the same as a document link for materiality
flagging purposes (app.services.materiality_service.unsupported_material_accounts).
"""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class AccountComment(Base):
    __tablename__ = "account_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_code: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    fiscal_year_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("fiscal_years.id"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    # Mirrors WPAnnotation's resolve/reopen pattern: a variance explanation can be marked
    # settled, then reopened later if a reviewer disagrees.
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
