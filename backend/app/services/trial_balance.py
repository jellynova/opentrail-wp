"""
Trial balance service: aggregation, CSV import, and connector-based import.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.connector import ExternalConnector
from app.models.trial_balance import TrialBalanceEntry

logger = logging.getLogger(__name__)


def get_working_trial_balance(db: Session, period_id: int) -> List[Dict[str, Any]]:
    """Working trial balance for a period. See app.services.working_papers."""
    from app.services.working_papers import working_trial_balance

    return working_trial_balance(db, period_id)


def import_from_csv(
    db: Session,
    period_id: int,
    file_content: bytes,
    column_mapping: Dict[str, str],
    fiscal_year_id: int,
) -> Tuple[int, int, List[str]]:
    """
    Parse a CSV file and upsert TrialBalanceEntry records for the given period.

    column_mapping maps CSV header names to internal field names:
      e.g. {"Account No": "acct_fmtd", "Debit": "period_debit", "Credit": "period_credit"}

    Returns (records_imported, records_updated, errors).
    """
    text = file_content.decode("utf-8-sig")  # handle BOM
    reader = csv.DictReader(io.StringIO(text))
    imported = 0
    updated = 0
    errors: List[str] = []

    for row_num, row in enumerate(reader, start=2):
        try:
            # Apply column mapping
            mapped: Dict[str, Any] = {}
            for csv_col, internal_col in column_mapping.items():
                if csv_col in row:
                    mapped[internal_col] = row[csv_col]

            acct_fmtd = str(mapped.get("acct_fmtd", "")).strip()
            if not acct_fmtd:
                errors.append(f"Row {row_num}: missing account identifier")
                continue

            # Look up account
            account = db.scalars(
                select(Account).where(
                    and_(
                        Account.acct_fmtd == acct_fmtd,
                        Account.fiscal_year_id == fiscal_year_id,
                    )
                )
            ).first()

            if account is None:
                errors.append(f"Row {row_num}: account '{acct_fmtd}' not found in fiscal year {fiscal_year_id}")
                continue

            def _decimal(val: Any, default: Decimal = Decimal("0")) -> Decimal:
                try:
                    s = str(val).replace(",", "").strip()
                    return Decimal(s) if s else default
                except Exception:
                    return default

            # Check for existing entry
            existing = db.scalars(
                select(TrialBalanceEntry).where(
                    and_(
                        TrialBalanceEntry.period_id == period_id,
                        TrialBalanceEntry.account_id == account.id,
                    )
                )
            ).first()

            if existing:
                existing.opening_debit = _decimal(mapped.get("opening_debit"), Decimal(str(existing.opening_debit)))
                existing.opening_credit = _decimal(mapped.get("opening_credit"), Decimal(str(existing.opening_credit)))
                existing.period_debit = _decimal(mapped.get("period_debit"), Decimal(str(existing.period_debit)))
                existing.period_credit = _decimal(mapped.get("period_credit"), Decimal(str(existing.period_credit)))
                existing.ytd_debit = _decimal(mapped.get("ytd_debit"), Decimal(str(existing.ytd_debit)))
                existing.ytd_credit = _decimal(mapped.get("ytd_credit"), Decimal(str(existing.ytd_credit)))
                existing.source = "csv_import"
                existing.imported_at = datetime.now(timezone.utc)
                updated += 1
            else:
                entry = TrialBalanceEntry(
                    period_id=period_id,
                    account_id=account.id,
                    opening_debit=_decimal(mapped.get("opening_debit")),
                    opening_credit=_decimal(mapped.get("opening_credit")),
                    period_debit=_decimal(mapped.get("period_debit")),
                    period_credit=_decimal(mapped.get("period_credit")),
                    ytd_debit=_decimal(mapped.get("ytd_debit")),
                    ytd_credit=_decimal(mapped.get("ytd_credit")),
                    source="csv_import",
                    imported_at=datetime.now(timezone.utc),
                )
                db.add(entry)
                imported += 1

        except Exception as exc:
            errors.append(f"Row {row_num}: {exc}")
            logger.warning("CSV import error row %d: %s", row_num, exc)

    db.commit()
    return imported, updated, errors


def import_from_connector(
    db: Session,
    connector_id: int,
    fiscal_year_id: int,
    period_id: int,
    fiscal_year: int,
    period_number: int,
) -> Tuple[int, int, List[str]]:
    """
    Pull trial balance data from the external connector and upsert entries.

    fiscal_year: the ERP fiscal year integer (e.g. 2024)
    period_number: the ERP period number (1-12)

    Returns (records_imported, records_updated, errors).
    """
    from app.services import sql_connector as svc

    connector = db.get(ExternalConnector, connector_id)
    if connector is None:
        return 0, 0, [f"Connector {connector_id} not found"]

    try:
        # Pull the whole year so YTD can be computed from periods 1..N.
        raw_rows = svc.pull_trial_balance(connector, fiscal_year, None)
    except Exception as exc:
        logger.error("Connector pull failed: %s", exc)
        return 0, 0, [str(exc)]

    imported = 0
    updated = 0
    errors: List[str] = []

    # Aggregate per account: opening (period 0, if the ERP stores one), this period's
    # movement, and YTD movement for periods 1..N. Multiple rows per account/period sum.
    totals: Dict[str, Dict[str, Decimal]] = {}
    for row in raw_rows:
        acct_fmtd = str(row.get("acct_fmtd", "") or "").strip()
        if not acct_fmtd:
            continue
        try:
            prd = int(row.get("fisc_prd"))
            amount = Decimal(str(row.get("amount", 0) or 0))
        except Exception as exc:
            errors.append(f"Row for '{acct_fmtd}': {exc}")
            continue
        t = totals.setdefault(acct_fmtd, {"opening": Decimal("0"), "period": Decimal("0"), "ytd": Decimal("0")})
        if prd == 0:
            t["opening"] += amount
        elif prd <= period_number:
            t["ytd"] += amount
            if prd == period_number:
                t["period"] += amount

    def _sides(amount: Decimal) -> Tuple[Decimal, Decimal]:
        # Sign convention (existing behaviour, unverified against AMAIS): positive
        # amounts are credits, negative amounts are debits. Returns (debit, credit).
        return (Decimal("0"), amount) if amount >= 0 else (abs(amount), Decimal("0"))

    for acct_fmtd, t in totals.items():
        account = db.scalars(
            select(Account).where(
                and_(
                    Account.acct_fmtd == acct_fmtd,
                    Account.fiscal_year_id == fiscal_year_id,
                )
            )
        ).first()
        if account is None:
            errors.append(f"Account '{acct_fmtd}' not found; skipped")
            continue

        opening_debit, opening_credit = _sides(t["opening"])
        period_debit, period_credit = _sides(t["period"])
        ytd_debit, ytd_credit = _sides(t["ytd"])
        values = dict(
            opening_debit=opening_debit,
            opening_credit=opening_credit,
            period_debit=period_debit,
            period_credit=period_credit,
            ytd_debit=ytd_debit,
            ytd_credit=ytd_credit,
            source="connector_pull",
            imported_at=datetime.now(timezone.utc),
            connector_id=connector_id,
        )

        existing = db.scalars(
            select(TrialBalanceEntry).where(
                and_(
                    TrialBalanceEntry.period_id == period_id,
                    TrialBalanceEntry.account_id == account.id,
                )
            )
        ).first()
        if existing:
            for k, v in values.items():
                setattr(existing, k, v)
            updated += 1
        else:
            db.add(TrialBalanceEntry(period_id=period_id, account_id=account.id, **values))
            imported += 1

    # Update connector last_pull_at
    connector.last_pull_at = datetime.now(timezone.utc)
    db.commit()

    return imported, updated, errors
