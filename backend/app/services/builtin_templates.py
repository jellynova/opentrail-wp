"""
Built-in legislated report templates (PLAN §5.2), expressed as report-builder definitions.

Templates are seeded at startup as protected Reports (is_template=True, is_protected=True)
keyed by definition["template_key"]. Users clone a template to customise it; a clone keeps
"source_template_key" so it can be reverted to the standard layout.

All templates read the "PSAB" mapping scheme using the hierarchical classification
values in PSAB_TAXONOMY (e.g. "liabilities.debt"). Accounts classified with only the
top-level value (e.g. "liabilities") fall into the "Other ..." line of their group.

Bump TEMPLATE_VERSION when changing a definition so existing installations are updated.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

TEMPLATE_VERSION = 1

# value -> label. Top-level values match PLAN §2.1 (PS 1201 groupings).
PSAB_TAXONOMY: Dict[str, str] = {
    "financial_assets.cash": "Cash and cash equivalents",
    "financial_assets.investments": "Portfolio investments",
    "financial_assets.taxes_receivable": "Property taxes receivable",
    "financial_assets.receivables": "Accounts receivable",
    "financial_assets.other": "Other financial assets",
    "liabilities.payables": "Accounts payable and accrued liabilities",
    "liabilities.deferred_revenue": "Deferred revenue",
    "liabilities.development_cost_charges": "Development cost charges",
    "liabilities.deposits": "Deposits and holdbacks",
    "liabilities.employee_benefits": "Employee future benefits",
    "liabilities.asset_retirement": "Asset retirement obligations",
    "liabilities.debt": "Long-term debt",
    "liabilities.other": "Other liabilities",
    "non_financial_assets.tca_cost": "Tangible capital assets — cost",
    "non_financial_assets.tca_amortization": "Tangible capital assets — accumulated amortization",
    "non_financial_assets.prepaids": "Prepaid expenses",
    "non_financial_assets.inventory": "Inventories of supplies",
    "revenue.taxation": "Taxation, net",
    "revenue.grants_in_lieu": "Grants in lieu of taxes",
    "revenue.sale_of_services": "Sale of services and user fees",
    "revenue.licences_permits": "Licences, permits and fines",
    "revenue.government_transfers": "Government transfers — operating",
    "revenue.capital_transfers": "Government transfers — capital",
    "revenue.dcc_recognized": "Development cost charges recognized",
    "revenue.investment_income": "Investment income",
    "revenue.gain_on_disposal": "Gain (loss) on disposal of tangible capital assets",
    "revenue.other": "Other revenue",
    "expense.general_government": "General government",
    "expense.protective_services": "Protective services",
    "expense.transportation": "Transportation services",
    "expense.environmental_health": "Environmental health (solid waste)",
    "expense.public_health": "Public health",
    "expense.development_services": "Planning and development services",
    "expense.recreation_culture": "Recreation and cultural services",
    "expense.water": "Water utility",
    "expense.sewer": "Sewer utility",
    "expense.other": "Other expenses",
    "accumulated_surplus.operating": "Accumulated surplus — operating funds",
    "accumulated_surplus.reserves": "Accumulated surplus — statutory reserves",
    "accumulated_surplus.capital": "Accumulated surplus — equity in tangible capital assets",
}

CREDIT = -1  # sign for credit-natured lines (presented as positive amounts)

NUMBER_FORMAT = {"decimals": 0, "currency_symbol": "$"}

COLS_CY_PY = [
    {"key": "cy", "label": "{fiscal_year}", "source": "actual"},
    {"key": "py", "label": "{prior_fiscal_year}", "source": "actual", "year_offset": -1},
]

COLS_BUD_CY_PY = [
    {"key": "bud", "label": "{fiscal_year} Budget", "source": "budget", "budget_version": "original"},
    *COLS_CY_PY,
]


def _acct(label: str, values: List[str], sign: int = 1, measure: str = "closing",
          id: Optional[str] = None, **extra) -> Dict[str, Any]:
    row = {"type": "accounts", "label": label, "classifications": values, "sign": sign, "measure": measure, **extra}
    if id:
        row["id"] = id
    return row


def _line(value: str, sign: int = 1, **extra) -> Dict[str, Any]:
    """Accounts row labelled from the taxonomy; '.other' lines also catch the bare top-level value."""
    values = [value]
    if value.endswith(".other"):
        values.append(value.split(".")[0])
    return _acct(PSAB_TAXONOMY[value], values, sign, **extra)


def _formula(id: str, label: str, formula: str, double: bool = False, **extra) -> Dict[str, Any]:
    style = {"bold": True, "underline": "double" if double else "single"}
    return {"id": id, "type": "formula", "label": label, "formula": formula, "style": style, **extra}


def _section(id: str, label: str, children: List[Dict[str, Any]], total_label: Optional[str] = None,
             **extra) -> Dict[str, Any]:
    row = {"id": id, "type": "section", "label": label, "children": children, **extra}
    if total_label:
        row["total_label"] = total_label
    return row


def _text(label: str) -> Dict[str, Any]:
    return {"type": "text", "label": label}


REVENUE_LINES = [
    "revenue.taxation", "revenue.grants_in_lieu", "revenue.sale_of_services", "revenue.licences_permits",
    "revenue.government_transfers", "revenue.capital_transfers", "revenue.dcc_recognized",
    "revenue.investment_income", "revenue.gain_on_disposal", "revenue.other",
]
EXPENSE_LINES = [
    "expense.general_government", "expense.protective_services", "expense.transportation",
    "expense.environmental_health", "expense.public_health", "expense.development_services",
    "expense.recreation_culture", "expense.water", "expense.sewer", "expense.other",
]
# Hidden building blocks for statements that start from the annual surplus.
SURPLUS_ROWS = [
    _acct("Revenue", ["revenue*"], CREDIT, id="h_rev", hidden=True),
    _acct("Expenses", ["expense*"], id="h_exp", hidden=True),
    _formula("surplus", "Annual surplus", "h_rev - h_exp", style={"bold": True}),
]


def _sfp(title: str, report_type: str) -> Dict[str, Any]:
    return {
        "version": 2,
        "title": title,
        "subtitle": "As at {period_end}",
        "report_type": report_type,
        "scheme": "PSAB",
        "number_format": NUMBER_FORMAT,
        "columns": COLS_CY_PY,
        "rows": [
            _section("fa", "Financial assets", [
                _line("financial_assets.cash"),
                _line("financial_assets.investments"),
                _line("financial_assets.taxes_receivable"),
                _line("financial_assets.receivables"),
                _line("financial_assets.other"),
            ], "Total financial assets"),
            _section("li", "Liabilities", [
                _line("liabilities.payables", CREDIT),
                _line("liabilities.deferred_revenue", CREDIT),
                _line("liabilities.development_cost_charges", CREDIT),
                _line("liabilities.deposits", CREDIT),
                _line("liabilities.employee_benefits", CREDIT),
                _line("liabilities.asset_retirement", CREDIT),
                _line("liabilities.debt", CREDIT),
                _line("liabilities.other", CREDIT),
            ], "Total liabilities"),
            _formula("nfa", "Net financial assets (debt)", "fa - li"),
            _section("nf", "Non-financial assets", [
                _acct("Tangible capital assets", ["non_financial_assets.tca_cost",
                                                  "non_financial_assets.tca_amortization"]),
                _line("non_financial_assets.prepaids"),
                _line("non_financial_assets.inventory"),
                _acct("Other non-financial assets", ["non_financial_assets"]),
            ], "Total non-financial assets"),
            _formula("as", "Accumulated surplus", "nfa + nf", double=True),
        ],
    }


def _so(title: str, report_type: str) -> Dict[str, Any]:
    return {
        "version": 2,
        "title": title,
        "subtitle": "For the year ended {period_end}",
        "report_type": report_type,
        "scheme": "PSAB",
        "number_format": NUMBER_FORMAT,
        "columns": COLS_BUD_CY_PY,
        "rows": [
            _section("rev", "Revenue", [_line(v, CREDIT) for v in REVENUE_LINES], "Total revenue"),
            _section("exp", "Expenses", [_line(v) for v in EXPENSE_LINES], "Total expenses"),
            _formula("surplus", "Annual surplus (deficit)", "rev - exp"),
            # Opening accumulated surplus = opening net assets (financial assets − liabilities
            # + non-financial assets); the budget column shows the same actual figure.
            _acct("Accumulated surplus, beginning of year",
                  ["financial_assets*", "liabilities*", "non_financial_assets*"],
                  measure="opening", id="as_open", copy_columns={"bud": "cy"}, always_show=True),
            _formula("as_close", "Accumulated surplus, end of year", "as_open + surplus", double=True),
        ],
    }


def _scnfa(title: str, report_type: str) -> Dict[str, Any]:
    return {
        "version": 2,
        "title": title,
        "subtitle": "For the year ended {period_end}",
        "report_type": report_type,
        "scheme": "PSAB",
        "number_format": NUMBER_FORMAT,
        "columns": COLS_BUD_CY_PY,
        "rows": [
            *SURPLUS_ROWS,
            _section("tca", "", [
                _acct("Acquisition of tangible capital assets", ["non_financial_assets.tca_cost"], -1, "movement"),
                _acct("Amortization of tangible capital assets", ["non_financial_assets.tca_amortization"], -1,
                      "movement"),
            ], hide_header=True),
            _section("other_nfa", "", [
                _acct("Change in prepaid expenses", ["non_financial_assets.prepaids"], -1, "movement"),
                _acct("Change in inventories of supplies", ["non_financial_assets.inventory"], -1, "movement"),
            ], hide_header=True),
            _formula("change", "Change in net financial assets (debt)", "surplus + tca + other_nfa"),
            _acct("Net financial assets (debt), beginning of year", ["financial_assets*", "liabilities*"],
                  measure="opening", id="nfa_open", copy_columns={"bud": "cy"}, always_show=True),
            _formula("nfa_close", "Net financial assets (debt), end of year", "nfa_open + change", double=True),
            _acct("Net financial assets per SFP", ["financial_assets*", "liabilities*"], id="nfa_sfp",
                  hidden=True),
        ],
        "checks": [{"label": "Closing net financial assets agree to Statement of Financial Position",
                    "formula": "nfa_close - nfa_sfp"}],
    }


def _scf(title: str, report_type: str) -> Dict[str, Any]:
    working_capital = [
        ("Property taxes receivable", ["financial_assets.taxes_receivable"]),
        ("Accounts receivable", ["financial_assets.receivables", "financial_assets.other", "financial_assets"]),
        ("Accounts payable and accrued liabilities", ["liabilities.payables"]),
        ("Deferred revenue", ["liabilities.deferred_revenue"]),
        ("Development cost charges", ["liabilities.development_cost_charges"]),
        ("Deposits and holdbacks", ["liabilities.deposits"]),
        ("Employee future benefits", ["liabilities.employee_benefits"]),
        ("Asset retirement obligations", ["liabilities.asset_retirement"]),
        ("Other liabilities", ["liabilities.other", "liabilities"]),
        ("Prepaid expenses", ["non_financial_assets.prepaids"]),
        ("Inventories of supplies", ["non_financial_assets.inventory"]),
        ("Other non-financial assets", ["non_financial_assets"]),
    ]
    return {
        "version": 2,
        "title": title,
        "subtitle": "For the year ended {period_end}",
        "report_type": report_type,
        "scheme": "PSAB",
        "number_format": NUMBER_FORMAT,
        "columns": COLS_CY_PY,
        "rows": [
            _section("op", "Operating transactions", [
                _acct("Revenue", ["revenue*"], CREDIT, id="h_rev", hidden=True, include_in_total=False),
                _acct("Expenses", ["expense*"], id="h_exp", hidden=True, include_in_total=False),
                _formula("surplus", "Annual surplus", "h_rev - h_exp", style={"bold": True},
                         include_in_total=True),
                _text("Items not involving cash:"),
                _acct("Amortization of tangible capital assets", ["non_financial_assets.tca_amortization"], -1,
                      "movement"),
                _text("Changes in non-cash operating items:"),
                *[_acct(label, values, -1, "movement") for label, values in working_capital],
            ], "Cash provided by operating transactions"),
            _section("cap", "Capital transactions", [
                _acct("Acquisition of tangible capital assets", ["non_financial_assets.tca_cost"], -1, "movement"),
            ], "Cash applied to capital transactions"),
            _section("inv", "Investing transactions", [
                _acct("Change in portfolio investments", ["financial_assets.investments"], -1, "movement"),
            ], "Cash provided by (applied to) investing transactions"),
            _section("fin", "Financing transactions", [
                _acct("Net change in long-term debt", ["liabilities.debt"], -1, "movement"),
            ], "Cash provided by (applied to) financing transactions"),
            _formula("change", "Change in cash and cash equivalents", "op + cap + inv + fin"),
            _acct("Cash and cash equivalents, beginning of year", ["financial_assets.cash"], measure="opening",
                  id="cash_open", always_show=True),
            _formula("cash_close", "Cash and cash equivalents, end of year", "cash_open + change", double=True),
            _acct("Cash per SFP", ["financial_assets.cash"], id="cash_sfp", hidden=True),
        ],
        "checks": [{"label": "Closing cash agrees to Statement of Financial Position",
                    "formula": "cash_close - cash_sfp"}],
    }


def _notes() -> Dict[str, Any]:
    return {
        "version": 2,
        "title": "Notes to the Financial Statements",
        "subtitle": "For the year ended {period_end}",
        "report_type": "psab_notes",
        "scheme": "PSAB",
        "number_format": NUMBER_FORMAT,
        "columns": COLS_CY_PY,
        "rows": [
            _section("n1", "1. Significant accounting policies", [
                _text("The financial statements of {organization} are prepared by management in accordance "
                      "with Canadian public sector accounting standards (PSAS)."),
                _text("Edit this note block to describe the basis of accounting, reporting entity, revenue "
                      "recognition, tangible capital assets and use of estimates."),
            ]),
            _section("n2", "2. Cash and cash equivalents", [
                _line("financial_assets.cash", show_detail=True, total_label="Total cash and cash equivalents"),
            ]),
            _section("n3", "3. Long-term debt", [
                _line("liabilities.debt", CREDIT, show_detail=True, total_label="Total long-term debt"),
            ]),
            _section("n4", "4. Tangible capital assets", [
                _line("non_financial_assets.tca_cost", always_show=True),
                _line("non_financial_assets.tca_amortization", always_show=True),
            ], "Net book value"),
            _section("n5", "5. Accumulated surplus", [
                _acct("Accumulated surplus", ["accumulated_surplus*"], CREDIT, show_detail=True,
                      total_label="Accumulated surplus per ledger (before current-year surplus)"),
            ]),
        ],
    }


LGDE_NOTE = ("LGDE format starting point: align line items to the current Local Government Data Entry "
             "form before submission.")


def _with(definition: Dict[str, Any], key: str) -> Dict[str, Any]:
    return {**definition, "template_key": key, "template_version": TEMPLATE_VERSION}


# key -> (name, report_type, description, definition)
TEMPLATES: Dict[str, Dict[str, Any]] = {
    "psab_sfp": {
        "name": "PSAB — Statement of Financial Position",
        "description": "PS 1201.031–.033. Net financial assets (debt) and accumulated surplus, with prior year.",
        "definition": _sfp("Statement of Financial Position", "psab_sfp"),
    },
    "psab_so": {
        "name": "PSAB — Statement of Operations",
        "description": "PS 1201. Revenue and expenses by function with budget, current and prior year columns.",
        "definition": _so("Statement of Operations", "psab_so"),
    },
    "psab_scnfa": {
        "name": "PSAB — Statement of Change in Net Financial Assets (Debt)",
        "description": "PS 1201. Reconciles annual surplus to the change in net financial assets.",
        "definition": _scnfa("Statement of Change in Net Financial Assets (Debt)", "psab_scnfa"),
    },
    "psab_scf": {
        "name": "PSAB — Statement of Cash Flows",
        "description": "PS 2450, indirect method: operating, capital, investing and financing transactions.",
        "definition": _scf("Statement of Cash Flows", "psab_scf"),
    },
    "psab_notes": {
        "name": "PSAB — Notes to the Financial Statements (starter)",
        "description": "Modular note blocks with account detail and dynamic values; extend as required.",
        "definition": _notes(),
    },
    "lgde_sfp": {
        "name": "LGDE — Statement of Financial Position",
        "description": LGDE_NOTE,
        "definition": _sfp("Statement of Financial Position (LGDE)", "lgde_sfp"),
    },
    "lgde_so": {
        "name": "LGDE — Statement of Operations",
        "description": LGDE_NOTE,
        "definition": _so("Statement of Operations (LGDE)", "lgde_so"),
    },
    "lgde_scnfa": {
        "name": "LGDE — Statement of Change in Net Financial Assets (Debt)",
        "description": LGDE_NOTE,
        "definition": _scnfa("Statement of Change in Net Financial Assets (Debt) (LGDE)", "lgde_scnfa"),
    },
    "lgde_scf": {
        "name": "LGDE — Statement of Cash Flows",
        "description": LGDE_NOTE,
        "definition": _scf("Statement of Cash Flows (LGDE)", "lgde_scf"),
    },
}

for _key, _tpl in TEMPLATES.items():
    _tpl["definition"] = _with(_tpl["definition"], _key)
    _tpl["report_type"] = _tpl["definition"]["report_type"]


def seed_templates(db, created_by_user_id: int) -> None:
    """Create or upgrade built-in templates and the PSAB mapping scheme. Idempotent."""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.models.mapping import MappingScheme
    from app.models.report import Report

    if not any(s.name.lower() == "psab" for s in db.scalars(select(MappingScheme)).all()):
        db.add(MappingScheme(name="PSAB", description="PSAB / PS 1201 financial statement classification",
                             is_active=True))

    existing = {
        (r.definition or {}).get("template_key"): r
        for r in db.scalars(select(Report).where(Report.is_template.is_(True), Report.is_protected.is_(True))).all()
    }
    now = datetime.now(timezone.utc)
    for key, tpl in TEMPLATES.items():
        report = existing.get(key)
        if report is None:
            db.add(Report(
                name=tpl["name"], description=tpl["description"], report_type=tpl["report_type"],
                is_template=True, is_protected=True, definition=tpl["definition"],
                created_by_user_id=created_by_user_id, created_at=now, updated_at=now,
            ))
        elif (report.definition or {}).get("template_version", 0) < TEMPLATE_VERSION:
            report.name, report.description = tpl["name"], tpl["description"]
            report.report_type, report.definition, report.updated_at = tpl["report_type"], tpl["definition"], now
    db.commit()
