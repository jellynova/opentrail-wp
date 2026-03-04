from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel


class ConnectorCreate(BaseModel):
    name: str
    system_type: str  # amais / vadim / mssql / postgres / mysql / sqlite
    host: Optional[str] = None
    port: Optional[int] = None
    database_name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None  # plain text — encrypted before storage
    schema_name: Optional[str] = None


class ConnectorUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    database_name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    schema_name: Optional[str] = None
    is_active: Optional[bool] = None


class ConnectorResponse(BaseModel):
    id: int
    name: str
    system_type: str
    host: Optional[str]
    port: Optional[int]
    database_name: Optional[str]
    username: Optional[str]
    schema_name: Optional[str]
    is_active: bool
    last_tested_at: Optional[datetime]
    last_pull_at: Optional[datetime]
    created_by_user_id: int

    model_config = {"from_attributes": True}


class ConnectorTestResult(BaseModel):
    success: bool
    message: str
    tables: Optional[List[str]] = None


class PullRequest(BaseModel):
    fiscal_year: int
    period: Optional[int] = None  # required for trial balance
    period_from: Optional[int] = None  # for transactions
    period_to: Optional[int] = None  # for transactions


class CustomQueryRequest(BaseModel):
    sql: str
    params: Optional[Dict[str, Any]] = None


class PullResult(BaseModel):
    records_processed: int
    records_created: int
    records_updated: int
    errors: List[str] = []
