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
from app.models.journal_entry import JournalLine, JournalEntry
from app.models.trial_balance import TrialBalanceEntry

logger = logging.getLogger(__name__)


def get_working_trial_balance(db: Session, period_id: int) -> List[Dict[str, Any]]:
    """
    Compute the working trial balance for a period.

    Working TB = TrialBalanceEntry amounts + posted/approved JournalLine adjustments
    grouped by account_id.

    Returns a list of dicts with fields matching WorkingTrialBalanceRow.
    """
    # Load all TB entries for the period
    tb_entries = db.scalars(
        select(TrialBalanceEntry).where(TrialBalanceEntry.period_id == period_id)
    ).all()

    # Build a map: account_id -> TB entry data
    tb_map: Dict[int, Dict[str, Decimal]] = {}
    for entry in tb_entries:
        tb_map[entry.account_id] = {
            "opening_debit": Decimal(str(entry.opening_debit)),
            "opening_credit": Decimal(str(entry.opening_credit)),
            "period_debit": Decimal(str(entry.period_debit)),
            "period_credit": Decimal(str(entry.period_credit)),
            "ytd_debit": Decimal(str(entry.ytd_debit)),
            "ytd_credit": Decimal(str(entry.ytd_credit)),
        }

    # Load posted/approved journal lines that affect this period
    # Join through JournalEntry to filter by period_id and status
    stmt = (
        select(JournalLine)
        .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
        .where(
            and_(
                JournalEntry.period_id == period_id,
                JournalEntry.status.in_(["posted", "approved"]),
            )
        )
    )
    journal_lines = db.scalars(stmt).all()

    # Aggregate journal adjustments by account_id
    adj_map: Dict[int, Dict[str, Decimal]] = {}
    for line in journal_lines:
        if line.account_id not in adj_map:
            adj_map[line.account_id] = {"adj_debit": Decimal("0"), "adj_credit": Decimal("0")}
        adj_map[line.account_id]["adj_debit"] += Decimal(str(line.debit))
        adj_map[line.account_id]["adj_credit"] += Decimal(str(line.credit))

    # Gather all account IDs involved
    all_account_ids = set(tb_map.keys()) | set(adj_map.keys())

    if not all_account_ids:
        return []

    # Load account metadata
    accounts = db.scalars(
        select(Account).where(Account.id.in_(all_account_ids))
    ).all()
    account_map = {a.id: a for a in accounts}

    rows = []
    for acct_id in sorted(all_account_ids):
        account = account_map.get(acct_id)
        tb = tb_map.get(
            acct_id,
            {
                "opening_debit": Decimal("0"),
                "opening_credit": Decimal("0"),
                "period_debit": Decimal("0"),
                "period_credit": Decimal("0"),
                "ytd_debit": Decimal("0"),
                "ytd_credit": Decimal("0"),
            },
        )
        adj = adj_map.get(acct_id, {"adj_debit": Decimal("0"), "adj_credit": Decimal("0")})

        adj_debit = adj["adj_debit"]
        adj_credit = adj["adj_credit"]
        ytd_debit = tb["ytd_debit"]
        ytd_credit = tb["ytd_credit"]

        # Closing = YTD + journal adjustments
        closing_debit = ytd_debit + adj_debit
        closing_credit = ytd_credit + adj_credit

        rows.append(
            {
                "account_id": acct_id,
                "acct_fmtd": account.acct_fmtd if account else str(acct_id),
                "description": account.description if account else None,
                "opening_debit": tb["opening_debit"],
                "opening_credit": tb["opening_credit"],
                "period_debit": tb["period_debit"],
                "period_credit": tb["period_credit"],
                "ytd_debit": ytd_debit,
                "ytd_credit": ytd_credit,
                "adj_debit": adj_debit,
                "adj_credit": adj_credit,
                "closing_debit": closing_debit,
                "closing_credit": closing_credit,
            }
        )

    return rows


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
        raw_rows = svc.pull_trial_balance(connector, fiscal_year, period_number)
    except Exception as exc:
        logger.error("Connector pull failed: %s", exc)
        return 0, 0, [str(exc)]

    imported = 0
    updated = 0
    errors: List[str] = []

    for row in raw_rows:
        try:
            acct_fmtd = str(row.get("acct_fmtd", "")).strip()
            if not acct_fmtd:
                continue

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

            # AMAIS gl-act-prds stores individual period amounts in 'amount'
            # We treat the amount as a period movement.
            # Sign convention: positive = credit for revenue/liability; negative = debit (or vice versa
            # depending on ERP). Store as period_debit or period_credit based on sign.
            amount = Decimal(str(row.get("amount", 0) or 0))
            if amount >= 0:
                period_debit = Decimal("0")
                period_credit = amount
            else:
                period_debit = abs(amount)
                period_credit = Decimal("0")

            existing = db.scalars(
                select(TrialBalanceEntry).where(
                    and_(
                        TrialBalanceEntry.period_id == period_id,
                        TrialBalanceEntry.account_id == account.id,
                    )
                )
            ).first()

            if existing:
                existing.period_debit = period_debit
                existing.period_credit = period_credit
                existing.source = "connector_pull"
                existing.imported_at = datetime.now(timezone.utc)
                existing.connector_id = connector_id
                updated += 1
            else:
                entry = TrialBalanceEntry(
                    period_id=period_id,
                    account_id=account.id,
                    opening_debit=Decimal("0"),
                    opening_credit=Decimal("0"),
                    period_debit=period_debit,
                    period_credit=period_credit,
                    ytd_debit=period_debit,
                    ytd_credit=period_credit,
                    source="connector_pull",
                    imported_at=datetime.now(timezone.utc),
                    connector_id=connector_id,
                )
                db.add(entry)
                imported += 1

        except Exception as exc:
            errors.append(f"Row for '{row.get('acct_fmtd')}': {exc}")

    # Update connector last_pull_at
    connector.last_pull_at = datetime.now(timezone.utc)
    db.commit()

    return imported, updated, errors
