# OpenTrail WP

Financial reporting and working paper system for small BC municipal finance teams
(4–10 users, self-hosted on the municipality's own server).

**Stack:** FastAPI (Python 3.12) · PostgreSQL 16 · React 18 + TypeScript (Vite) · nginx ·
Docker Compose. No cloud services, no SaaS auth, no telemetry — see `PLAN.md` for the
design principles and the full build plan.

---

## Quick start

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"                        # SECRET_KEY
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # FERNET_KEY
# edit .env: set POSTGRES_PASSWORD, SECRET_KEY, FERNET_KEY
docker compose up -d --build
```

Open `http://localhost` (or `APP_PORT` from `.env`).

The first start creates the schema and seeds one administrator:

| Username | Password   |
|----------|------------|
| `admin`  | `admin123` |

**Change that password immediately** (top-right menu → Admin → Users), and keep
`SECRET_KEY` and `FERNET_KEY` out of version control. Rotating `FERNET_KEY` makes every
stored ERP password unreadable — re-enter them in Admin → Connectors afterwards.

### Development

```bash
docker compose -f docker-compose.dev.yml up      # backend :8000 with reload, Vite :5173
```

Run the backend test suite (SQLite in-memory; no PostgreSQL needed):

```bash
docker build -f backend/Dockerfile -t opentrail-test ./backend   # or install requirements locally
docker run --rm -v "$PWD/backend:/app" opentrail-test python -m pytest -q
```

`pytest` is not in `requirements.txt` (it is not needed in production); install it
alongside the requirements for local runs. The frontend type-checks and builds with
`npm install && npm run build`.

---

## What it does

| Area | Where | Notes |
|---|---|---|
| Trial balance & COA | Trial Balance, Admin → Mapping Schemes | ERP import (AMAIS/VADIM), CSV import, segment labels, user-defined mapping schemes |
| Journal entries | Journal Entries | Adjusting / reclassifying / elimination / budget-variance entries, post → approve, configurable balance enforcement |
| Working papers | Reports → Working papers | Working trial balance, leadsheets by PSAB group, AJE/RJE schedules, ZIP package |
| Reports | Reports | Report builder (sections → row groups → rows, formula rows, comparative columns), built-in PSAB and LGDE templates, PDF/Excel export |
| SOFI | Reports → SOFI | Supplier payments (>$25k), employee remuneration (>$75k), guarantees |
| Budget | Budget | Department requests, finance review, consolidation, amendments, budget-vs-actual, council report |
| Documents | Documents | Audit-binder folders, versioning, review notes, preparer/reviewer sign-off |
| Period close | Admin → Fiscal Years | Pre-close checks, closing balance snapshot, reopen, fiscal-year roll forward |
| Activity | Activity | Full audit trail with CSV export, live notifications |

### Deliberate deviation from `PLAN.md` §7.3

The plan says the period-close snapshot is "written to `TrialBalanceEntry`". It is
instead written to `period_closes` / `period_close_balances`. `TrialBalanceEntry` rows
hold the **unadjusted** figures as the ERP reported them, and the balance engine
(`app/services/balances.py`) adds posted journal adjustments on top; writing adjusted
closing balances back into the trial balance would double-count every AJE and RJE. The
close snapshot is therefore a separate, immutable record — one row per account with
opening, YTD, period movement, AJE, RJE and closing — which is also what an auditor
should be shown.

---

## Deployment guide

### Host requirements

- Docker Engine with Compose v2, 2 vCPU / 4 GB RAM / 20 GB disk is ample.
- Local network access from finance workstations. No outbound internet is required.
- For HTTPS, terminate TLS at an existing reverse proxy or add a certificate to the
  `proxy` service; the app itself speaks plain HTTP behind nginx.

### Volumes and backups

| Volume | Contents | Back up |
|---|---|---|
| `postgres_data` | all financial data | `docker compose exec db pg_dump -U $POSTGRES_USER $POSTGRES_DB > backup.sql` |
| `documents_data` | uploaded working papers | `docker run --rm -v opentrail-wp_documents_data:/d -v $PWD:/b alpine tar czf /b/documents.tgz -C /d .` |

Back up both together: a database restored without the documents volume has working
paper rows pointing at files that are no longer there. Take the database dump while the
stack is idle, or use `pg_dump` (which is consistent) rather than copying the data
directory.

### ERP connectors (AMAIS / VADIM)

Connector passwords are Fernet-encrypted in the database, so the database alone does not
expose ERP credentials.

**AMAIS** runs on Progress OpenEdge and is read over its SQL Broker via ODBC. The
Progress OpenEdge ODBC driver must be installed **on the host running the backend
container**, and the container needs access to it. Add the driver to the backend image
and expose the driver directory, for example:

```yaml
# docker-compose.override.yml
services:
  backend:
    volumes:
      - /opt/progress/odbc:/opt/progress/odbc:ro
    environment:
      ODBCINI: /etc/odbc.ini
      LD_LIBRARY_PATH: /opt/progress/odbc/lib
```

Then configure the connector in Admin → Connectors with the AMAIS host, port, database
name and credentials, and use **Test connection** before importing. VADIM (SQL Server)
needs no extra driver work — `pymssql` is bundled.

Import order for a new municipality (Admin → Connectors):

1. Configure the connector and test the connection.
2. **Pull COA** — imports the chart of accounts for the ERP fiscal year.
3. **Segment Labels** — name the segments this installation actually uses.
4. **Mapping Schemes** — classify accounts (at minimum a `PSAB` scheme).
5. **Pull trial balance** for the periods you need.

### Live notifications (SSE)

`GET /api/v1/events/stream` keeps a long-lived connection open per signed-in browser.
`EventSource` cannot set an `Authorization` header, so the endpoint also accepts the
access token as a `token` query parameter. That is acceptable for a locally hosted,
single-municipality deployment over a trusted network; if the app is ever exposed
publicly, terminate TLS in front of it and keep the tokens short-lived.

The bundled nginx configuration proxies that path with `proxy_buffering off` and a long
read timeout. If you put another proxy in front of OpenTrail, disable response buffering
for `/api/v1/events/stream` as well, or notifications will arrive in bursts.

### Upgrades

```bash
git pull
docker compose build
docker compose up -d
```

Schema changes are applied on start: the backend entrypoint runs `alembic upgrade head`
and then creates any tables that are still missing, so a fresh install and an upgrade
take the same path. Take a database dump first.

### Operational notes

- **Periods and years are frozen deliberately.** Closing a period snapshots its balances
  and blocks further trial balance edits; closing a year closes its periods in order.
  Corrections go through *reopen* (finance_admin), which is recorded in the activity log.
- **Segregation of duties is enforced**: a reviewer cannot approve a working paper,
  journal entry, or budget request they prepared, and only a `finance_admin` can review
  working papers, force a period close, or reopen one.
- **Everything is audited.** Every mutation writes to `audit_logs` with the user, IP,
  before/after values and a description; passwords and connector secrets are redacted.
- **Optimistic locking.** Trial balance entries, budget requests and journal entries carry
  a `version`; a client that sends a stale version gets `409 Conflict`
  (`X-Conflict-Reason: stale-version`) instead of silently overwriting a colleague's work.

### Roles

| Role | Can |
|---|---|
| `finance_admin` | everything: users, connectors, period close/reopen, roll forward, review sign-off |
| `finance_officer` | day-to-day work: trial balance, journal entries, reports, budget review, document preparation |
| `budget_manager` | submit and track their own department's budget requests |
| `viewer` | read-only access to reports, working papers and statements |
