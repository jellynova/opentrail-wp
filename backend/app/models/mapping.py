from typing import Optional
from sqlalchemy import String, Boolean, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class MappingScheme(Base):
    __tablename__ = "mapping_schemes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)  # e.g. "PSAB", "Management", "Audit File"
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AccountClassification(Base):
    __tablename__ = "account_classifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    scheme_id: Mapped[int] = mapped_column(Integer, ForeignKey("mapping_schemes.id"), nullable=False, index=True)
    classification_value: Mapped[str] = mapped_column(
        String(200), nullable=False
    )  # e.g. "revenue", "expense", "financial_assets"
    sort_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
