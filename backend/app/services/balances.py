"""
Account balance engine shared by the working trial balance, leadsheets, the report
builder and budget variance analysis.

Conventions
-----------
* All amounts are signed **debit-positive** (debit − credit). Presentation layers flip
  the sign for credit-natured lines (revenue, liabilities, surplus).
* TrialBalanceEntry.ytd_* are year-to-date *movements* (excluding the opening balance),
  so the unadjusted closing balance is ``opening + ytd``.
* "Through period N" uses, per account, the TB entry with the highest period_number ≤ N
  (YTD figures are cumulative, so later entries supersede earlier ones).
* Journal adjustments are cumulative within the fiscal year: every posted/approved entry
  in periods 1..N counts. ``adjusting`` and ``reclassifying`` entries flow to the working
  trial balance and financial statements; ``elimination`` entries only to consolidated
  views; ``budget_variance`` entries never touch actuals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.journal_entry import JournalEntry, JournalLine
from app.models.mapping import AccountClassification, MappingScheme
from app.models.period import FiscalYear, Period
from app.models.trial_balance import TrialBalanceEntry

ZERO = Decimal("0")
POSTED_STATUSES = ("posted", "approved")
STATEMENT_ENTRY_TYPES = ("adjusting", "reclassifying")

# PSAB classifications whose natural balance is a credit. Values may be hierarchical
# ("liabilities.debt"); the top-level segment decides.
CREDIT_NATURED_CLASSES = {"liabilities", "revenue", "accumulated_surplus"}


def D(value) -> Decimal:
    return Decimal(str(value)) if value is not None else ZERO


@dataclass
class AccountBalance:
    account_id: int
    opening: Decimal = ZERO  # opening balance for the fiscal year
    ytd: Decimal = ZERO  # unadjusted YTD movement from the TB
    period_debit: Decimal = ZERO
    period_credit: Decimal = ZERO
    opening_debit: Decimal = ZERO
    opening_credit: Decimal = ZERO
    ytd_debit: Decimal = ZERO
    ytd_credit: Decimal = ZERO
    adjustments: Dict[str, Dict[str, Decimal]] = field(default_factory=dict)  # type -> {debit, credit}

    @property
    def unadjusted(self) -> Decimal:
        return self.opening + self.ytd

    def adj_debit(self, entry_type: str) -> Decimal:
        return self.adjustments.get(entry_type, {}).get("debit", ZERO)

    def adj_credit(self, entry_type: str) -> Decimal:
        return self.adjustments.get(entry_type, {}).get("credit", ZERO)

    def adj_net(self, entry_type: str) -> Decimal:
        return self.adj_debit(entry_type) - self.adj_credit(entry_type)

    def closing(self, entry_types: Iterable[str] = STATEMENT_ENTRY_TYPES) -> Decimal:
        return self.unadjusted + sum((self.adj_net(t) for t in entry_types), ZERO)

    def movement(self, entry_types: Iterable[str] = STATEMENT_ENTRY_TYPES) -> Decimal:
        return self.closing(entry_types) - self.opening


def last_period_number(db: Session, fiscal_year_id: int) -> int:
    numbers = db.scalars(select(Period.period_number).where(Period.fiscal_year_id == fiscal_year_id)).all()
    return max(numbers, default=12)


def account_balances(
    db: Session,
    fiscal_year_id: int,
    through_period: Optional[int] = None,
) -> Dict[int, AccountBalance]:
    """Balances for every account with TB data or adjustments, through `through_period`."""
    if through_period is None:
        through_period = last_period_number(db, fiscal_year_id)

    periods = db.scalars(
        select(Period).where(Period.fiscal_year_id == fiscal_year_id, Period.period_number <= through_period)
    ).all()
    period_num = {p.id: p.period_number for p in periods}
    if not period_num:
        return {}

    balances: Dict[int, AccountBalance] = {}
    latest: Dict[int, int] = {}
    entries = db.scalars(select(TrialBalanceEntry).where(TrialBalanceEntry.period_id.in_(period_num))).all()
    for e in entries:
        n = period_num[e.period_id]
        if n < latest.get(e.account_id, -1):
            continue
        latest[e.account_id] = n
        b = AccountBalance(account_id=e.account_id)
        b.opening_debit, b.opening_credit = D(e.opening_debit), D(e.opening_credit)
        b.ytd_debit, b.ytd_credit = D(e.ytd_debit), D(e.ytd_credit)
        b.opening = b.opening_debit - b.opening_credit
        b.ytd = b.ytd_debit - b.ytd_credit
        if n == through_period:
            b.period_debit, b.period_credit = D(e.period_debit), D(e.period_credit)
        balances[e.account_id] = b

    rows = db.execute(
        select(JournalEntry.entry_type, JournalLine.account_id, JournalLine.debit, JournalLine.credit)
        .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
        .where(JournalEntry.period_id.in_(period_num), JournalEntry.status.in_(POSTED_STATUSES))
    ).all()
    for entry_type, account_id, debit, credit in rows:
        b = balances.setdefault(account_id, AccountBalance(account_id=account_id))
        adj = b.adjustments.setdefault(entry_type, {"debit": ZERO, "credit": ZERO})
        adj["debit"] += D(debit)
        adj["credit"] += D(credit)

    return balances


def load_accounts(db: Session, account_ids: Iterable[int]) -> Dict[int, Account]:
    ids = list(set(account_ids))
    if not ids:
        return {}
    return {a.id: a for a in db.scalars(select(Account).where(Account.id.in_(ids))).all()}


def resolve_scheme_id(db: Session, scheme: Optional[object]) -> Optional[int]:
    """Accept a scheme id or name (case-insensitive); default to the "PSAB" scheme."""
    if isinstance(scheme, int):
        return scheme
    if isinstance(scheme, str) and scheme.isdigit():
        return int(scheme)
    name = (scheme or "PSAB")
    for s in db.scalars(select(MappingScheme)).all():
        if s.name.lower() == str(name).lower():
            return s.id
    return None


def classifications(db: Session, scheme_id: Optional[int], account_ids: Iterable[int]) -> Dict[int, str]:
    ids = list(set(account_ids))
    if scheme_id is None or not ids:
        return {}
    rows = db.scalars(
        select(AccountClassification).where(
            AccountClassification.scheme_id == scheme_id, AccountClassification.account_id.in_(ids)
        )
    ).all()
    return {c.account_id: c.classification_value for c in rows}


def is_credit_natured(account: Optional[Account], classification: Optional[str] = None) -> bool:
    """Natural side of an account: explicit normal_balance wins, then PSAB classification."""
    if account is not None and account.normal_balance in ("debit", "credit"):
        return account.normal_balance == "credit"
    if classification:
        return classification.split(".")[0].lower() in CREDIT_NATURED_CLASSES
    return False


def prior_fiscal_year(db: Session, fiscal_year_id: int, offset: int = 1) -> Optional[FiscalYear]:
    """The fiscal year `offset` years before the given one (ordered by start date)."""
    years = db.scalars(select(FiscalYear).order_by(FiscalYear.start_date)).all()
    ids = [y.id for y in years]
    if fiscal_year_id not in ids:
        return None
    idx = ids.index(fiscal_year_id) - offset
    return years[idx] if 0 <= idx < len(years) else None


def accounts_by_code(db: Session, fiscal_year_id: int) -> Dict[str, Account]:
    return {
        a.acct_fmtd: a
        for a in db.scalars(select(Account).where(Account.fiscal_year_id == fiscal_year_id)).all()
    }


def match_classification(value: Optional[str], patterns: List[str]) -> bool:
    """
    Exact match, or hierarchical match for patterns ending in '*':
    "liabilities*" matches "liabilities" and "liabilities.debt", not "liabilities_x".
    """
    if value is None:
        return False
    for p in patterns:
        if p.endswith("*"):
            base = p[:-1].rstrip(".")
            if value == base or value.startswith(base + "."):
                return True
        elif value == p:
            return True
    return False
