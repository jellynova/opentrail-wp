"""
Period close and fiscal-year roll forward (PLAN §7.3).

Close flow
----------
1. Checks: the period is open, its fiscal year is not locked, every journal entry in the
   period is posted/approved, and the current year's working papers are reviewed and
   signed off (the sign-off check can be overridden by a ``finance_admin`` with ``force``,
   which is recorded in the close record and the audit trail).
2. The closing balance per account — opening + YTD movement + AJEs + RJEs — is written to
   ``PeriodCloseBalance``. This is an immutable snapshot; the trial balance itself is left
   as the ERP reported it (see the note on ``PeriodClose``).
3. The period is flagged closed.

Roll forward
------------
Creates the next fiscal year with its 12 periods, copies the chart of accounts, the
ERP account mappings and the mapping-scheme classifications, and posts prior-year
closing balances as the new year's opening balances (PLAN §1.3). Opening balances are GL
balances: adjusting entries carry forward, reclassifications (presentation only, PLAN
§4.1) do not. Revenue and expense accounts open at zero; the year's net surplus or
deficit is closed to the account classified ``accumulated_surplus`` in the PSAB scheme.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.account import Account, AccountMapping
from app.models.document import WorkingPaper
from app.models.journal_entry import JournalEntry
from app.models.mapping import AccountClassification, MappingScheme
from app.models.period import FiscalYear, Period, PeriodClose, PeriodCloseBalance
from app.models.trial_balance import TrialBalanceEntry
from app.models.user import User
from app.services import audit as audit_svc
from app.services.balances import (
    ZERO, account_balances, classifications, last_period_number, resolve_scheme_id,
)
from app.services.document_manager import latest_versions, sign_off_status

logger = logging.getLogger(__name__)

POSTED_STATUSES = ("posted", "approved")
GL_ENTRY_TYPES = ("adjusting",)
OPERATIONS_CLASSES = {"revenue", "expense"}


class CloseBlocked(Exception):
    """Raised when pre-close checks fail; carries the reasons for the API to return."""

    def __init__(self, reasons: List[str], blocking: Optional[Dict[str, Any]] = None):
        super().__init__("; ".join(reasons))
        self.reasons = reasons
        self.blocking = blocking or {}


def _split(net: Decimal) -> tuple[Decimal, Decimal]:
    """Signed debit-positive amount -> (debit, credit) sides."""
    return (net, ZERO) if net >= 0 else (ZERO, -net)


def unsigned_current_year_documents(db: Session, fy: FiscalYear) -> List[dict]:
    """Latest version of every document in ``/current/<label>`` that is not approved."""
    rows = latest_versions(db, fiscal_year_id=fy.id, folder_prefix=f"/current/{fy.label}")
    outstanding = []
    for row in rows:
        versions = _versions_of(db, row)
        status = sign_off_status(versions, row)
        if status["sign_off_state"] != "approved":
            outstanding.append(
                {
                    "document_id": row.id,
                    "display_name": row.display_name,
                    "folder_path": row.folder_path,
                    "state": status["sign_off_state"],
                }
            )
    return outstanding


def _versions_of(db: Session, row: WorkingPaper) -> List[WorkingPaper]:
    root = row.root_id
    return list(
        db.scalars(
            select(WorkingPaper)
            .where((WorkingPaper.id == root) | (WorkingPaper.parent_version_id == root))
            .order_by(WorkingPaper.version_number, WorkingPaper.id)
        ).all()
    )


def unposted_entries(db: Session, period: Period) -> List[dict]:
    rows = db.scalars(
        select(JournalEntry).where(
            JournalEntry.period_id == period.id, JournalEntry.status.notin_(POSTED_STATUSES)
        )
    ).all()
    return [
        {"id": r.id, "reference": r.reference, "status": r.status, "entry_type": r.entry_type} for r in rows
    ]


def preclose_check(db: Session, period: Period, *, require_sign_offs: bool = True) -> Dict[str, Any]:
    """Return the pre-close findings without changing anything."""
    fy = db.get(FiscalYear, period.fiscal_year_id)
    entries = unposted_entries(db, period)
    unsigned = unsigned_current_year_documents(db, fy) if require_sign_offs else []
    return {
        "period_id": period.id,
        "fiscal_year_id": fy.id,
        "already_closed": period.is_closed,
        "unposted_journal_entries": entries,
        "unsigned_documents": unsigned,
        "ready": not entries and not unsigned and not period.is_closed,
    }


def close_period(
    db: Session,
    period_id: int,
    user: User,
    *,
    notes: Optional[str] = None,
    force: bool = False,
    request: Any = None,
) -> PeriodClose:
    """
    Close a period and snapshot its closing balances.

    ``force`` skips the working-paper sign-off check (never the journal entry check) and
    is only honoured for ``finance_admin``.
    """
    period = db.get(Period, period_id)
    if period is None:
        raise LookupError("Period not found")

    fy = db.get(FiscalYear, period.fiscal_year_id)
    if fy is not None and fy.status == "locked":
        raise CloseBlocked([f"Fiscal year {fy.label} is locked"])
    if period.is_closed:
        raise CloseBlocked([f"Period '{period.name}' is already closed"])

    findings = preclose_check(db, period, require_sign_offs=not force)
    reasons: List[str] = []
    if findings["unposted_journal_entries"]:
        refs = ", ".join(
            e["reference"] or f"#{e['id']}" for e in findings["unposted_journal_entries"][:10]
        )
        reasons.append(f"Journal entries are not posted: {refs}")
    if findings["unsigned_documents"]:
        names = ", ".join(d["display_name"] for d in findings["unsigned_documents"][:10])
        reasons.append(f"Working papers are not signed off: {names}")
    if reasons:
        raise CloseBlocked(reasons, blocking=findings)

    overrides = None
    if force:
        skipped = unsigned_current_year_documents(db, fy)
        if skipped:
            overrides = "sign-off check overridden for: " + ", ".join(d["display_name"] for d in skipped)

    balances = account_balances(db, period.fiscal_year_id, through_period=period.period_number)
    accounts = {
        a.id: a
        for a in db.scalars(
            select(Account).where(Account.id.in_(list(balances.keys()) or [0]))
        ).all()
    }

    posted_entries = db.scalar(
        select(func.count())
        .select_from(JournalEntry)
        .where(JournalEntry.period_id == period.id, JournalEntry.status.in_(POSTED_STATUSES))
    )

    close = db.scalars(select(PeriodClose).where(PeriodClose.period_id == period.id)).first()
    if close is None:
        close = PeriodClose(period_id=period.id)
        db.add(close)
    else:
        # Re-closing after a reopen: the old snapshot is replaced.
        close.balances.clear()
        close.reopened_at = None
        close.reopened_by_user_id = None

    close.closed_by_user_id = user.id
    close.closed_at = datetime.now(timezone.utc)
    close.notes = notes
    close.journal_entry_count = posted_entries or 0
    close.overrides = overrides

    total_debit = ZERO
    total_credit = ZERO
    for account_id, b in sorted(balances.items()):
        account = accounts.get(account_id)
        closing = b.closing()
        debit, credit = _split(closing)
        total_debit += debit
        total_credit += credit
        db.add(
            PeriodCloseBalance(
                period_close=close,
                account_id=account_id,
                acct_fmtd=account.acct_fmtd if account else str(account_id),
                opening=b.opening,
                ytd_debit=b.ytd_debit,
                ytd_credit=b.ytd_credit,
                period_debit=b.period_debit,
                period_credit=b.period_credit,
                aje_debit=b.adj_debit("adjusting"),
                aje_credit=b.adj_credit("adjusting"),
                rje_debit=b.adj_debit("reclassifying"),
                rje_credit=b.adj_credit("reclassifying"),
                closing=closing,
            )
        )

    close.account_count = len(balances)
    close.total_debits = total_debit
    close.total_credits = total_credit
    close.is_balanced = total_debit == total_credit
    db.add(close)

    period.is_closed = True
    db.flush()

    audit_svc.record(
        db,
        user=user,
        action="close",
        resource_type="period",
        resource_id=period.id,
        new={
            "period": period.name,
            "fiscal_year": fy.label if fy else None,
            "accounts": close.account_count,
            "total_debits": str(total_debit),
            "total_credits": str(total_credit),
            "balanced": close.is_balanced,
            "overrides": overrides,
        },
        summary=f"closed period {period.name} {fy.label if fy else ''}".strip(),
        request=request,
        commit=True,
    )
    db.refresh(close)
    return close


def close_fiscal_year(
    db: Session,
    fiscal_year_id: int,
    user: User,
    *,
    force: bool = False,
    request: Any = None,
) -> Dict[str, Any]:
    """
    Close every period in the fiscal year (snapshotting each) and set the year to closed.

    Returns a summary; raises ``CloseBlocked`` if any period fails its checks.
    """
    fy = db.get(FiscalYear, fiscal_year_id)
    if fy is None:
        raise LookupError("Fiscal year not found")
    if fy.status == "locked":
        raise CloseBlocked([f"Fiscal year {fy.label} is already locked"])
    if fy.status == "closed":
        raise CloseBlocked([f"Fiscal year {fy.label} is already closed"])

    periods = db.scalars(
        select(Period).where(Period.fiscal_year_id == fiscal_year_id).order_by(Period.period_number)
    ).all()
    if not periods:
        raise CloseBlocked([f"Fiscal year {fy.label} has no periods"])

    blocked: List[str] = []
    for period in periods:
        if period.is_closed:
            continue
        try:
            close_period(db, period.id, user, force=force, request=request)
        except CloseBlocked as exc:
            blocked.append(f"{period.name}: {'; '.join(exc.reasons)}")

    if blocked:
        raise CloseBlocked(blocked)

    fy.status = "closed"
    audit_svc.record(
        db,
        user=user,
        action="close",
        resource_type="fiscal_year",
        resource_id=fy.id,
        new={"label": fy.label, "periods_closed": len(periods), "forced": force},
        summary=f"closed fiscal year {fy.label}",
        request=request,
        commit=True,
    )
    db.refresh(fy)
    return {"fiscal_year": fy, "periods_closed": len(periods)}


def reopen_period(
    db: Session,
    period_id: int,
    user: User,
    *,
    reason: Optional[str] = None,
    request: Any = None,
) -> Period:
    """
    Reopen a closed period so figures can be corrected. The close snapshot is kept until
    the period is closed again (then it is replaced), and the reopen is audited.
    """
    period = db.get(Period, period_id)
    if period is None:
        raise LookupError("Period not found")

    fy = db.get(FiscalYear, period.fiscal_year_id)
    if fy is not None and fy.status in ("closed", "locked"):
        raise CloseBlocked([f"Fiscal year {fy.label} is {fy.status}; reopen the fiscal year first"])
    if not period.is_closed:
        raise CloseBlocked([f"Period '{period.name}' is not closed"])

    period.is_closed = False
    close = period_close_detail(db, period.id)
    if close is not None:
        close.reopened_at = datetime.now(timezone.utc)
        close.reopened_by_user_id = user.id

    audit_svc.record(
        db,
        user=user,
        action="reopen",
        resource_type="period",
        resource_id=period.id,
        new={"period": period.name, "fiscal_year": fy.label if fy else None, "reason": reason},
        summary=f"reopened period {period.name} {fy.label if fy else ''}".strip(),
        request=request,
        commit=True,
    )
    db.refresh(period)
    return period


def period_close_detail(db: Session, period_id: int) -> Optional[PeriodClose]:
    return db.scalars(select(PeriodClose).where(PeriodClose.period_id == period_id)).first()


def _shift_year(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:  # 29 February
        return value.replace(year=value.year + years, day=28)


def _next_label(fy: FiscalYear) -> str:
    try:
        return str(int(fy.label) + 1)
    except (TypeError, ValueError):
        return str(fy.start_date.year + 1)


def prior_year_closing(db: Session, fy: FiscalYear) -> Dict[int, Decimal]:
    """
    GL closing balance per account (opening + YTD + AJEs, excluding presentation-only
    RJEs) for a fiscal year, from the last period's close snapshot if one exists,
    otherwise computed from the balances engine.
    """
    last_number = last_period_number(db, fy.id)
    final_period = db.scalars(
        select(Period)
        .where(Period.fiscal_year_id == fy.id, Period.period_number == last_number)
        .limit(1)
    ).first()

    if final_period is not None:
        close = period_close_detail(db, final_period.id)
        if close is not None and close.balances:
            return {
                b.account_id: sum(
                    (Decimal(str(v)) for v in (b.opening, b.ytd_debit, b.aje_debit)), ZERO
                ) - sum((Decimal(str(v)) for v in (b.ytd_credit, b.aje_credit)), ZERO)
                for b in close.balances
            }

    return {
        account_id: b.closing(GL_ENTRY_TYPES)
        for account_id, b in account_balances(db, fy.id, last_number).items()
    }


def close_operations(
    db: Session, closing: Dict[int, Decimal]
) -> tuple[Dict[int, Decimal], Decimal, Optional[int], List[str]]:
    """
    Year-end closing entry: zero revenue and expense accounts and move their net into
    accumulated surplus. Returns (opening balances by old account id, net surplus as a
    debit-positive amount, the surplus account id used, warnings).
    """
    classes = classifications(db, resolve_scheme_id(db, "PSAB"), closing.keys())

    def top(account_id: int) -> str:
        return (classes.get(account_id) or "").split(".")[0].lower()

    opening: Dict[int, Decimal] = {}
    net = ZERO
    warnings: List[str] = []
    unclassified = 0
    for account_id, amount in closing.items():
        if top(account_id) in OPERATIONS_CLASSES:
            net += amount
            continue
        if not top(account_id) and amount != ZERO:
            unclassified += 1
        opening[account_id] = amount

    surplus_ids = [a for a, c in classes.items() if c.split(".")[0].lower() == "accumulated_surplus"]
    surplus_id = None
    if net != ZERO:
        if len(surplus_ids) == 1:
            surplus_id = surplus_ids[0]
            opening[surplus_id] = opening.get(surplus_id, ZERO) + net
        else:
            warnings.append(
                "The year's surplus/deficit was not closed to accumulated surplus: "
                + ("no account is" if not surplus_ids else f"{len(surplus_ids)} accounts are")
                + " classified 'accumulated_surplus' in the PSAB scheme (exactly one is required),"
                " so opening balances do not balance."
            )
    if unclassified:
        warnings.append(
            f"{unclassified} account(s) with balances have no PSAB classification and were carried "
            "forward as balance-sheet accounts."
        )
    return opening, net, surplus_id, warnings


def roll_forward(
    db: Session,
    fiscal_year_id: int,
    user: User,
    *,
    label: Optional[str] = None,
    request: Any = None,
) -> Dict[str, Any]:
    """
    Roll a closed fiscal year forward: create the next year, copy the COA, ERP mappings and
    classifications, and post prior-year closing balances as opening balances.
    """
    source = db.get(FiscalYear, fiscal_year_id)
    if source is None:
        raise LookupError("Fiscal year not found")
    if source.status != "closed":
        raise CloseBlocked([f"Fiscal year {source.label} must be closed before it can be rolled forward"])

    new_label = label or _next_label(source)
    new_start = _shift_year(source.start_date, 1)
    new_end = _shift_year(source.end_date, 1)

    existing = db.scalars(
        select(FiscalYear).where(
            (FiscalYear.label == new_label)
            | ((FiscalYear.start_date <= new_end) & (FiscalYear.end_date >= new_start))
        )
    ).first()
    if existing is not None:
        raise CloseBlocked([f"Fiscal year {existing.label} already exists; cannot roll forward"])

    target = FiscalYear(
        label=new_label,
        start_date=new_start,
        end_date=new_end,
        status="open",
        source_fiscal_year_id=source.id,
    )
    db.add(target)
    db.flush()

    source_periods = db.scalars(
        select(Period).where(Period.fiscal_year_id == source.id).order_by(Period.period_number)
    ).all()
    if source_periods:
        period_specs = [
            (p.period_number, p.name, _shift_year(p.start_date, 1), _shift_year(p.end_date, 1))
            for p in source_periods
        ]
    else:
        period_specs = [
            (n, date(new_start.year, n, 1).strftime("%B"),
             date(new_start.year, n, 1),
             date(new_start.year, n + 1, 1).replace(day=1) if n < 12 else new_end)
            for n in range(1, 13)
        ]

    created_periods: Dict[int, Period] = {}
    for number, name, start, end in period_specs:
        period = Period(
            fiscal_year_id=target.id,
            period_number=number,
            name=name,
            start_date=start,
            end_date=end,
            is_closed=False,
        )
        db.add(period)
        created_periods[number] = period
    db.flush()

    # Chart of accounts + ERP mappings
    source_accounts = db.scalars(select(Account).where(Account.fiscal_year_id == source.id)).all()
    account_map: Dict[int, Account] = {}
    for account in source_accounts:
        clone = Account(
            fiscal_year_id=target.id,
            acct_fmtd=account.acct_fmtd,
            description=account.description,
            acct_type=account.acct_type,
            record_class=account.record_class,
            capital_acct=account.capital_acct,
            dept_code=account.dept_code,
            fund_code=account.fund_code,
            stat=account.stat,
            total_lvl=account.total_lvl,
            total_lvl_cde=account.total_lvl_cde,
            rev_exp_rpt=account.rev_exp_rpt,
            object_str=account.object_str,
            project_str=account.project_str,
            normal_balance=account.normal_balance,
            is_active=account.is_active,
            source_system=account.source_system,
            connector_id=account.connector_id,
        )
        for n in range(1, 11):
            setattr(clone, f"seg{n}", getattr(account, f"seg{n}"))
            setattr(clone, f"seg{n}_descr", getattr(account, f"seg{n}_descr"))
        db.add(clone)
        account_map[account.id] = clone
    db.flush()

    mappings_copied = 0
    if account_map:
        for mapping in db.scalars(
            select(AccountMapping).where(AccountMapping.account_id.in_(list(account_map.keys())))
        ).all():
            db.add(
                AccountMapping(
                    account_id=account_map[mapping.account_id].id,
                    source_system=mapping.source_system,
                    source_acct_fmtd=mapping.source_acct_fmtd,
                )
            )
            mappings_copied += 1

    # Mapping-scheme classifications (PLAN §1.3: mappings carry into the new year)
    classifications_copied = 0
    if account_map:
        scheme_ids = [s.id for s in db.scalars(select(MappingScheme)).all()]
        for classification in db.scalars(
            select(AccountClassification).where(
                AccountClassification.account_id.in_(list(account_map.keys())),
                AccountClassification.scheme_id.in_(scheme_ids or [0]),
            )
        ).all():
            db.add(
                AccountClassification(
                    account_id=account_map[classification.account_id].id,
                    scheme_id=classification.scheme_id,
                    classification_value=classification.classification_value,
                    sort_order=classification.sort_order,
                )
            )
            classifications_copied += 1

    # Opening balances = prior-year closing balances
    opening_period = created_periods.get(min(created_periods) if created_periods else 1)
    closing, net_surplus, surplus_id, warnings = close_operations(db, prior_year_closing(db, source))
    opening_entries = 0
    total_debit = ZERO
    total_credit = ZERO
    if opening_period is not None:
        for old_account_id, amount in closing.items():
            clone = account_map.get(old_account_id)
            if clone is None or amount == ZERO:
                continue
            debit, credit = _split(Decimal(str(amount)))
            total_debit += debit
            total_credit += credit
            db.add(
                TrialBalanceEntry(
                    period_id=opening_period.id,
                    account_id=clone.id,
                    opening_debit=debit,
                    opening_credit=credit,
                    period_debit=ZERO,
                    period_credit=ZERO,
                    ytd_debit=ZERO,
                    ytd_credit=ZERO,
                    source="roll_forward",
                    imported_at=datetime.now(timezone.utc),
                )
            )
            opening_entries += 1

    db.flush()

    summary = {
        "fiscal_year_id": target.id,
        "label": target.label,
        "start_date": target.start_date,
        "end_date": target.end_date,
        "periods_created": len(created_periods),
        "accounts_copied": len(account_map),
        "account_mappings_copied": mappings_copied,
        "classifications_copied": classifications_copied,
        "opening_balances_posted": opening_entries,
        "opening_debits": str(total_debit),
        "opening_credits": str(total_credit),
        "balanced": total_debit == total_credit,
        "net_surplus": str(-net_surplus),  # credit-positive: a surplus is > 0
        "surplus_account": account_map[surplus_id].acct_fmtd if surplus_id in account_map else None,
        "warnings": warnings,
    }

    audit_svc.record(
        db,
        user=user,
        action="roll_forward",
        resource_type="fiscal_year",
        resource_id=target.id,
        old={"source_fiscal_year_id": source.id, "label": source.label},
        new=summary,
        summary=f"rolled fiscal year {source.label} forward to {target.label}",
        request=request,
        commit=True,
    )
    db.refresh(target)
    summary["fiscal_year"] = target
    return summary


def reopen_fiscal_year(
    db: Session,
    fiscal_year_id: int,
    user: User,
    *,
    reason: str,
    force: bool = False,
    request: Any = None,
) -> Dict[str, Any]:
    """
    Reopen a closed fiscal year (finance_admin only, audited).

    Only the year's status flips back to open — its periods are left exactly as
    they are, so the response reports which of them are still closed and the UI
    can offer to reopen them individually. A *locked* year additionally requires
    ``force``, and the override is recorded in the audit trail.
    """
    fy = db.get(FiscalYear, fiscal_year_id)
    if fy is None:
        raise LookupError("Fiscal year not found")
    if fy.status == "open":
        raise CloseBlocked([f"Fiscal year {fy.label} is already open"])
    if fy.status == "locked" and not force:
        raise CloseBlocked([f"Fiscal year {fy.label} is locked; force is required to reopen it"])

    old_status = fy.status
    fy.status = "open"
    db.flush()

    closed_periods = db.scalars(
        select(Period)
        .where(Period.fiscal_year_id == fiscal_year_id, Period.is_closed.is_(True))
        .order_by(Period.period_number)
    ).all()

    audit_svc.record(
        db,
        user=user,
        action="reopen",
        resource_type="fiscal_year",
        resource_id=fy.id,
        old={"status": old_status},
        new={"status": fy.status, "reason": reason, "forced": force},
        summary=(
            f"reopened fiscal year {fy.label}"
            + (" (locked year, forced)" if old_status == "locked" else "")
        ),
        request=request,
        commit=True,
    )
    db.refresh(fy)
    return {"fiscal_year": fy, "prior_status": old_status, "forced": force, "closed_periods": closed_periods}
