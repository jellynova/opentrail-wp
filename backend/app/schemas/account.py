from typing import Optional, List
from pydantic import BaseModel


class AccountCreate(BaseModel):
    fiscal_year_id: int
    acct_fmtd: str
    description: Optional[str] = None
    acct_type: Optional[str] = None
    record_class: Optional[str] = None
    capital_acct: Optional[bool] = None
    dept_code: Optional[str] = None
    fund_code: Optional[str] = None
    stat: Optional[str] = None
    total_lvl: Optional[int] = None
    total_lvl_cde: Optional[str] = None
    rev_exp_rpt: Optional[str] = None
    object_str: Optional[str] = None
    project_str: Optional[str] = None
    seg1: Optional[int] = None
    seg2: Optional[int] = None
    seg3: Optional[int] = None
    seg4: Optional[int] = None
    seg5: Optional[int] = None
    seg6: Optional[int] = None
    seg7: Optional[int] = None
    seg8: Optional[int] = None
    seg9: Optional[int] = None
    seg10: Optional[int] = None
    seg1_descr: Optional[str] = None
    seg2_descr: Optional[str] = None
    seg3_descr: Optional[str] = None
    seg4_descr: Optional[str] = None
    seg5_descr: Optional[str] = None
    seg6_descr: Optional[str] = None
    seg7_descr: Optional[str] = None
    seg8_descr: Optional[str] = None
    seg9_descr: Optional[str] = None
    seg10_descr: Optional[str] = None
    normal_balance: Optional[str] = None
    is_active: bool = True
    source_system: Optional[str] = None
    connector_id: Optional[int] = None


class AccountUpdate(BaseModel):
    description: Optional[str] = None
    acct_type: Optional[str] = None
    record_class: Optional[str] = None
    capital_acct: Optional[bool] = None
    dept_code: Optional[str] = None
    fund_code: Optional[str] = None
    stat: Optional[str] = None
    normal_balance: Optional[str] = None
    is_active: Optional[bool] = None


class AccountResponse(BaseModel):
    id: int
    fiscal_year_id: int
    acct_fmtd: str
    description: Optional[str]
    acct_type: Optional[str]
    record_class: Optional[str]
    capital_acct: Optional[bool]
    dept_code: Optional[str]
    fund_code: Optional[str]
    stat: Optional[str]
    total_lvl: Optional[int]
    total_lvl_cde: Optional[str]
    rev_exp_rpt: Optional[str]
    object_str: Optional[str]
    project_str: Optional[str]
    seg1: Optional[int]
    seg2: Optional[int]
    seg3: Optional[int]
    seg4: Optional[int]
    seg5: Optional[int]
    seg6: Optional[int]
    seg7: Optional[int]
    seg8: Optional[int]
    seg9: Optional[int]
    seg10: Optional[int]
    seg1_descr: Optional[str]
    seg2_descr: Optional[str]
    seg3_descr: Optional[str]
    seg4_descr: Optional[str]
    seg5_descr: Optional[str]
    seg6_descr: Optional[str]
    seg7_descr: Optional[str]
    seg8_descr: Optional[str]
    seg9_descr: Optional[str]
    seg10_descr: Optional[str]
    normal_balance: Optional[str]
    is_active: bool
    source_system: Optional[str]
    connector_id: Optional[int]

    model_config = {"from_attributes": True}


class MappingSchemeCreate(BaseModel):
    name: str
    description: Optional[str] = None


class MappingSchemeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class MappingSchemeResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_active: bool

    model_config = {"from_attributes": True}


class AccountClassificationItem(BaseModel):
    scheme_id: int
    classification_value: str
    sort_order: Optional[int] = None


class AccountClassificationUpdate(BaseModel):
    classifications: List[AccountClassificationItem]


class AccountClassificationResponse(BaseModel):
    id: int
    account_id: int
    scheme_id: int
    classification_value: str
    sort_order: Optional[int]

    model_config = {"from_attributes": True}


class SegmentDefinitionUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class SegmentDefinitionResponse(BaseModel):
    id: int
    connector_id: Optional[int]
    segment_number: int
    label: str
    description: Optional[str]
    is_active: bool

    model_config = {"from_attributes": True}
