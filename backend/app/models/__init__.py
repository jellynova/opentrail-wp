# Import all models here so Alembic can discover them via Base.metadata
from app.core.database import Base  # noqa: F401

from app.models.user import User  # noqa: F401
from app.models.period import (  # noqa: F401
    FiscalYear,
    Period,
    PeriodClose,
    PeriodCloseBalance,
)
from app.models.connector import ExternalConnector, AuditLog  # noqa: F401
from app.models.account import Account, AccountMapping  # noqa: F401
from app.models.segment import SegmentDefinition  # noqa: F401
from app.models.mapping import MappingScheme, AccountClassification  # noqa: F401
from app.models.trial_balance import TrialBalanceEntry  # noqa: F401
from app.models.journal_entry import JournalEntry, JournalLine  # noqa: F401
from app.models.document import WorkingPaper, WPAnnotation  # noqa: F401
from app.models.document_links import DocumentAccountLink  # noqa: F401
from app.models.budget import (  # noqa: F401
    BudgetYear, BudgetRequest, BudgetLine, BudgetAmendment, BudgetAmendmentLine,
)
from app.models.report import Report  # noqa: F401
from app.models.sofi import SofiEntry  # noqa: F401
from app.models.tca import TcaScheduleLine  # noqa: F401

__all__ = [
    "Base",
    "User",
    "FiscalYear",
    "Period",
    "PeriodClose",
    "PeriodCloseBalance",
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
    "DocumentAccountLink",
    "BudgetYear",
    "BudgetRequest",
    "BudgetLine",
    "BudgetAmendment",
    "BudgetAmendmentLine",
    "Report",
    "SofiEntry",
    "TcaScheduleLine",
]
