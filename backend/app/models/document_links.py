"""
Leadsheet-to-document links (PLAN §4.3/§7): tie a working paper document to a
specific lead-sheet account code so reviewers can jump from a leadsheet line to
the supporting evidence (and back from the Documents binder).
"""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class DocumentAccountLink(Base):
    """One account code attached to one working paper document (any version row)."""

    __tablename__ = "document_account_links"
    __table_args__ = (
        UniqueConstraint("working_paper_id", "account_code", name="uq_wp_account_link"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    working_paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("working_papers.id"), nullable=False, index=True
    )
    account_code: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    fiscal_year_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("fiscal_years.id"), nullable=False, index=True
    )
    created_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    working_paper: Mapped["WorkingPaper"] = relationship(
        "WorkingPaper", back_populates="account_links"
    )  # noqa: F821


class DocumentCrossLink(Base):
    """
    A cross-reference between two working paper documents (distinct from
    DocumentAccountLink, which ties a document to a TB/GL account code): e.g. "this
    adjustment memo supports that bank reconciliation", so reviewers can navigate between
    related evidence directly, not just from a document to its leadsheet account.

    Stored as one directed row per pair; ``document_id`` is whichever side the link was
    created from and ``related_document_id`` the other, but the relationship itself is
    symmetric — the API returns it from both documents' perspectives and refuses a
    duplicate in either direction.
    """

    __tablename__ = "document_cross_links"
    __table_args__ = (
        UniqueConstraint("document_id", "related_document_id", name="uq_document_cross_link"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("working_papers.id"), nullable=False, index=True
    )
    related_document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("working_papers.id"), nullable=False, index=True
    )
    note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
