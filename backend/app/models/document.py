from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class WorkingPaper(Base):
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

    annotations: Mapped[list["WPAnnotation"]] = relationship(
        "WPAnnotation", back_populates="working_paper", cascade="all, delete-orphan"
    )


class WPAnnotation(Base):
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

    working_paper: Mapped["WorkingPaper"] = relationship("WorkingPaper", back_populates="annotations")
