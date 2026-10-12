"""
Materiality (PLAN gap vs. CaseWare): set a dollar threshold per fiscal year, then flag
leadsheet accounts whose balance exceeds it but have no supporting document attached --
the gaps most worth a reviewer's attention first, not merely the biggest balances.
"""
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document_links import DocumentAccountLink
from app.models.account_comment import AccountComment
from app.models.materiality import Materiality
from app.services.working_papers import get_period, leadsheets


def get_materiality(db: Session, fiscal_year_id: int) -> Optional[Materiality]:
    return db.scalars(select(Materiality).where(Materiality.fiscal_year_id == fiscal_year_id)).first()


def set_materiality(
    db: Session,
    fiscal_year_id: int,
    *,
    overall_materiality: Decimal,
    performance_materiality: Optional[Decimal],
    trivial_threshold: Optional[Decimal],
    basis: Optional[str],
    rationale: Optional[str],
    user_id: int,
) -> Materiality:
    """Create or replace the fiscal year's materiality record (one per year)."""
    row = get_materiality(db, fiscal_year_id)
    if row is None:
        row = Materiality(fiscal_year_id=fiscal_year_id, overall_materiality=overall_materiality, set_by_user_id=user_id)
        db.add(row)
    row.overall_materiality = overall_materiality
    row.performance_materiality = performance_materiality
    row.trivial_threshold = trivial_threshold
    row.basis = basis
    row.rationale = rationale
    row.set_by_user_id = user_id
    db.flush()
    return row


def flagging_threshold(materiality: Materiality) -> Decimal:
    """Performance materiality if set (the more conservative, actually-tested figure), else overall."""
    return materiality.performance_materiality if materiality.performance_materiality is not None else materiality.overall_materiality


def unsupported_material_accounts(db: Session, period_id: int, scheme: Any = "PSAB") -> Dict[str, Any]:
    """
    Leadsheet accounts through ``period_id`` whose |final balance| meets or exceeds the
    fiscal year's flagging threshold but carry zero DocumentAccountLink rows AND zero
    AccountComment rows -- an account is "supported" either by an attached document or
    by a comment explaining the variance, since not every material balance needs a file.
    Returns an empty, threshold-less result (not an error) when no materiality has been
    set yet -- the feature is opt-in per fiscal year.
    """
    period = get_period(db, period_id)
    materiality = get_materiality(db, period.fiscal_year_id)
    if materiality is None:
        return {"period_id": period_id, "threshold": None, "threshold_basis": None, "accounts": []}

    threshold = flagging_threshold(materiality)
    basis = "performance_materiality" if materiality.performance_materiality is not None else "overall_materiality"

    linked_codes = set(
        db.scalars(
            select(DocumentAccountLink.account_code).where(
                DocumentAccountLink.fiscal_year_id == period.fiscal_year_id
            )
        ).all()
    )
    commented_codes = set(
        db.scalars(
            select(AccountComment.account_code).where(AccountComment.fiscal_year_id == period.fiscal_year_id)
        ).all()
    )
    supported_codes = linked_codes | commented_codes

    result = leadsheets(db, period_id, scheme)
    flagged = []
    for group in result["leadsheets"]:
        for acct in group["accounts"]:
            final = acct["final"]
            if abs(final) >= threshold and acct["acct_fmtd"] not in supported_codes:
                flagged.append(
                    {
                        "account_id": acct["account_id"],
                        "acct_fmtd": acct["acct_fmtd"],
                        "description": acct["description"],
                        "classification": group["classification"],
                        "final_balance": final,
                        "threshold": threshold,
                        "excess": abs(final) - threshold,
                    }
                )
    flagged.sort(key=lambda r: r["excess"], reverse=True)
    return {"period_id": period_id, "threshold": threshold, "threshold_basis": basis, "accounts": flagged}
