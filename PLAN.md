# OpenTrail WP — Implementation Plan
## BC Municipal Government Financial Reporting & Working Paper System

**Date:** March 2026
**Stack:** Python (FastAPI) + React (TypeScript) + PostgreSQL + Docker Compose
**Target:** Small-town BC local government finance teams (4–10 users, locally hosted)
**Scope:** Financial reporting, working paper preparation, budget management — no cloud dependencies

---

## Design Principles

1. **Local-first, no cloud.** All data stays on municipal servers. No external API calls for core functionality. No SaaS auth providers, no cloud storage, no telemetry.
2. **BC municipal context.** Fiscal year April 1 – March 31. PSAB/PSAS compliance as first-class concern. Not auditor software — this is the finance department's own tool.
3. **SQL connector-native.** VADIM (Tempus Nova, SQL Server) and MAIS are primary data sources. The import model is live SQL queries, not just CSV upload — though CSV/Excel always available as fallback.
4. **Budget workflow built-in.** Department heads submit requests; finance reviews; actuals pulled from VADIM for variance analysis. This is not an afterthought module.
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
│   │   │   ├── account.py
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

BC municipal fiscal year: April 1 – March 31.

**Model:**
```
FiscalYear: id, label (e.g. "2024-25"), start_date, end_date, status (open/closed/locked)
Period: id, fiscal_year_id, period_number (1-12), name, start_date, end_date, is_closed
```

Roll-forward: closing a fiscal year copies account mappings and document structure to the new year. Opening balances = prior year closing balances after adjustments.

---

## Phase 2: Trial Balance Engine

### 2.1 Chart of Accounts & Mapping

The application maintains its own chart of accounts (COA) separate from any source system. GL accounts from VADIM or CSV imports are mapped to this internal COA.

**Models:**
```
AccountGroup: id, fiscal_year_id, group_code, description, psab_category
  (PSAB categories: financial_assets, liabilities, non_financial_assets,
   revenue, expense, accumulated_surplus)

Account: id, fiscal_year_id, gl_code, description, account_group_id,
         normal_balance (debit/credit), is_active

AccountMapping: id, account_id, source_system (vadim/csv/etc), source_gl_code
```

**PSAB groupings built-in:**
- Financial Assets (PS 1201.031)
- Liabilities (PS 1201.032)
- Non-Financial Assets (PS 1201.033)
- Revenue (PS 1201)
- Expenses (by object and function)
- Net Financial Assets / Debt (derived)
- Accumulated Surplus/Deficit (derived)

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

Generic SQL connector using SQLAlchemy with driver-level abstraction.

**Supported drivers:**
| System | Driver | SQLAlchemy URL Pattern |
|---|---|---|
| VADIM (Tempus Nova) | SQL Server via `pymssql` or `pyodbc` | `mssql+pymssql://` |
| MAIS | SQL Server via `pymssql` or `pyodbc` | `mssql+pymssql://` |
| Generic SQL Server | `pymssql` / `pyodbc` | `mssql+pymssql://` |
| PostgreSQL | `psycopg2` | `postgresql+psycopg2://` |
| MySQL/MariaDB | `pymysql` | `mysql+pymysql://` |
| SQLite | built-in | `sqlite:///` |

**Connector Model:**
```
ExternalConnector: id, name, db_type (mssql/postgres/mysql/sqlite),
                   host, port, database_name, username,
                   encrypted_password,  # Fernet-encrypted at rest
                   schema_name,         # e.g. "dbo" for SQL Server
                   is_active, last_tested_at, last_pull_at,
                   created_by_user_id
```

Passwords encrypted using a Fernet key stored as an environment variable (never in the DB unencrypted).

### 3.2 VADIM-Specific Mapping

VADIM (Tempus Nova) common table structure for BC municipalities:

The connector includes a **VADIM profile** with pre-configured query templates targeting known VADIM table names (GL accounts, transaction detail, budget tables). The user selects "VADIM" as the connector type and the query templates are pre-filled — they only need to confirm table/column names match their installation.

Queries exposed:
- **GL Account list** — pull chart of accounts
- **Trial balance by period** — debit/credit totals per account per period
- **GL transaction detail** — line-level transaction drill-down (for supporting schedules)
- **Budget amounts by account/period** — feeds budgeting module

### 3.3 MAIS-Specific Mapping

MAIS integration targets property assessment data relevant to municipal revenue reporting (assessed values, levy calculations). Query templates for common MAIS schemas provided as a starting point — municipalities can customize SQL.

### 3.4 Import Workflow

1. User configures connector (host, credentials, DB name)
2. "Test Connection" verifies connectivity
3. User selects fiscal year and period to pull
4. System executes mapped queries, previews result set
5. User confirms mapping of source GL codes → internal accounts (saved for future pulls)
6. Data written to `TrialBalanceEntry` with `source = connector_id`
7. Pull history logged with row counts and timestamp

### 3.5 Custom Query Support

For advanced users: a **Custom Query** feature lets `finance_admin` users write and save named SQL queries against any configured connector. Results can be materialized into the app as supporting schedule data or displayed in reports. This is deliberately simple — not a full query builder, just a SQL text editor with parameterization support for `{fiscal_year}` and `{period}` tokens.

---

## Phase 4: Journal Entries & Adjustments

### 4.1 Entry Types

Following PSAB requirements (adapted from CWP's model, removing audit-specific types):

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

## Phase 5: Financial Report Generator (PSAB)

### 5.1 PSAB Statement Templates

Built-in templates for BC municipal reporting under PSAB:

| Statement | Standard | Notes |
|---|---|---|
| Statement of Financial Position | PS 1201.031-.033 | Net Financial Assets/Debt as key line |
| Statement of Operations | PS 1201 | Budget vs. Actual required column |
| Statement of Change in Net Financial Assets | PS 1201 | |
| Statement of Cash Flow | PS 2450 | Direct or indirect method |
| Schedule of Segment Disclosure | PS 2700 | Optional, common for larger towns |
| Notes to Financial Statements | Various PS sections | Modular note blocks |
| Tangible Capital Asset Schedule | PS 3150 | By asset class |

### 5.2 Report Designer

Not a general-purpose designer (that's too complex for MVP). Instead:
- Templates are defined as structured JSON configs mapping PSAB line items to account groups
- Finance admin can adjust which account groups roll up to which line item
- Number formatting, comparative columns (current year / prior year / budget) configurable
- Notes: rich text editor per note section with ability to link dynamic values (account balances, calculated figures)

### 5.3 Export

- **PDF** via WeasyPrint (CSS-based, good enough for municipal financial statements)
- **Excel** via openpyxl (for further manipulation, circulation to council)
- **Working papers package** — ZIP of all generated documents for a period

---

## Phase 6: Budgeting Module

This is a key differentiator. CWP has no meaningful budget workflow; this module is built specifically for BC municipal budget processes.

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

Pulls actual YTD figures from the trial balance (sourced from VADIM connector) and compares against approved budget lines.

Report outputs:
- **Budget vs. Actual by Department** — variance $, variance %, traffic-light status
- **Budget vs. Actual by Account Group** — PSAB-aligned summary
- **Multi-year comparison** — current budget / current actual / prior actual / prior budget
- **Variance drill-down** — click a department to see account-level detail

### 6.4 Budget Amendment Tracking

Mid-year budget amendments tracked separately from original budget. Amendment entries logged with approval reference and rationale. Statement of Operations shows: Original Budget | Amended Budget | Actual | Variance.

---

## Phase 7: Document Management

Simplified from CWP's full engagement binder — focused on what a municipal finance team actually needs.

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
| External DB access | SQLAlchemy + pymssql + pyodbc | SQL Server support for VADIM/MAIS, plus generic SQL |
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
2. Period/fiscal year management
3. Chart of accounts and PSAB account mapping
4. CSV/Excel trial balance import
5. VADIM SQL connector (SQL Server)
6. Generic SQL connector framework

### Phase 2: Working paper functionality
7. Journal entries (adjusting and reclassifying)
8. Auto-generated leadsheets and working trial balance
9. PSAB financial statement templates (SFP, SO, SCNFA, SCF)
10. PDF and Excel export
11. Document management (file upload, folders, sign-off)

### Phase 3: Budget module
12. Budget year setup and department request portal
13. Budget-to-actual comparison with VADIM data
14. Budget amendment tracking
15. Budget reports (council-ready format)

### Phase 4: Polish & advanced features
16. MAIS connector
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

**Why FastAPI over Django?** FastAPI's async support matters for concurrent SQL Server queries against VADIM (which can be slow on some installations). Auto-generated OpenAPI docs also make it easy for the finance IT team to understand what the API does.

**Why not ERPNext as a base?** ERPNext's Frappe framework is opinionated and would constrain VADIM connector design. Building on FastAPI gives full control over the SQL connector architecture, which is essential for VADIM's specific table structure.

**Why PSAB groups hardcoded into the data model?** BC municipal reporting requirements are stable — PS 1201 has been the standard for years. Hardcoding PSAB structure into the account group model means every calculation and report template can rely on it without complex configuration.

**Why WeasyPrint over ReportLab?** WeasyPrint lets you design statements in CSS/HTML, which is far more maintainable than ReportLab's programmatic PDF layout. Municipal financial statements have complex multi-column layouts that CSS handles well.

**Why SSE over WebSockets for real-time?** For 4–10 users in a local network, SSE is sufficient and dramatically simpler to implement. WebSockets add complexity (connection management, reconnection logic) that isn't justified at this scale.
