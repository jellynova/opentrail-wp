from typing import Optional
from sqlalchemy import String, Boolean, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    fiscal_year_id: Mapped[int] = mapped_column(Integer, ForeignKey("fiscal_years.id"), nullable=False, index=True)
    acct_fmtd: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    acct_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    record_class: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    capital_acct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    dept_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    fund_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    stat: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    total_lvl: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_lvl_cde: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    rev_exp_rpt: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    object_str: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    project_str: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)

    # Segment codes (integer codes from ERP)
    seg1: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    seg2: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    seg3: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    seg4: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    seg5: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    seg6: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    seg7: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    seg8: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    seg9: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    seg10: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Segment descriptions
    seg1_descr: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    seg2_descr: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    seg3_descr: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    seg4_descr: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    seg5_descr: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    seg6_descr: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    seg7_descr: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    seg8_descr: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    seg9_descr: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    seg10_descr: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    normal_balance: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # debit / credit
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source_system: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # amais / vadim / csv / manual
    connector_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("external_connectors.id"), nullable=True
    )


class AccountMapping(Base):
    __tablename__ = "account_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    source_acct_fmtd: Mapped[str] = mapped_column(String(30), nullable=False)
