"""
SQL connector service for pulling data from external ERP systems.

Supports:
  - AMAIS (Progress OpenEdge via pyodbc)
  - VADIM / SQL Server (via pymssql or pyodbc)
  - PostgreSQL, MySQL, SQLite via SQLAlchemy

Passwords are Fernet-encrypted in the database. Decrypt before connecting.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet
from app.core.config import settings
from app.models.connector import ExternalConnector

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def _decrypt_password(encrypted: Optional[str]) -> Optional[str]:
    """Decrypt a Fernet-encrypted connector password."""
    if not encrypted:
        return None
    f = Fernet(settings.FERNET_KEY.encode() if isinstance(settings.FERNET_KEY, str) else settings.FERNET_KEY)
    return f.decrypt(encrypted.encode()).decode()


def encrypt_password(plain: str) -> str:
    """Encrypt a plain-text password for storage."""
    f = Fernet(settings.FERNET_KEY.encode() if isinstance(settings.FERNET_KEY, str) else settings.FERNET_KEY)
    return f.encrypt(plain.encode()).decode()


# ---------------------------------------------------------------------------
# AMAIS (Progress OpenEdge via pyodbc)
# ---------------------------------------------------------------------------

AMAIS_COA_QUERY = """
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
WHERE m."fisc-yr" = ?
ORDER BY m."acct-fmtd"
"""

AMAIS_TRIAL_BALANCE_QUERY = """
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
WHERE p."fisc-yr" = ?
  AND p."rec-type" = 'P'
ORDER BY p."acct-fmtd", p."fisc-prd"
"""

AMAIS_BUDGET_QUERY = """
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
WHERE b."fisc-yr" = ?
ORDER BY b."acct-fmtd", b."fisc-prd", b."rec-type"
"""

AMAIS_TRANSACTIONS_QUERY = """
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
WHERE t."fisc-yr" = ?
  AND t."fisc-prd" BETWEEN ? AND ?
ORDER BY t."object-str", t."primary-date"
"""


def _amais_conn_str(connector: ExternalConnector, password: Optional[str]) -> str:
    """Build AMAIS Progress OpenEdge ODBC connection string."""
    driver_version = "12.2"  # common installed version; override via schema_name field if needed
    if connector.schema_name and connector.schema_name.startswith("driver="):
        # Allow overriding driver version via schema_name field
        driver_version = connector.schema_name.split("=", 1)[1].strip()
    return (
        f"DRIVER={{Progress OpenEdge {driver_version} driver}};"
        f"HOST={connector.host};"
        f"PORT={connector.port};"
        f"DB={connector.database_name};"
        f"UID={connector.username};"
        f"PWD={password or ''};"
    )


def _rows_to_dicts(cursor) -> List[Dict[str, Any]]:
    """Convert pyodbc cursor results to a list of dicts."""
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _amais_connect(connector: ExternalConnector):
    """Open a raw pyodbc connection to AMAIS."""
    import pyodbc  # type: ignore

    password = _decrypt_password(connector.encrypted_password)
    conn_str = _amais_conn_str(connector, password)
    return pyodbc.connect(conn_str, timeout=30)


# ---------------------------------------------------------------------------
# Generic SQLAlchemy connector (vadim/mssql/postgres/mysql/sqlite)
# ---------------------------------------------------------------------------

def _sqlalchemy_url(connector: ExternalConnector, password: Optional[str]) -> str:
    """Build a SQLAlchemy URL for non-AMAIS connectors."""
    st = connector.system_type
    host = connector.host or "localhost"
    port = connector.port
    db = connector.database_name or ""
    user = connector.username or ""
    pw = password or ""

    if st in ("vadim", "mssql"):
        port_str = f":{port}" if port else ""
        return f"mssql+pymssql://{user}:{pw}@{host}{port_str}/{db}"
    elif st == "postgres":
        port_str = f":{port}" if port else ":5432"
        return f"postgresql+psycopg2://{user}:{pw}@{host}{port_str}/{db}"
    elif st == "mysql":
        port_str = f":{port}" if port else ":3306"
        return f"mysql+pymysql://{user}:{pw}@{host}{port_str}/{db}"
    elif st == "sqlite":
        return f"sqlite:///{db}"
    else:
        raise ValueError(f"Unknown system_type: {st}")


def _sqlalchemy_connect(connector: ExternalConnector):
    """Open a SQLAlchemy connection for non-AMAIS connectors."""
    from sqlalchemy import create_engine, text  # type: ignore

    password = _decrypt_password(connector.encrypted_password)
    url = _sqlalchemy_url(connector, password)
    engine = create_engine(url, pool_pre_ping=True)
    return engine


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def test_connection(connector: ExternalConnector) -> Dict[str, Any]:
    """
    Test the connector and return a list of visible table names.
    Returns {"success": bool, "message": str, "tables": [...]}
    """
    try:
        if connector.system_type == "amais":
            conn = _amais_connect(connector)
            cursor = conn.cursor()
            cursor.execute("SELECT TABNAME FROM SYSTABLES WHERE OWNER = 'PUB' ORDER BY TABNAME")
            tables = [row[0] for row in cursor.fetchall()]
            conn.close()
        else:
            engine = _sqlalchemy_connect(connector)
            from sqlalchemy import inspect as sa_inspect

            insp = sa_inspect(engine)
            schema = connector.schema_name or None
            tables = insp.get_table_names(schema=schema)
            engine.dispose()

        return {"success": True, "message": f"Connection successful. {len(tables)} tables found.", "tables": tables}
    except Exception as exc:
        logger.error("Connector test failed for %s: %s", connector.name, exc)
        return {"success": False, "message": str(exc), "tables": None}


def pull_coa(connector: ExternalConnector, fiscal_year: int) -> List[Dict[str, Any]]:
    """
    Pull chart of accounts from AMAIS for a given fiscal year.
    Returns a list of dicts ready to upsert into the accounts table.
    """
    if connector.system_type != "amais":
        raise NotImplementedError(f"pull_coa is only implemented for AMAIS; got {connector.system_type}")

    conn = _amais_connect(connector)
    try:
        cursor = conn.cursor()
        cursor.execute(AMAIS_COA_QUERY, (fiscal_year,))
        return _rows_to_dicts(cursor)
    finally:
        conn.close()


def pull_trial_balance(
    connector: ExternalConnector, fiscal_year: int, period: int
) -> List[Dict[str, Any]]:
    """
    Pull all posted trial balance rows from AMAIS for the given fiscal year.
    The caller filters by period using the fisc_prd field.
    Returns raw rows — the service layer aggregates into TB entries.
    """
    if connector.system_type != "amais":
        raise NotImplementedError(
            f"pull_trial_balance is only implemented for AMAIS; got {connector.system_type}"
        )

    conn = _amais_connect(connector)
    try:
        cursor = conn.cursor()
        cursor.execute(AMAIS_TRIAL_BALANCE_QUERY, (fiscal_year,))
        all_rows = _rows_to_dicts(cursor)
        # Filter to the specific period
        return [r for r in all_rows if r.get("fisc_prd") == period]
    finally:
        conn.close()


def pull_budget(connector: ExternalConnector, fiscal_year: int) -> List[Dict[str, Any]]:
    """
    Pull budget rows from AMAIS gl-bud for the given fiscal year.
    """
    if connector.system_type != "amais":
        raise NotImplementedError(f"pull_budget is only implemented for AMAIS; got {connector.system_type}")

    conn = _amais_connect(connector)
    try:
        cursor = conn.cursor()
        cursor.execute(AMAIS_BUDGET_QUERY, (fiscal_year,))
        return _rows_to_dicts(cursor)
    finally:
        conn.close()


def pull_transactions(
    connector: ExternalConnector,
    fiscal_year: int,
    period_from: int,
    period_to: int,
) -> List[Dict[str, Any]]:
    """
    Pull GL transaction detail from AMAIS gl-trn.
    """
    if connector.system_type != "amais":
        raise NotImplementedError(
            f"pull_transactions is only implemented for AMAIS; got {connector.system_type}"
        )

    conn = _amais_connect(connector)
    try:
        cursor = conn.cursor()
        cursor.execute(AMAIS_TRANSACTIONS_QUERY, (fiscal_year, period_from, period_to))
        return _rows_to_dicts(cursor)
    finally:
        conn.close()


def execute_custom_query(
    connector: ExternalConnector,
    sql: str,
    params: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Execute an arbitrary read-only SQL query against the connector.
    Only SELECT statements are permitted; raises ValueError otherwise.
    """
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT"):
        raise ValueError("Only SELECT queries are permitted via execute_custom_query")

    if connector.system_type == "amais":
        conn = _amais_connect(connector)
        try:
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, list(params.values()))
            else:
                cursor.execute(sql)
            return _rows_to_dicts(cursor)
        finally:
            conn.close()
    else:
        engine = _sqlalchemy_connect(connector)
        from sqlalchemy import text as sa_text

        try:
            with engine.connect() as conn:
                result = conn.execute(sa_text(sql), params or {})
                columns = list(result.keys())
                return [dict(zip(columns, row)) for row in result.fetchall()]
        finally:
            engine.dispose()
