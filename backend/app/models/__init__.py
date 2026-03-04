# Import all models here so Alembic can discover them via Base.metadata
from app.core.database import Base  # noqa: F401

from app.models.user import User  # noqa: F401
from app.models.period import FiscalYear, Period  # noqa: F401
from app.models.connector import ExternalConnector, AuditLog  # noqa: F401
from app.models.account import Account, AccountMapping  # noqa: F401
from app.models.segment import SegmentDefinition  # noqa: F401
from app.models.mapping import MappingScheme, AccountClassification  # noqa: F401
from app.models.trial_balance import TrialBalanceEntry  # noqa: F401
from app.models.journal_entry import JournalEntry, JournalLine  # noqa: F401
from app.models.document import WorkingPaper, WPAnnotation  # noqa: F401
from app.models.budget import BudgetYear, BudgetRequest, BudgetLine  # noqa: F401
from app.models.report import Report  # noqa: F401

__all__ = [
    "Base",
    "User",
    "FiscalYear",
    "Period",
    "ExternalConnector",
    "AuditLog",
    "Account",
    "AccountMapping",
    "SegmentDefinition",
    "MappingScheme",
    "AccountClassification",
    "TrialBalanceEntry",
    "JournalEntry",
    "JournalLine",
    "WorkingPaper",
    "WPAnnotation",
    "BudgetYear",
    "BudgetRequest",
    "BudgetLine",
    "Report",
]
