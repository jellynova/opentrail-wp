from typing import Optional
from sqlalchemy import String, Boolean, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class SegmentDefinition(Base):
    __tablename__ = "segment_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    connector_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("external_connectors.id"), nullable=True
    )
    segment_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-10
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
