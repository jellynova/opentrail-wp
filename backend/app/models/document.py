from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Float, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class WorkingPaper(Base):
    """
    One *version* of a working paper file (PLAN §7.1).

    Every upload creates a row; a new version of an existing document is a new row with
    ``version_number`` incremented and ``parent_version_id`` pointing at the document's
    first version (the root). The root row is the document; its latest version is what the
    UI lists. Sign-off state (PLAN §7.2) lives on the version row, because a reviewer
    signs off on the file they actually reviewed — uploading a replacement version
    therefore leaves the document unsigned until it is reviewed again.
    """

    __tablename__ = "working_papers"

    id: Mapped[int] = mapped_column(primary_key=True)
    fiscal_year_id: Mapped[int] = mapped_column(Integer, ForeignKey("fiscal_years.id"), nullable=False, index=True)
    folder_path: Mapped[str] = mapped_column(String(500), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)  # pdf / xlsx / docx / img / other
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_version_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("working_papers.id"), nullable=True
    )

    # Shared-drive storage (CaseWare-style: the organization's own network drive /
    # SharePoint sync folder is the single canonical copy, not a byte copy inside
    # OpenTrail). "managed" = OpenTrail's own documents volume (original behaviour,
    # still used for anything uploaded before SHARED_DRIVE_PATH was configured).
    storage_backend: Mapped[str] = mapped_column(String(20), nullable=False, default="managed")
    # sha256 hex + mtime of the underlying file the last time OpenTrail confirmed it --
    # lets a cheap stat-only check notice someone edited or moved the file directly on
    # the shared drive (outside the app) without having to re-hash on every request.
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_mtime: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Set when a drift check finds the live file missing (deleted/moved externally);
    # cleared the moment a new version or re-link restores it. Null = fine.
    missing_since: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Where this version's PREVIOUS content was backed up (relative to SHARED_DRIVE_PATH)
    # right before this version's bytes overwrote the canonical file in place -- only set
    # for shared_drive documents past their first version. The backup lives on the same
    # shared drive, not inside OpenTrail, so there is still exactly one filing system.
    backup_path: Mapped[Optional[str]] = mapped_column(String(600), nullable=True)

    # Two-level sign-off (PLAN §7.2): preparer marks complete, reviewer approves.
    preparer_signed_off_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    preparer_signed_off_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_signed_off_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    reviewer_signed_off_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set when a signed-off document is modified (new version, metadata edit): the
    # document must be re-reviewed before it counts as complete again.
    requires_reapproval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Set when a version is superseded, so history stays readable.
    superseded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    annotations: Mapped[list["WPAnnotation"]] = relationship(
        "WPAnnotation", back_populates="working_paper", cascade="all, delete-orphan"
    )
    # Leadsheet account codes this document supports (PLAN §4.3). No cascade: links
    # are removed explicitly, and deleting a document removes them at the DB level.
    account_links: Mapped[list["DocumentAccountLink"]] = relationship(
        "DocumentAccountLink", back_populates="working_paper"
    )

    @property
    def root_id(self) -> int:
        """The document's first version id (the row that represents the document)."""
        return self.parent_version_id or self.id

    @property
    def is_preparer_signed_off(self) -> bool:
        return self.preparer_signed_off_at is not None

    @property
    def is_reviewer_signed_off(self) -> bool:
        return self.reviewer_signed_off_at is not None

    @property
    def is_shared_drive(self) -> bool:
        return self.storage_backend == "shared_drive"

    @property
    def is_missing(self) -> bool:
        return self.missing_since is not None


class WPAnnotation(Base):
    """A review note on a working paper (PLAN §7.1)."""

    __tablename__ = "wp_annotations"

    id: Mapped[int] = mapped_column(primary_key=True)
    working_paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("working_papers.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    working_paper: Mapped["WorkingPaper"] = relationship("WorkingPaper", back_populates="annotations")
