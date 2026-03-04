# OpenTrail WP — Implementation Plan
## BC Municipal Government Financial Reporting & Working Paper System

**Date:** March 2026
**Stack:** Python (FastAPI) + React (TypeScript) + PostgreSQL + Docker Compose
**Target:** Small-town BC local government finance teams (4–10 users, locally hosted)
**Scope:** Financial reporting, working paper preparation, budget management — no cloud dependencies

---

## Design Principles

1. **Local-first, no cloud.** All data stays on municipal servers. No external API calls for core functionality. No SaaS auth providers, no cloud storage, no telemetry.
2. **BC municipal context.** Fiscal year January 1 – December 31. PSAB/PSAS compliance as first-class concern. Not auditor software — this is the finance department's own tool.
3. **SQL connector-native.** AMAIS and VADIM (Tempus Nova) are the two primary ERP source systems — both SQL Server based, both with standardized schemas across all installations. AMAIS is the first integration target. The import model is live SQL queries against known table structures, not just CSV upload — though CSV/Excel always available as fallback.
4. **Budget workflow built-in.** Department heads submit requests; finance reviews; actuals pulled from the ERP connector for variance analysis. This is not an afterthought module.
5. **Minimize complexity.** 4–10 users. No need for distributed systems, message queues, or microservices. Simple, maintainable code wins.

---

## Project Structure

```
opentrail-wp/
├── backend/
│   ├── app/
│   │   ├── api/v1/            # FastAPI route handlers
│   │   │   ├── auth.py
│   │   │   ├── users.py
│   │   │   ├── periods.py
│   │   │   ├── accounts.py
│   │   │   ├── trial_balance.py
│   │   │   ├── journal_entries.py
│   │   │   ├── reports.py
│   │   │   ├── documents.py
│   │   │   ├── budget.py
│   │   │   └── connectors.py
│   │   ├── core/
│   │   │   ├── config.py      # Settings from env vars
│   │   │   ├── database.py    # SQLAlchemy engine + session
│   │   │   └── security.py    # JWT, password hashing
│   │   ├── models/            # SQLAlchemy ORM models
│   │   │   ├── user.py
│   │   │   ├── period.py
│   │   │   ├── account.py         # Account, AccountMapping
│   │   │   ├── segment.py         # SegmentDefinition
│   │   │   ├── mapping.py         # MappingScheme, AccountClassification
│   │   │   ├── trial_balance.py
│   │   │   ├── journal_entry.py
│   │   │   ├── document.py
│   │   │   ├── budget.py
│   │   │   └── connector.py
│   │   ├── schemas/           # Pydantic request/response schemas
│   │   ├── services/          # Business logic layer
│   │   │   ├── trial_balance.py
│   │   │   ├── report_generator.py
│   │   │   ├── sql_connector.py
│   │   │   ├── budget_service.py
│   │   │   └── document_manager.py
│   │   └── main.py            # FastAPI app entry point
│   ├── alembic/               # Database migrations
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/        # Reusable UI components
│   │   ├── pages/             # Route-level page components
│   │   │   ├── Dashboard/
│   │   │   ├── TrialBalance/
│   │   │   ├── JournalEntries/
│   │   │   ├── Reports/
│   │   │   ├── Budget/
│   │   │   ├── Documents/
│   │   │   └── Admin/
│   │   ├── hooks/             # React Query hooks for API calls
│   │   ├── store/             # Zustand state management
│   │   ├── lib/               # API client, utilities
│   │   └── App.tsx
│   ├── package.json
│   └── Dockerfile
├── nginx/
│   └── nginx.conf             # Reverse proxy: routes /api → backend, / → frontend
├── docker-compose.yml         # Production
├── docker-compose.dev.yml     # Dev with hot reload
└── .env.example               # Template for local configuration
```

---

## Phase 1: Foundation & Infrastructure

### 1.1 Docker Compose Stack

**Services:**
- `db` — PostgreSQL 16
- `backend` — FastAPI (uvicorn), port 8000 internal
- `frontend` — nginx serving built React app
- `proxy` — nginx reverse proxy, port 80 (and 443 with local cert optional)

**No** Redis, no Celery, no message queues — keep it simple for a small team.

### 1.2 Authentication & Users

Local JWT authentication only. No OAuth, no LDAP (can be added later if IT requests AD integration).

**User roles:**
| Role | Description |
|---|---|
| `finance_admin` | Full access — manages users, periods, connectors, signs off reports |
| `finance_officer` | Creates/edits trial balances, journal entries, reports, budgets |
| `budget_manager` | Submits and tracks department budget requests only |
| `viewer` | Read-only access to reports and working papers |

**Models:**
```
User: id, username, email, hashed_password, role, department, is_active, created_at
```

**Security:** bcrypt password hashing, HS256 JWTs with configurable expiry, refresh tokens stored in httpOnly cookies.

### 1.3 Period / Fiscal Year Management

Fiscal year: January 1 – December 31 (calendar year).

**Model:**
```
FiscalYear: id, label (e.g. "2024"), start_date, end_date, status (open/closed/locked)
Period: id, fiscal_year_id, period_number (1-12), name, start_date, end_date, is_closed
```

Roll-forward: closing a fiscal year copies account mappings and document structure to the new year. Opening balances = prior year closing balances after adjustments.

---

## Phase 2: Trial Balance Engine

### 2.1 Chart of Accounts & Mapping

The internal COA exists to layer classification structure on top of the ERP's own account data. It does **not** replace the ERP COA — it adds dimensions that drive financial statement generation, reporting groupings, and working paper templates.

**COA population strategy (in priority order):**
1. **Import from AMAIS connector** — pulls all 10 segment codes/descriptions plus account properties. This is the expected path for AMAIS users.
2. **Import from VADIM connector** — same approach.
3. **CSV/Excel import** — fallback for clients without a live connector, or to supplement.
4. **Manual entry** — available but not the expected workflow.

**Segment definitions are client-configurable.** AMAIS exposes up to 10 GL segments (`gl-acc1`..`gl-acc10`) whose meaning varies by installation — one client's seg1 is "fund", another's is "department". OpenTrail imports all segments generically and lets the `finance_admin` assign labels during setup. The labels drive column headings in the COA view and filter options in reports.

**Mapping schemes are flexible and user-defined.** Rather than hardcoding "PSAB categories" as fixed columns, OpenTrail supports named mapping schemes — a scheme is a named classification system (e.g. "PSAB", "Management Report", "Audit File") that assigns each account to a value within that scheme. A client can have multiple schemes simultaneously. PSAB is a first-class scheme but not the only one.

**Template generation is downstream.** Templates (Statement of Operations, Statement of Financial Position, etc.) are generated *from* the mapping scheme configuration, not embedded in the app. The workflow is: import COA → configure segment labels → build mapping schemes → export scheme as a structured spec → Claude generates the template structure → template is loaded into the report engine. This means OpenTrail's report engine is generic; the client-specific shape lives in the mapping scheme.

**Models:**
```
SegmentDefinition: id, connector_id, segment_number (1–10), label,
                   description, is_active
  -- e.g.: seg_number=1, label="Fund", is_active=true
  -- created/edited by finance_admin during initial setup
  -- drives column labels in COA view, filter options, and report dimensions

MappingScheme: id, org_id, name, description, is_active
  -- e.g.: name="PSAB", name="Management", name="Audit File"
  -- a client can have multiple schemes; one scheme per report type

AccountClassification: id, account_id, scheme_id, classification_value, sort_order
  -- e.g.: account_id=42, scheme_id=1 (PSAB), classification_value="Revenue"
  -- one row per account per scheme; updated when COA changes
  -- these rows are what drive financial statement line mapping

Account: id, fiscal_year_id, acct_fmtd, description, acct_type, record_class,
         capital_acct, dept_code, fund_code, stat,
         total_lvl, total_lvl_cde, rev_exp_rpt,
         object_str, project_str,
         seg1..seg10 (codes), seg1_descr..seg10_descr (descriptions),
         normal_balance (debit/credit), is_active,
         source_system (amais/vadim/csv/manual), connector_id
  -- all ERP fields preserved as-is; classification lives in AccountClassification

AccountMapping: id, account_id, source_system, source_acct_fmtd
  -- tracks origin for re-import reconciliation
```

**PSAB scheme values (built-in defaults, user can rename/extend):**
- `financial_assets` — PS 1201.031
- `liabilities` — PS 1201.032
- `non_financial_assets` — PS 1201.033
- `revenue`
- `expense`
- `accumulated_surplus` (derived — no direct account mapping needed)

### 2.2 Trial Balance Data

```
TrialBalanceEntry: id, period_id, account_id, opening_debit, opening_credit,
                   period_debit, period_credit, ytd_debit, ytd_credit,
                   source (connector_pull / csv_import / manual),
                   imported_at, connector_id
```

Closing balance = opening + period movements, then adjusted by journal entries.

### 2.3 Import

- **CSV/Excel import** — column mapping wizard (user maps "Account No", "Description", "Debit", "Credit" to internal fields)
- **SQL connector import** — see Phase 3

---

## Phase 3: SQL Database Connectors

This is a differentiating feature not present in any open-source alternative.

### 3.1 Connector Framework

Municipal ERP systems have **standardized schemas consistent across all customer installations**. This means pre-built, hardcoded query templates — not configurable placeholders. AMAIS runs on Progress OpenEdge; VADIM runs on SQL Server.

Generic SQL connector using SQLAlchemy with driver-level abstraction.

**Supported drivers:**
| System | Driver | SQLAlchemy URL Pattern |
|---|---|---|
| AMAIS (municipal ERP) | Progress OpenEdge via `pyodbc` + Progress ODBC driver | ODBC connection string |
| VADIM / Tempus Nova (municipal ERP) | SQL Server via `pymssql` or `pyodbc` | `mssql+pymssql://` |
| Generic SQL Server | `pymssql` / `pyodbc` | `mssql+pymssql://` |
| PostgreSQL | `psycopg2` | `postgresql+psycopg2://` |
| MySQL/MariaDB | `pymysql` | `mysql+pymysql://` |
| SQLite | built-in | `sqlite:///` |

**Connector Model:**
```
ExternalConnector: id, name,
                   system_type (amais/vadim/mssql/postgres/mysql/sqlite),
                   host, port, database_name, username,
                   encrypted_password,  # Fernet-encrypted at rest
                   schema_name,         # e.g. "dbo" for SQL Server
                   is_active, last_tested_at, last_pull_at,
                   created_by_user_id
```

Passwords encrypted using a Fernet key stored as an environment variable (never in the DB unencrypted).

### 3.2 AMAIS Connector *(first priority)*

AMAIS is a full municipal ERP system (general ledger, AP, AR, payroll, utilities billing, etc.) used by BC municipalities. All AMAIS installations share a consistent schema.

**Connection architecture:** AMAIS runs on **Progress OpenEdge** (not SQL Server). It exposes SQL access via a Progress SQL Broker through ODBC using the Progress OpenEdge ODBC driver (DataDirect or native). There is no SQLAlchemy dialect for Progress; the connector uses `pyodbc` directly with the Progress-specific ODBC connection string.

```python
# AMAIS connection via Progress ODBC SQL Broker
conn_str = (
    f"DRIVER={{Progress OpenEdge {driver_version} driver}};"
    f"HOST={host};PORT={port};DB={database};"
    f"UID={username};PWD={password};"
)
conn = pyodbc.connect(conn_str)
```

**Schema notes (confirmed from SYSTABLES/SYSCOLUMNS introspection):**

Progress SQL-92 requires double-quoting all hyphenated table and column names (e.g. `PUB."gl-mstr"`, `"object-str"`). All queries below follow this convention.
Schema prefix `"CONCORD"."PUB"."table"` observed in user's M queries; for ODBC DSN connections `PUB."table"` is sufficient (DSN binds to the catalog).

Key table roles (confirmed by user):
- `gl-mstr` — **THE** GL account master / COA listing and account properties (gl-master is empty; use gl-mstr for everything)
- `gl-act-prds` — **actual amounts by period** (the trial balance source; `rec-type='P'` for posted actuals)
- `gl-bud` — budget amounts by period (original, provisional, transfers, finals stored as separate `rec-type` rows)
- `gl-trn` — GL transaction detail (segment FKs `gl-acc1`..`gl-acc10`; `object-str` = formatted account string)
- `wm-master` — work order detail (grants, managerial reporting; `gl-acc1`..`gl-acc10` segment FKs)
- `gl-seg1`..`gl-seg10` — account segment description tables (confirmed; join key and description field TBC — user to provide)
- `gl-prds` — fiscal period calendar (`fisc-yr` + `prd` + `date-from` + `date-thru` + `status-flag`)
- `gl-transaction` — older transaction table (legacy; do not use)
- `fa-hdr` — financial fixed assets (TCA schedule) — **empty at surveyed installation**; TCA source TBD

**Pre-built AMAIS queries:**

```sql
-- 1. CHART OF ACCOUNTS
-- Populate internal COA on first setup; user then assigns PSAB categories.
-- All field names confirmed via SYSCOLUMNS.
-- acct-fmtd = full formatted account key (varchar 30); consistent across gl-mstr/gl-act-prds/gl-bud.
-- object-str (varchar 80) and project-str (varchar 80) are segment-level display strings, not the PK.
-- total-lvl / total-lvl-cde drive the COA hierarchy for financial statement subtotalling.
-- acct-type values: TBC (run diagnostic below); record-class values: TBC.
-- gl-seg# join: gl-acc1..gl-acc10 (numeric) = x-code (numeric) in gl-seg1..gl-seg10.
-- Segment-to-meaning mapping is CLIENT-CONFIGURABLE — seg# assignment differs per installation.
-- All 10 segments are always imported; finance_admin labels them during setup via SegmentDefinition.
SELECT
    m."acct-fmtd"       AS acct_fmtd,
    m."fisc-yr"         AS fisc_yr,
    m.descr             AS description,
    m."acct-type"       AS acct_type,
    m."record-class"    AS record_class,
    m."capital-acct"    AS capital_acct,
    m."dept-code"       AS dept_code,
    m."fund-code"       AS fund_code,
    m.stat              AS stat,
    m."total-lvl"       AS total_lvl,
    m."total-lvl-cde"   AS total_lvl_cde,
    m."rev-exp-rpt"     AS rev_exp_rpt,
    m."object-str"      AS object_str,
    m."project-str"     AS project_str,
    m."gl-acc1"         AS seg1,
    m."gl-acc2"         AS seg2,
    m."gl-acc3"         AS seg3,
    m."gl-acc4"         AS seg4,
    m."gl-acc5"         AS seg5,
    m."gl-acc6"         AS seg6,
    m."gl-acc7"         AS seg7,
    m."gl-acc8"         AS seg8,
    m."gl-acc9"         AS seg9,
    m."gl-acc10"        AS seg10,
    s1.descr            AS seg1_descr,
    s2.descr            AS seg2_descr,
    s3.descr            AS seg3_descr,
    s4.descr            AS seg4_descr,
    s5.descr            AS seg5_descr,
    s6.descr            AS seg6_descr,
    s7.descr            AS seg7_descr,
    s8.descr            AS seg8_descr,
    s9.descr            AS seg9_descr,
    s10.descr           AS seg10_descr
FROM PUB."gl-mstr" m
LEFT JOIN PUB."gl-seg1"  s1  ON m."gl-acc1"  = s1."x-code"
LEFT JOIN PUB."gl-seg2"  s2  ON m."gl-acc2"  = s2."x-code"
LEFT JOIN PUB."gl-seg3"  s3  ON m."gl-acc3"  = s3."x-code"
LEFT JOIN PUB."gl-seg4"  s4  ON m."gl-acc4"  = s4."x-code"
LEFT JOIN PUB."gl-seg5"  s5  ON m."gl-acc5"  = s5."x-code"
LEFT JOIN PUB."gl-seg6"  s6  ON m."gl-acc6"  = s6."x-code"
LEFT JOIN PUB."gl-seg7"  s7  ON m."gl-acc7"  = s7."x-code"
LEFT JOIN PUB."gl-seg8"  s8  ON m."gl-acc8"  = s8."x-code"
LEFT JOIN PUB."gl-seg9"  s9  ON m."gl-acc9"  = s9."x-code"
LEFT JOIN PUB."gl-seg10" s10 ON m."gl-acc10" = s10."x-code"
WHERE m."fisc-yr" = {fiscal_year}
ORDER BY m."acct-fmtd"
```

```sql
-- 1b. DIAGNOSTIC: distinct acct-type / record-class / stat values
-- Run once during setup to understand COA classification scheme.
-- Results inform how OpenTrail maps acct-type to PSAB categories.
SELECT DISTINCT "acct-type", "record-class", stat
FROM PUB."gl-mstr"
ORDER BY "acct-type", "record-class"
```

```sql
-- 2. TRIAL BALANCE BY PERIOD
-- Primary source for working trial balance and financial statements.
-- All field names confirmed via SYSCOLUMNS.
-- JOIN key: gl-act-prds.acct-fmtd = gl-mstr.acct-fmtd (both varchar 30 — confirmed consistent).
-- Also join on fisc-yr so we get the correct COA year's description/type/flags.
-- rec-type 'P' = Posted actuals; pull all rec-types and let user configure which to surface.
-- gl-trn.object-str vs gl-mstr.acct-fmtd join TBC — very likely same value, different field names.
SELECT
    p."acct-fmtd"       AS acct_fmtd,
    p."fisc-yr"         AS fisc_yr,
    p."fisc-prd"        AS fisc_prd,
    p."rec-type"        AS rec_type,
    p.amount            AS amount,
    p.remarks           AS remarks,
    m.descr             AS description,
    m."acct-type"       AS acct_type,
    m."record-class"    AS record_class,
    m."capital-acct"    AS capital_acct,
    m."dept-code"       AS dept_code,
    m."fund-code"       AS fund_code,
    m."total-lvl"       AS total_lvl,
    m."rev-exp-rpt"     AS rev_exp_rpt
FROM PUB."gl-act-prds" p
LEFT JOIN PUB."gl-mstr" m
    ON p."acct-fmtd" = m."acct-fmtd"
    AND m."fisc-yr" = p."fisc-yr"
WHERE p."fisc-yr" = {fiscal_year}
  AND p."rec-type" = 'P'
ORDER BY p."acct-fmtd", p."fisc-prd"
```

```sql
-- 3. GL TRANSACTION DETAIL
-- Line-level drill-down for supporting schedules and leadsheets
-- Column list confirmed from user's live Power Query. SUBSTR(descr1,1,255) because
-- descr1 is a wide field that truncates in some ODBC drivers.
-- object-str is the formatted account string (equivalent to acct-fmtd in other tables).
-- gl-acc1..gl-acc10 are individual segment codes joining to gl-seg1..gl-seg10.
SELECT
    t."object-str"          AS acct_fmtd,
    t."fisc-yr"             AS fisc_yr,
    t."fisc-prd"            AS fisc_prd,
    t."primary-date"        AS trans_date,
    t."second-date"         AS second_date,
    t.amount                AS amount,
    SUBSTR(t.descr1, 1, 255) AS description1,
    t.descr2                AS description2,
    t."ref-no"              AS reference_no,
    t."je-batch-no"         AS je_batch_no,
    t."je-dtl-id"           AS je_dtl_id,
    t."sl-code"             AS sl_code,
    t."sl-account-no"       AS sl_account_no,
    t."inv-no"              AS inv_no,
    t."po-no"               AS po_no,
    t."work-order"          AS work_order,
    t."work-id"             AS work_id,
    t."job-no"              AS job_no,
    t."asset-no"            AS asset_no,
    t."veh-no"              AS veh_no,
    t."emp-no"              AS emp_no,
    t."usr-id"              AS usr_id,
    t.location              AS location,
    t.recovery              AS recovery,
    t.archival              AS archival,
    t."gl-acc1"             AS seg1,
    t."gl-acc2"             AS seg2,
    t."gl-acc3"             AS seg3,
    t."gl-acc4"             AS seg4,
    t."gl-acc5"             AS seg5,
    t."gl-acc6"             AS seg6,
    t."gl-acc7"             AS seg7,
    t."gl-acc8"             AS seg8,
    t."gl-acc9"             AS seg9,
    t."gl-acc10"            AS seg10
FROM PUB."gl-trn" t
WHERE t."fisc-yr" = {fiscal_year}
  AND t."fisc-prd" BETWEEN {period_from} AND {period_to}
ORDER BY t."object-str", t."primary-date"
```

```sql
-- 3b. WORK ORDER DETAIL (for grant reporting and managerial schedules)
-- wm-master is the AMAIS work/service order module.
-- gl-acc1..gl-acc10 match gl-trn segments; project-str is the formatted project string.
-- SUBSTR(details,1,255) because details is a wide/CLOB field.
SELECT
    w."work-order"              AS work_order,
    w."wm-master-id"            AS wm_master_id,
    w.description               AS description,
    w."work-desc"               AS work_desc,
    w."work-assign-desc"        AS work_assign_desc,
    SUBSTR(w.details, 1, 255)   AS details,
    w."project-str"             AS project_str,
    w."project-no"              AS project_no,
    w."fiscal-year"             AS fiscal_year,
    w."budget-year"             AS budget_year,
    w."budget-cycle"            AS budget_cycle,
    w."date-work-order"         AS date_work_order,
    w."date-exp-complete"       AS date_exp_complete,
    w."date-act-complete"       AS date_act_complete,
    w."wm-status"               AS wm_status,
    w."rec-type"                AS rec_type,
    w."activity-code"           AS activity_code,
    w.active                    AS active,
    w."on_hold"                 AS on_hold,
    w."wm-cost"                 AS wm_cost,
    w."accomp-exp"              AS accomp_exp,
    w."accomp-act"              AS accomp_act,
    w.account                   AS account,
    w."customer-no"             AS customer_no,
    w.billable                  AS billable,
    w."ref-no"                  AS ref_no,
    w.prov                      AS prov,
    w."response-code"           AS response_code,
    w."time-work-order"         AS time_work_order,
    w."super-comm"              AS super_comm,
    w."comp-comm"               AS comp_comm,
    w."asset-no"                AS asset_no,
    w."area-str-locate"         AS area_str_locate,
    w."work-house"              AS work_house,
    w."work-street"             AS work_street,
    w."work-suite"              AS work_suite,
    w."work-phone"              AS work_phone,
    w.unit                      AS unit,
    w."gl-acc1"                 AS seg1,
    w."gl-acc2"                 AS seg2,
    w."gl-acc3"                 AS seg3,
    w."gl-acc4"                 AS seg4,
    w."gl-acc5"                 AS seg5,
    w."gl-acc6"                 AS seg6,
    w."gl-acc7"                 AS seg7,
    w."gl-acc8"                 AS seg8,
    w."gl-acc9"                 AS seg9,
    w."gl-acc10"                AS seg10
FROM PUB."wm-master" w
WHERE w."fiscal-year" = {fiscal_year}
ORDER BY w."work-order"
```

```sql
-- 4. BUDGET BY PERIOD
-- gl-bud structure mirrors gl-act-prds exactly (same acct-fmtd/fisc-yr/fisc-prd/rec-type/amount).
-- All field names confirmed via SYSCOLUMNS.
-- rec-type values in gl-bud: meaning TBC — pull all and surface rec-type to user for configuration.
-- Approved budget rec-type (for PSAB Statement of Operations comparison column): TBC.
SELECT
    b."acct-fmtd"       AS acct_fmtd,
    b."fisc-yr"         AS fisc_yr,
    b."fisc-prd"        AS fisc_prd,
    b."rec-type"        AS rec_type,
    b.amount            AS amount,
    b."line-no"         AS line_no,
    b.remarks           AS remarks,
    b."date-created"    AS date_created,
    b."usr-id"          AS usr_id,
    m.descr             AS description,
    m."acct-type"       AS acct_type
FROM PUB."gl-bud" b
LEFT JOIN PUB."gl-mstr" m
    ON b."acct-fmtd" = m."acct-fmtd"
    AND m."fisc-yr" = b."fisc-yr"
WHERE b."fisc-yr" = {fiscal_year}
ORDER BY b."acct-fmtd", b."fisc-prd", b."rec-type"
```

```sql
-- 5. FISCAL PERIOD CALENDAR
-- Loaded once per fiscal year; drives period selector in UI
SELECT
    "fisc-yr"       AS fisc_yr,
    prd             AS period_no,
    "date-from"     AS date_from,
    "date-thru"     AS date_thru,
    descr           AS period_name,
    "status-flag"   AS status
FROM PUB."gl-prds"
ORDER BY "fisc-yr", prd
```

```sql
-- 6. AP OUTSTANDING (for accrual working papers)
-- Confirmed stat codes: P=Paid, V=Void, H=Hold, S=Selected for payment run,
-- U=Unposted, blank=Open. Outstanding = everything except Paid and Void.
SELECT
    i."vend-no"                         AS vendor_no,
    m.name                              AS vendor_name,
    i."inv-no"                          AS invoice_no,
    i."inv-date"                        AS invoice_date,
    i."due-date"                        AS due_date,
    i."amt-inv"                         AS invoice_amount,
    i."amt-paid"                        AS amount_paid,
    (i."amt-inv" - i."amt-paid")        AS balance_owing,
    i."fisc-yr"                         AS fisc_yr,
    i."fisc-prd"                        AS fisc_prd,
    i.stat                              AS status,
    i.descr                             AS description
FROM PUB."ap-inv" i
LEFT JOIN PUB."ap-master" m ON i."vend-no" = m."vend-no"
WHERE i.stat NOT IN ('P', 'V')   -- P=Paid, V=Void (confirmed)
ORDER BY i."vend-no", i."inv-date"
```

```sql
-- 7. AR OUTSTANDING
-- ar-invos is a purpose-built outstanding AR view in AMAIS
SELECT
    o."customer-no"         AS customer_no,
    m.name                  AS customer_name,
    o."invoice-no"          AS invoice_no,
    o."invoice-date"        AS invoice_date,
    o."due-date"            AS due_date,
    o.amount                AS amount,
    o.description           AS description,
    o."reference-no"        AS reference_no,
    o."transaction-type"    AS transaction_type
FROM PUB."ar-invos" o
LEFT JOIN PUB."ar-master" m ON o."customer-no" = m."account-no"
WHERE o."paid-indicator" = 0   -- 0=outstanding (bit field)
ORDER BY o."customer-no", o."invoice-date"
```

```sql
-- 8. FIXED ASSETS / TCA SCHEDULE (PS 3150)
-- NOTE: fa-hdr (financial FA module) is empty at surveyed installation —
-- this municipality does not appear to use the AMAIS financial FA module.
-- TCA schedule will require an alternative source:
--   Option A: Manual CSV import (asset register from spreadsheet)
--   Option B: Query fa-master (fleet/WM module) if TCA assets are tracked there
--   Option C: Derive from GL using capital-acct flag + fa_fund_src table
-- Query below is preserved for installations that do use fa-hdr; skip otherwise.
SELECT
    h."asset-no"        AS asset_no,
    h."asset-class"     AS asset_class,
    c.descr             AS class_descr,
    h."asset-grp"       AS asset_group,
    h.descr             AS description,
    h."pur-date"        AS purchase_date,
    h."pur-amt"         AS purchase_amount,
    h."into-service"    AS in_service_date,
    h."exp-life"        AS expected_life_years,
    h."amort-code"      AS amort_code,
    a."amort-method"    AS amort_method,
    a.rate              AS amort_rate,
    h."salvage_value"   AS salvage_value,
    h."rep-cost"        AS replacement_cost,
    h."federal-grant"   AS federal_grant,
    h.dept              AS department,
    h.stat              AS status
FROM PUB."fa-hdr" h
LEFT JOIN PUB."fa-class" c ON h."asset-class" = c."asset-class"
LEFT JOIN PUB."fa-amort" a ON h."amort-code" = a."amort-code"
ORDER BY h."asset-class", h."asset-no"
```

**Confirmed status codes:**
- `ap-inv.stat`: `P`=Paid, `V`=Void, `H`=Hold, `S`=Selected for payment run, `U`=Unposted, blank=Open
- `gl-act-prds.rec-type`: `P`=Posted actuals; `B1`–`B7`=budget versions 1–7; `BP`=budget provisional; `C1`/`C2`/`C3`/`C7`=comparative/cumulative (meaning TBC)

**Confirmed via SYSCOLUMNS introspection:**
- `gl-mstr`: join key = `acct-fmtd` (varchar 30); description = `descr`; `acct-type`, `record-class`, `capital-acct`, `dept-code`, `fund-code`, `stat`, `total-lvl`, `total-lvl-cde`, `rev-exp-rpt`, `object-str`, `project-str` all present
- `gl-act-prds`: join key = `acct-fmtd` (varchar 30) — matches gl-mstr exactly; also has `remarks`
- `gl-bud`: identical structure to gl-act-prds; adds `line-no`, `date-created`, `usr-id`, `remarks`
- `gl-seg1`..`gl-seg10`: all present; join key = `x-code` (numeric 15) → `gl-acc1`..`gl-acc10`; description = `descr`
- `gl-trn.object-str` vs `gl-mstr.acct-fmtd`: very likely the same value (different field names); join needed in transaction detail drill-down

**Resolved at runtime, not design time:**
- `acct-type` and `record-class` values — surfaced by diagnostic query 1b during client setup; used to suggest default PSAB classifications in the mapping scheme UI
- Budget `rec-type` for approved budget — user selects it in the connector configuration UI when setting up their budget comparison column; no hardcoded default needed
- Segment labels — user assigns them during setup step 4 above; not a design question
- `fa-hdr` is empty at the reference installation — TCA will use CSV import or manual entry for this client; other clients using the AMAIS FA module will use query 8 as-is

The user selects "AMAIS" as the system type, enters host/port/credentials, and all 8 queries execute immediately against the confirmed schema. The Progress OpenEdge ODBC driver must be installed on the OpenTrail WP host server (documented in deployment guide).

### 3.3 VADIM Connector *(second priority)*

VADIM (Tempus Nova) is another BC municipal ERP on SQL Server, also with a consistent schema across installations. Integration follows the same pattern as AMAIS.

**Pre-built VADIM queries:**
- **GL Account list** — pull chart of accounts
- **Trial balance by period** — debit/credit totals per account per period
- **GL transaction detail** — line-level transaction drill-down
- **Budget amounts by account/period** — feeds budgeting module

### 3.4 Import Workflow

**First-time setup (one-time per client):**
1. Configure connector (system type, host, credentials, DB name)
2. "Test Connection" — verifies connectivity, checks expected tables exist
3. **Import COA** — pulls account structure, stores all 10 segment codes/descriptions, creates `Account` and `AccountMapping` rows
4. **Label segments** — `finance_admin` assigns labels to the segments that are in use (e.g. "Fund", "Department", "GL Account", "Project") and marks unused ones inactive
5. **Define mapping schemes** — create named schemes (at minimum: "PSAB"); assign each account to a classification value within each scheme
6. **Export mapping scheme** — structured JSON/CSV export of segment labels + account classifications; can be handed to Claude to generate report templates
7. **Load templates** — generated templates imported into the report engine

**Ongoing period pulls:**
1. User selects fiscal year and period
2. System executes queries (trial balance, budget, transactions as configured)
3. Preview results before commit
4. Data written to `TrialBalanceEntry` with `source = connector_id`
5. Pull history logged with row counts and timestamp
6. Re-import COA if new accounts have been added in the ERP since last pull

### 3.5 Custom Query Support

For advanced users: a **Custom Query** feature lets `finance_admin` users write and save named SQL queries against any configured connector. Results can be materialized into the app as supporting schedule data or displayed in reports. This is deliberately simple — not a full query builder, just a SQL text editor with parameterization support for `{fiscal_year}` and `{period}` tokens.

---

## Phase 4: Journal Entries & Adjustments

### 4.1 Entry Types

Journal entry types for municipal finance working paper purposes:

| Type | Description | Flows To |
|---|---|---|
| `adjusting` | Standard period-end corrections | GL records + financial statements |
| `reclassifying` | Presentation reclassifications | Financial statements only (not GL) |
| `elimination` | Consolidation eliminations (for orgs with controlled entities) | Consolidated view only |
| `budget_variance` | Budget adjustment entries (for amended budgets) | Budget module |

### 4.2 Models

```
JournalEntry: id, period_id, entry_date, reference, description,
              entry_type, prepared_by_user_id, reviewed_by_user_id,
              status (draft/posted/approved), created_at

JournalLine: id, journal_entry_id, account_id, debit, credit,
             description, gl_reference
```

Balance enforcement: prevent posting if debit ≠ credit (configurable: warn vs. hard block).

### 4.3 Auto-Generated Schedules

From the mapped trial balance + journal entries, the system auto-generates:
- Working trial balance (opening, adjustments, closing per account)
- Leadsheets by PSAB group
- Adjusting journal entry schedule
- Reclassification schedule

---

## Phase 5: Report Builder & Financial Statements

The report system is a full-featured report builder, not a fixed template engine. Pre-built legislated report templates are provided as starting points, but every report is editable and users can build entirely custom reports from scratch.

### 5.1 Report Builder

**Design model:** Reports are structured as a tree of sections → row groups → rows. Each row maps to one of:
- An account or account group (pulling live balance data)
- A calculated field (sum, difference, percentage, ratio of other rows)
- A static text/label row
- A dynamic value (linked to a specific account balance, date, or system field)

Users can drag-and-drop rows, change account mappings, add formula rows, rename headings, set number formats, and configure comparative columns — all through the UI without writing code.

**Report types supported:**
| Category | Examples |
|---|---|
| **Legislated — PSAB** | Statement of Financial Position, Statement of Operations, SCNFA, Cash Flow Statement, Segment Disclosure, TCA Schedule, Notes |
| **Legislated — LGDE/SOFI** | SOFI statements (Financial Position, Operations, SCNFA, Cash Flow), Supplier Payments schedule (>$25K), Employee Remuneration schedule (>$75K), Guarantee & Indemnity schedule |
| **Working papers** | Working trial balance, leadsheets by PSAB group, AJE schedule, reclassification schedule |
| **Budget** | Budget vs. actual by department, by account group, multi-year comparison, council budget presentation |
| **Grant reporting** | Custom grant expenditure reports mapped to grant-specific account codes |
| **Managerial** | Any user-defined report — departmental cost summaries, project tracking, utility rate analysis, etc. |

**Report configuration stored as JSON:** Each saved report is a JSON definition (section tree + formatting + data source mappings). This makes reports portable, version-controllable, and copyable between fiscal years.

### 5.2 Built-In Legislated Templates

Pre-built templates that conform to current legislated requirements. These are used as starting points and can be modified but ship in a "protected" state so users can always revert to the standard layout.

**PSAB Annual Financial Statements:**

| Statement | Standard | Notes |
|---|---|---|
| Statement of Financial Position | PS 1201.031–.033 | Net Financial Assets/Debt as key line |
| Statement of Operations | PS 1201 | Budget vs. Actual required column |
| Statement of Change in Net Financial Assets | PS 1201 | |
| Statement of Cash Flow | PS 2450 | Direct or indirect method |
| Schedule of Segment Disclosure | PS 2700 | Optional, common for larger municipalities |
| Tangible Capital Asset Schedule | PS 3150 | By asset class |
| Notes to Financial Statements | Various PS sections | Modular note blocks with dynamic value links |

**LGDE / SOFI (Financial Information Act, BC):**

Required annually for BC local governments. Submitted to the province via the LGDE web system; this module generates the underlying schedules.

| Schedule | Requirement |
|---|---|
| Statement of Financial Position | Same as PSAB SFP, LGDE format |
| Statement of Operations | Same as PSAB SO, LGDE format |
| Statement of Change in Net Financial Assets | LGDE format |
| Statement of Cash Flows | LGDE format |
| Schedule of Supplier Payments | Payments >$25,000 in the calendar year |
| Schedule of Employee Remuneration & Expenses | Employees earning >$75,000 |
| Schedule of Guarantee and Indemnity Agreements | Per s.168 LGDE requirements |

### 5.3 Leadsheets & Working Papers (Auto-Generated)

From the mapped trial balance + journal entries:
- Working trial balance (opening → adjustments → closing per account)
- Leadsheets by PSAB group (auto-built from report builder layout)
- Adjusting journal entry schedule
- Reclassification schedule

These are generated automatically but can also be opened in the report builder for customization.

### 5.4 Export

- **PDF** via WeasyPrint (CSS-to-PDF; handles multi-column financial statement layouts)
- **Excel** via openpyxl (for circulation to council, further manipulation)
- **Working papers package** — ZIP of all generated documents for a period

---

## Phase 6: Budgeting Module

The budget module is built specifically for BC municipal budget processes and is a core feature of the system, not an afterthought.

### 6.1 Budget Workflow Overview

```
Budget Year Setup → Department Request Submission → Finance Review →
Consolidation → Council Approval → Budget-to-Actual Monitoring
```

### 6.2 Budget Request System

Department budget managers (role: `budget_manager`) log in and submit requests for their department accounts.

**Models:**
```
BudgetYear: id, fiscal_year_id, label, submission_deadline,
            status (setup/open/under_review/approved/adopted),
            instructions_text, created_by

BudgetRequest: id, budget_year_id, account_id, department,
               prior_year_actual, prior_year_budget, proposed_amount,
               justification_text, supporting_notes,
               submitted_by_user_id, submitted_at,
               reviewed_by_user_id, review_comment,
               status (draft/submitted/approved/modified/rejected),
               approved_amount

BudgetLine: id, budget_year_id, account_id, approved_amount,
            budget_type (operating/capital)
```

### 6.3 Budget-to-Actual Comparison

Pulls actual YTD figures from the trial balance (sourced from the active ERP connector — AMAIS or VADIM) and compares against approved budget lines.

Report outputs:
- **Budget vs. Actual by Department** — variance $, variance %, traffic-light status
- **Budget vs. Actual by Account Group** — PSAB-aligned summary
- **Multi-year comparison** — current budget / current actual / prior actual / prior budget
- **Variance drill-down** — click a department to see account-level detail

### 6.4 Budget Amendment Tracking

Mid-year budget amendments tracked separately from original budget. Amendment entries logged with approval reference and rationale. Statement of Operations shows: Original Budget | Amended Budget | Actual | Variance.

---

## Phase 7: Document Management

Focused on what a municipal finance team actually needs for working paper and document management.

### 7.1 Working Paper Files

```
WorkingPaper: id, fiscal_year_id, folder_path, filename, display_name,
              file_type (pdf/xlsx/docx/img/other), file_size,
              uploaded_by_user_id, uploaded_at, description,
              version_number, parent_version_id

WPAnnotation: id, working_paper_id, user_id, text, created_at,
              is_resolved, resolved_by_user_id
```

Files stored on local filesystem (Docker volume). Folder structure mirrors typical municipal audit binder:
- `/permanent/` — entity information, bylaws, council minutes
- `/current/[year]/` — current period working papers
- `/statements/` — generated financial statements
- `/budget/` — budget working papers

### 7.2 Sign-Off Workflow

Two-level sign-off (appropriate for small team):
1. **Preparer sign-off** — finance officer marks working paper complete
2. **Reviewer sign-off** — finance director/deputy reviews and approves

Post-sign-off modifications flagged and require re-approval.

### 7.3 Period Close & Roll Forward

1. Finance admin initiates period close
2. System checks: all journal entries posted, required sign-offs complete
3. Closing balance snapshot written to `TrialBalanceEntry` for the period
4. Roll forward to new fiscal year: account mappings copied, opening balances set from prior closing

---

## Phase 8: Local Collaboration

### 8.1 Multi-User Access

- PostgreSQL handles concurrent writes safely via transactions
- No file locking needed (we're in a DB, not a file system)
- **Optimistic locking** on critical records (trial balance entries, budget requests) — detect conflicts if two users edit the same record simultaneously

### 8.2 Real-Time Notifications

Server-Sent Events (SSE) for lightweight real-time updates:
- "User X just posted journal entry #45"
- "Budget request for Parks submitted"
- "Finance Director has signed off on Statement of Operations"

SSE is simpler than WebSockets and sufficient for this use case (4–10 users).

### 8.3 Audit Trail

All changes to financial data logged:

```
AuditLog: id, user_id, action, resource_type, resource_id,
          old_values (JSONB), new_values (JSONB), ip_address, timestamp
```

This is not optional — it's required for accountability in public sector finance.

---

## Tech Stack Summary

| Layer | Technology | Rationale |
|---|---|---|
| Backend framework | FastAPI (Python 3.12+) | Fast, async, excellent type safety, auto OpenAPI docs |
| ORM | SQLAlchemy 2.0 + Alembic | Industry standard, supports both async and sync, great migration support |
| App database | PostgreSQL 16 | Robust for financial data, JSONB for flexible audit logs |
| External DB access | pyodbc (AMAIS/Progress direct) + SQLAlchemy + pymssql (VADIM/SQL Server) | AMAIS uses Progress ODBC driver directly; VADIM and generic SQL use SQLAlchemy |
| Auth | python-jose (JWT) + passlib (bcrypt) | Local auth, no cloud dependencies |
| Encryption | cryptography (Fernet) | Encrypt DB credentials at rest |
| PDF generation | WeasyPrint | CSS-to-PDF, good for financial statements |
| Excel | openpyxl | Reading and writing Excel files |
| Data processing | pandas | Trial balance calculations, budget aggregations |
| Frontend framework | React 18 + TypeScript + Vite | Fast dev experience, strong typing |
| UI components | shadcn/ui + Tailwind CSS | Clean, accessible components; no external CDN |
| State management | Zustand | Lightweight, no boilerplate |
| Server state | TanStack Query (React Query) | API data fetching, caching, invalidation |
| Tables | TanStack Table | For trial balance and budget grids |
| Charts | Recharts | Budget vs. actual charts, ratio analysis |
| Deployment | Docker Compose | Simple, reproducible local deployment |
| Reverse proxy | nginx | Serve frontend, proxy /api to backend |

---

## Build Phases & Priorities

### MVP (Phases 1–3): Core financial data pipeline
1. Foundation: Docker Compose, FastAPI, React scaffold, PostgreSQL, auth
2. Period/fiscal year management (calendar year Jan–Dec)
3. AMAIS SQL connector — COA import, trial balance pull, GL detail
4. Chart of accounts with PSAB mapping (populated from AMAIS import)
5. CSV/Excel trial balance import (fallback path)
6. Generic SQL connector framework

### Phase 2: Working paper functionality & report builder
7. Journal entries (adjusting and reclassifying)
8. Auto-generated leadsheets and working trial balance
9. Report builder core (section tree, account row mapping, calculated rows, comparative columns)
10. Built-in PSAB templates (SFP, SO, SCNFA, SCF, Notes) — built as report builder configs
11. LGDE/SOFI schedules (Supplier Payments, Employee Remuneration, Guarantees)
12. PDF and Excel export
13. Document management (file upload, folders, sign-off)

### Phase 3: Budget module
12. Budget year setup and department request portal
13. Budget-to-actual comparison with AMAIS actuals
14. Budget amendment tracking
15. Budget reports (council-ready format)

### Phase 4: Polish & advanced features
16. VADIM connector (same pattern as AMAIS, different schema)
17. Custom SQL query builder
18. Tangible Capital Asset schedule (PS 3150)
19. Audit trail and activity log views
20. Multi-year comparative reports
21. Period close and roll-forward automation

---

## Items Explicitly Out of Scope

- **No cloud integration** — no AWS, Azure, GCP, no cloud file storage, no SaaS auth
- **No client portal / PBC requests** — this is internal finance software, not auditor-client workflow
- **No XBRL export** — not required for BC municipal reporting
- **No tax software export** — municipalities don't file corporate tax returns
- **No mobile app** — desktop/tablet web browser only
- **No IDEA/analytics integration** — not needed for internal reporting
- **No multi-firm / multi-tenant** — single municipality installation
- **No engagement lockdown** — replaced by period close + sign-off workflow appropriate for internal finance team

---

## Key Decisions & Rationale

**Why FastAPI over Django?** FastAPI's async support matters for concurrent SQL Server queries against AMAIS/VADIM (which can be slow on some installations). Auto-generated OpenAPI docs also make it easy for the finance IT team to understand what the API does.

**Why not ERPNext as a base?** ERPNext's Frappe framework is opinionated and would constrain the ERP connector design. Building on FastAPI gives full control over the SQL connector architecture, which is essential for querying AMAIS and VADIM's specific table structures.

**Why PSAB groups hardcoded into the data model?** BC municipal reporting requirements are stable — PS 1201 has been the standard for years. Hardcoding PSAB structure into the account group model means every calculation and report template can rely on it without complex configuration.

**Why WeasyPrint over ReportLab?** WeasyPrint lets you design statements in CSS/HTML, which is far more maintainable than ReportLab's programmatic PDF layout. Municipal financial statements have complex multi-column layouts that CSS handles well.

**Why SSE over WebSockets for real-time?** For 4–10 users in a local network, SSE is sufficient and dramatically simpler to implement. WebSockets add complexity (connection management, reconnection logic) that isn't justified at this scale.
