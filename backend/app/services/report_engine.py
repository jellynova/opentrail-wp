"""
Report builder engine (PLAN §5.1).

A report is a JSON definition: a tree of rows rendered against one or more columns.

Definition (version 2)
----------------------
{
  "version": 2,
  "title": "Statement of Financial Position",
  "subtitle": "As at {period_end}",
  "report_type": "psab_sfp",
  "scheme": "PSAB",                         # mapping scheme name or id (default PSAB)
  "number_format": {"decimals": 0, "currency_symbol": "$"},
  "columns": [
    {"key": "cy",  "label": "{fiscal_year}",       "source": "actual"},
    {"key": "py",  "label": "{prior_fiscal_year}", "source": "actual", "year_offset": -1},
    {"key": "bud", "label": "Budget",              "source": "budget", "budget_version": "original"},
    {"key": "var", "label": "Variance",            "source": "formula", "formula": "cy - bud"}
  ],
  "rows": [ ...row objects... ]
}

Row types
---------
section / group  {label, children: [...], total_label?, hide_header?}
                 value = sum of children (account, group and manual rows; formula rows only
                 when "include_in_total": true). A total row is emitted when total_label is set.
accounts         {label, classifications: ["revenue.taxation", "liabilities*"],
                  accounts: ["4-1*"], sign: 1|-1, measure: closing|opening|movement,
                  show_detail: bool, scheme?: override}
                 Balances are debit-positive; use sign -1 for credit-natured lines.
formula          {formula: "fa - liab"} — arithmetic over other row ids (per column).
                 Functions: abs, min, max, round, pct(a, b) = a / b * 100.
manual           {values: {"cy": 1234.56}} — keyed amounts typed in by the user.
text             {label} — static text. Labels anywhere may use tokens: {fiscal_year},
                 {prior_fiscal_year}, {period_end}, {period_name}, {organization},
                 {row:ROW_ID} / {row:ROW_ID:COLUMN} (formatted amount of another row).
Common row keys: id, style {bold, italic, underline: single|double, indent}, hidden.

Column sources: actual (year_offset, entry_types), budget (budget_version original|amended),
formula (over other column keys of the same row).
"""
from __future__ import annotations

import ast
import copy
import operator
import re
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from fnmatch import fnmatchcase
from typing import Any, Callable, Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.period import FiscalYear, Period
from app.services.balances import (
    STATEMENT_ENTRY_TYPES,
    ZERO,
    AccountBalance,
    account_balances,
    classifications,
    is_credit_natured,
    last_period_number,
    load_accounts,
    match_classification,
    prior_fiscal_year,
    resolve_scheme_id,
)

SUMMABLE_TYPES = {"accounts", "section", "group", "manual"}
GROUP_TYPES = {"section", "group"}


class ReportDefinitionError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Safe formula evaluation
# ---------------------------------------------------------------------------

_BINOPS: Dict[type, Callable] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def _pct(a, b):
    return None if a is None or not b else a / b * Decimal("100")


def _round(a, n=0):
    return None if a is None else round(a, int(n))


_FUNCS: Dict[str, Callable] = {
    "abs": lambda a: None if a is None else abs(a),
    "min": lambda *a: min(x for x in a if x is not None) if any(x is not None for x in a) else None,
    "max": lambda *a: max(x for x in a if x is not None) if any(x is not None for x in a) else None,
    "round": _round,
    "pct": _pct,
}


def parse_formula(formula: str) -> ast.Expression:
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as exc:
        raise ReportDefinitionError(f"Invalid formula '{formula}': {exc.msg}") from exc
    for node in ast.walk(tree):
        if isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Name, ast.Load, ast.Constant,
                             ast.USub, ast.UAdd, *_BINOPS.keys())):
            continue
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
            continue
        raise ReportDefinitionError(f"Unsupported expression in formula '{formula}'")
    return tree


def formula_names(formula: str) -> Set[str]:
    tree = parse_formula(formula)
    funcs = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call)}
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - funcs


def evaluate_formula(formula: str, resolve: Callable[[str], Optional[Decimal]]) -> Optional[Decimal]:
    """Evaluate with Decimal arithmetic. Missing values propagate as None in +-*/ only
    when every operand is None; otherwise None is treated as zero. Division by zero → None."""
    tree = parse_formula(formula)

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                return Decimal(str(node.value))
            raise ReportDefinitionError(f"Unsupported constant in formula '{formula}'")
        if isinstance(node, ast.Name):
            return resolve(node.id)
        if isinstance(node, ast.UnaryOp):
            v = ev(node.operand)
            return None if v is None else (-v if isinstance(node.op, ast.USub) else v)
        if isinstance(node, ast.BinOp):
            left, right = ev(node.left), ev(node.right)
            if left is None and right is None:
                return None
            left, right = left or ZERO, right or ZERO
            if isinstance(node.op, ast.Div) and right == 0:
                return None
            return _BINOPS[type(node.op)](left, right)
        if isinstance(node, ast.Call):
            return _FUNCS[node.func.id](*(ev(a) for a in node.args))
        raise ReportDefinitionError(f"Unsupported expression in formula '{formula}'")

    return ev(tree)


# ---------------------------------------------------------------------------
# Definition normalisation (v1 → v2)
# ---------------------------------------------------------------------------

def normalize_definition(definition: Dict[str, Any]) -> Dict[str, Any]:
    """Return a version-2 definition. Version-1 definitions (flat sections with
    scheme_id/classification_values/negate) are converted."""
    if definition.get("version", 1) >= 2 or "rows" in definition:
        d = copy.deepcopy(definition)
        d.setdefault("columns", [{"key": "cy", "label": "{fiscal_year}", "source": "actual"}])
        d.setdefault("rows", [])
        return d

    sections = sorted(definition.get("sections", []), key=lambda s: s.get("sort_order", 0))
    columns = [{"key": "cy", "label": "{fiscal_year}", "source": "actual"}]
    if definition.get("comparative"):
        columns.append({"key": "py", "label": "{prior_fiscal_year}", "source": "actual", "year_offset": -1})
    rows = []
    for i, s in enumerate(sections):
        # v1 amounts were credit-positive (credit − debit), optionally negated.
        sign = 1 if s.get("negate") else -1
        rows.append(
            {
                "id": f"s{i}",
                "type": "section",
                "label": s["title"],
                "total_label": s.get("subtotal_label") or f"Total {s['title']}",
                "children": [
                    {
                        "type": "accounts",
                        "label": s["title"],
                        "scheme": s.get("scheme_id"),
                        "classifications": s.get("classification_values", []),
                        "sign": sign,
                        "show_detail": bool(definition.get("include_account_detail")),
                        "hidden": not definition.get("include_account_detail"),
                    }
                ],
            }
        )
    if rows:
        rows.append(
            {
                "id": "grand_total",
                "type": "formula",
                "label": "Grand Total",
                "formula": " + ".join(r["id"] for r in rows),
                "style": {"bold": True, "underline": "double"},
            }
        )
    return {
        "version": 2,
        "title": definition.get("title", "Report"),
        "subtitle": definition.get("subtitle"),
        "report_type": definition.get("report_type", "custom"),
        "number_format": {"decimals": 2, "currency_symbol": definition.get("currency_symbol", "$")},
        "show_zero_balances": definition.get("show_zero_balances", False),
        "columns": columns,
        "rows": rows,
    }


def validate_definition(definition: Dict[str, Any]) -> List[str]:
    """Structural validation. Returns a list of problems (empty when valid)."""
    d = normalize_definition(definition)
    problems: List[str] = []
    col_keys = [c.get("key") for c in d["columns"]]
    if not col_keys:
        problems.append("at least one column is required")
    if len(set(col_keys)) != len(col_keys):
        problems.append("column keys must be unique")
    for c in d["columns"]:
        src = c.get("source", "actual")
        if src not in ("actual", "budget", "formula"):
            problems.append(f"column '{c.get('key')}': unknown source '{src}'")
        if src == "formula":
            try:
                unknown = formula_names(c.get("formula", "")) - set(col_keys)
                if unknown:
                    problems.append(f"column '{c.get('key')}': unknown column(s) {sorted(unknown)}")
            except ReportDefinitionError as exc:
                problems.append(str(exc))

    ids: List[str] = []

    def walk(rows):
        for r in rows:
            if r.get("id"):
                ids.append(r["id"])
            t = r.get("type")
            if t not in ("section", "group", "accounts", "formula", "text", "manual"):
                problems.append(f"row '{r.get('label', r.get('id'))}': unknown type '{t}'")
            if t in GROUP_TYPES:
                walk(r.get("children", []))
            if t == "accounts" and r.get("measure", "closing") not in ("closing", "opening", "movement"):
                problems.append(f"row '{r.get('label')}': unknown measure '{r.get('measure')}'")

    walk(d["rows"])
    if len(set(ids)) != len(ids):
        problems.append("row ids must be unique")

    def walk_formulas(rows):
        for r in rows:
            if r.get("type") == "formula":
                try:
                    unknown = formula_names(r.get("formula", "")) - set(ids)
                    if unknown:
                        problems.append(f"row '{r.get('label')}': formula references unknown row(s) {sorted(unknown)}")
                except ReportDefinitionError as exc:
                    problems.append(str(exc))
            walk_formulas(r.get("children", []))

    walk_formulas(d["rows"])
    return problems


# ---------------------------------------------------------------------------
# Data context
# ---------------------------------------------------------------------------

class _ColumnData:
    """Account balances / budget amounts backing one source column."""

    def __init__(self, balances: Dict[int, AccountBalance], budget: Optional[Dict[int, Decimal]],
                 entry_types: tuple):
        self.balances = balances
        self.budget = budget
        self.entry_types = entry_types

    def account_ids(self):
        return set(self.balances) | set(self.budget or {})

    def value(self, account_id: int, measure: str, signed_budget: Callable[[int, Decimal], Decimal]) -> Decimal:
        if self.budget is not None:
            if measure != "closing":
                return ZERO
            amt = self.budget.get(account_id)
            return signed_budget(account_id, amt) if amt is not None else ZERO
        b = self.balances.get(account_id)
        if b is None:
            return ZERO
        if measure == "opening":
            return b.opening
        if measure == "movement":
            return b.movement(self.entry_types)
        return b.closing(self.entry_types)


def _fmt_date(d) -> str:
    return f"{d.strftime('%B')} {d.day}, {d.year}" if d else ""


class ReportEngine:
    def __init__(self, db: Session, definition: Dict[str, Any], fiscal_year_id: int,
                 period_id: Optional[int] = None):
        self.db = db
        self.d = normalize_definition(definition)
        problems = validate_definition(self.d)
        if problems:
            raise ReportDefinitionError("; ".join(problems))
        self.fy = db.get(FiscalYear, fiscal_year_id)
        if self.fy is None:
            raise ValueError(f"Fiscal year {fiscal_year_id} not found")
        self.period = db.get(Period, period_id) if period_id else None
        if period_id and (self.period is None or self.period.fiscal_year_id != fiscal_year_id):
            raise ValueError(f"Period {period_id} is not in fiscal year {fiscal_year_id}")
        self.through = self.period.period_number if self.period else last_period_number(db, fiscal_year_id)
        self.prior_fy = prior_fiscal_year(db, fiscal_year_id)
        self.warnings: List[str] = []
        self.columns = self.d["columns"]
        self.source_cols = [c for c in self.columns if c.get("source", "actual") != "formula"]
        self._col_data: Dict[str, _ColumnData] = {}
        self._class_cache: Dict[tuple, Dict[int, str]] = {}
        self._load()

    # -- loading -----------------------------------------------------------

    def _fy_for_offset(self, offset: int) -> Optional[FiscalYear]:
        return self.fy if offset == 0 else prior_fiscal_year(self.db, self.fy.id, -offset)

    def _load(self):
        from app.services.budget_service import budget_amounts_by_account

        for c in self.source_cols:
            fy = self._fy_for_offset(int(c.get("year_offset", 0)))
            entry_types = tuple(c.get("entry_types") or STATEMENT_ENTRY_TYPES)
            if fy is None:
                self.warnings.append(f"Column '{c['key']}': no fiscal year at offset {c.get('year_offset')}")
                self._col_data[c["key"]] = _ColumnData({}, None, entry_types)
            elif c.get("source") == "budget":
                amounts = budget_amounts_by_account(self.db, fy.id, c.get("budget_version", "original"))
                self._col_data[c["key"]] = _ColumnData({}, amounts, entry_types)
            else:
                through = min(self.through, last_period_number(self.db, fy.id))
                self._col_data[c["key"]] = _ColumnData(account_balances(self.db, fy.id, through), None, entry_types)

        all_ids = set().union(*(cd.account_ids() for cd in self._col_data.values())) if self._col_data else set()
        self.accounts = load_accounts(self.db, all_ids)
        self.default_scheme = resolve_scheme_id(self.db, self.d.get("scheme"))
        if self.default_scheme is None:
            self.warnings.append(f"Mapping scheme '{self.d.get('scheme') or 'PSAB'}' not found")

    def _classes(self, scheme) -> Dict[int, str]:
        scheme_id = self.default_scheme if scheme is None else resolve_scheme_id(self.db, scheme)
        key = (scheme_id,)
        if key not in self._class_cache:
            self._class_cache[key] = classifications(self.db, scheme_id, self.accounts.keys())
        return self._class_cache[key]

    def _signed_budget(self, account_id: int, amount: Decimal) -> Decimal:
        """Budget amounts are entered positive; convert to the debit-positive convention."""
        acct = self.accounts.get(account_id)
        cls = self._classes(None).get(account_id)
        return -amount if is_credit_natured(acct, cls) else amount

    # -- evaluation --------------------------------------------------------

    def _matching_accounts(self, row: Dict[str, Any]) -> List[int]:
        patterns = row.get("classifications") or []
        acct_patterns = row.get("accounts") or []
        classes = self._classes(row.get("scheme"))
        out = []
        for acct_id, acct in self.accounts.items():
            if patterns and match_classification(classes.get(acct_id), patterns):
                out.append(acct_id)
            elif acct_patterns and any(fnmatchcase(acct.acct_fmtd, p) for p in acct_patterns):
                out.append(acct_id)
        return sorted(out, key=lambda i: self.accounts[i].acct_fmtd)

    def build(self) -> Dict[str, Any]:
        rows = self.d["rows"]
        index: Dict[str, Dict[str, Any]] = {}
        self._assign_ids(rows, index, [0])
        values: Dict[str, Dict[str, Optional[Decimal]]] = {}
        in_progress: Set[str] = set()
        detail: Dict[str, List[Dict[str, Any]]] = {}

        def compute(row_id: str) -> Dict[str, Optional[Decimal]]:
            if row_id in values:
                return values[row_id]
            if row_id in in_progress:
                raise ReportDefinitionError(f"Circular reference involving row '{row_id}'")
            in_progress.add(row_id)
            row = index[row_id]
            t = row.get("type")
            result: Dict[str, Optional[Decimal]] = {}
            if t == "accounts":
                sign = Decimal(str(row.get("sign", 1)))
                measure = row.get("measure", "closing")
                acct_ids = self._matching_accounts(row)
                # Detail lines merge by account code so prior-year accounts (separate
                # Account rows) line up with the current year.
                lines: Dict[str, Dict[str, Any]] = {}
                for c in self.source_cols:
                    result[c["key"]] = ZERO
                for acct_id in acct_ids:
                    code = self.accounts[acct_id].acct_fmtd
                    line = lines.setdefault(
                        code, {"account_id": acct_id, "values": {c["key"]: ZERO for c in self.source_cols}}
                    )
                    if self.accounts[acct_id].fiscal_year_id == self.fy.id:
                        line["account_id"] = acct_id  # prefer the current-year description
                    for c in self.source_cols:
                        v = sign * self._col_data[c["key"]].value(acct_id, measure, self._signed_budget)
                        line["values"][c["key"]] += v
                        result[c["key"]] += v
                detail[row_id] = list(lines.values())
            elif t in GROUP_TYPES:
                for c in self.source_cols:
                    result[c["key"]] = ZERO
                for child in row.get("children", []):
                    ct = child.get("type")
                    if ct in SUMMABLE_TYPES or (ct == "formula" and child.get("include_in_total")):
                        cv = compute(child["id"])
                        for c in self.source_cols:
                            result[c["key"]] += cv.get(c["key"]) or ZERO
            elif t == "formula":
                for c in self.source_cols:
                    result[c["key"]] = evaluate_formula(
                        row["formula"], lambda name, k=c["key"]: compute(name).get(k)
                    )
            elif t == "manual":
                manual = row.get("values") or {}
                for c in self.source_cols:
                    v = manual.get(c["key"])
                    try:
                        result[c["key"]] = Decimal(str(v)) if v is not None and v != "" else None
                    except InvalidOperation:
                        self.warnings.append(f"Row '{row.get('label')}': invalid manual amount '{v}'")
                        result[c["key"]] = None
            else:  # text
                result = {c["key"]: None for c in self.source_cols}
            in_progress.discard(row_id)
            values[row_id] = result
            return result

        for row_id in index:
            compute(row_id)

        # Column formulas (variance, % etc.) per row and per detail line
        def apply_column_formulas(vals: Dict[str, Optional[Decimal]], has_values: bool):
            for c in self.columns:
                if c.get("source") == "formula":
                    vals[c["key"]] = (
                        evaluate_formula(c["formula"], lambda name: vals.get(name)) if has_values else None
                    )

        for row_id, vals in values.items():
            apply_column_formulas(vals, index[row_id].get("type") != "text")
        for lines in detail.values():
            for line in lines:
                apply_column_formulas(line["values"], True)

        self._values = values
        out_rows: List[Dict[str, Any]] = []
        self._emit(rows, 0, values, detail, out_rows)

        return {
            "title": self._tokens(self.d.get("title", "Report")),
            "subtitle": self._tokens(self.d.get("subtitle") or "") or None,
            "report_type": self.d.get("report_type"),
            "organization": settings.ORGANIZATION_NAME,
            "fiscal_year_id": self.fy.id,
            "fiscal_year": self.fy.label,
            "period_id": self.period.id if self.period else None,
            "period_name": self.period.name if self.period else None,
            "as_at": str(self._as_at()),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "number_format": {"decimals": 0, "currency_symbol": "$", **(self.d.get("number_format") or {})},
            "columns": [{"key": c["key"], "label": self._tokens(c.get("label", c["key"]))} for c in self.columns],
            "rows": out_rows,
            "warnings": self.warnings,
        }

    def _assign_ids(self, rows, index, counter):
        for r in rows:
            if not r.get("id"):
                counter[0] += 1
                r["id"] = f"_r{counter[0]}"
            index[r["id"]] = r
            if r.get("type") in GROUP_TYPES:
                self._assign_ids(r.get("children", []), index, counter)

    def _is_zero(self, vals: Dict[str, Optional[Decimal]]) -> bool:
        return all(not v for v in vals.values())

    def _emit(self, rows, level, values, detail, out):
        show_zero = self.d.get("show_zero_balances", False)
        for r in rows:
            t = r.get("type")
            style = r.get("style") or {}
            if t in GROUP_TYPES:
                if not r.get("hide_header"):
                    out.append(self._out_row(r, level, None, {"bold": True, **style}, "header"))
                self._emit(r.get("children", []), level + 1, values, detail, out)
                if r.get("total_label"):
                    out.append(self._out_row(
                        {**r, "label": r["total_label"]}, level, values[r["id"]],
                        {"bold": True, "underline": "single", **(r.get("total_style") or {})}, "total",
                    ))
                continue
            if r.get("hidden"):
                continue
            vals = values[r["id"]]
            if t == "accounts" and not show_zero and self._is_zero(vals) and not r.get("always_show"):
                continue
            if t == "accounts" and r.get("show_detail"):
                for line in detail.get(r["id"], []):
                    if not show_zero and self._is_zero(line["values"]):
                        continue
                    acct = self.accounts[line["account_id"]]
                    out.append({
                        "id": f"{r['id']}:{acct.id}",
                        "type": "account",
                        "label": acct.description or acct.acct_fmtd,
                        "acct_fmtd": acct.acct_fmtd,
                        "account_id": acct.id,
                        "level": level + 1,
                        "style": {},
                        "values": line["values"],
                    })
                if r.get("label"):
                    out.append(self._out_row({**r, "label": r.get("total_label") or r["label"]}, level, vals,
                                             {"bold": True, **style}, "subtotal"))
                continue
            out.append(self._out_row(r, level, vals if t != "text" else None, style, t))

    def _out_row(self, r, level, vals, style, kind):
        return {
            "id": r["id"],
            "type": kind,
            "label": self._tokens(r.get("label", "")),
            "level": level + int((r.get("style") or {}).get("indent", 0)),
            "style": style,
            "values": vals if vals is not None else {c["key"]: None for c in self.columns},
        }

    # -- tokens --------------------------------------------------------------

    def _as_at(self):
        if self.period:
            return self.period.end_date
        last = self.db.scalars(
            select(Period).where(Period.fiscal_year_id == self.fy.id).order_by(Period.period_number.desc())
        ).first()
        return last.end_date if last else self.fy.end_date

    def _tokens(self, text: str) -> str:
        if not text or "{" not in text:
            return text

        def row_token(m):
            row_id, col = m.group(1), m.group(2) or self.columns[0]["key"]
            v = getattr(self, "_values", {}).get(row_id, {}).get(col)
            return format_amount(v, self.d.get("number_format")) if v is not None else ""

        text = re.sub(r"\{row:([\w-]+)(?::([\w-]+))?\}", row_token, text)
        repl = {
            "fiscal_year": self.fy.label,
            "prior_fiscal_year": self.prior_fy.label if self.prior_fy else "",
            "period_end": _fmt_date(self._as_at()),
            "period_name": self.period.name if self.period else "",
            "organization": settings.ORGANIZATION_NAME,
        }
        return re.sub(r"\{(\w+)\}", lambda m: repl.get(m.group(1), m.group(0)), text)


def format_amount(value: Optional[Decimal], number_format: Optional[Dict[str, Any]] = None,
                  with_symbol: bool = False) -> str:
    """Accounting format: thousands separators, negatives in parentheses."""
    if value is None:
        return ""
    nf = number_format or {}
    decimals = int(nf.get("decimals", 0))
    sym = nf.get("currency_symbol", "$") if with_symbol else ""
    q = Decimal(1).scaleb(-decimals)
    v = Decimal(value).quantize(q, rounding=ROUND_HALF_UP)
    s = f"{abs(v):,.{decimals}f}"
    if v == 0:
        return "-"
    return f"({sym}{s})" if v < 0 else f"{sym}{s}"


def generate(db: Session, definition: Dict[str, Any], fiscal_year_id: int,
             period_id: Optional[int] = None) -> Dict[str, Any]:
    return ReportEngine(db, definition, fiscal_year_id, period_id).build()
