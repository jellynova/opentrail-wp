export interface User {
  id: number
  username: string
  email: string
  role: 'finance_admin' | 'finance_officer' | 'budget_manager' | 'viewer'
  department: string | null
  is_active: boolean
  created_at: string
}

export interface FiscalYear {
  id: number
  label: string
  start_date: string
  end_date: string
  status: 'open' | 'closed' | 'locked'
}

export interface Period {
  id: number
  fiscal_year_id: number
  period_number: number
  name: string
  start_date: string
  end_date: string
  is_closed: boolean
}

export interface Account {
  id: number
  fiscal_year_id: number
  acct_fmtd: string
  description: string | null
  acct_type: string | null
  record_class: string | null
  dept_code: string | null
  fund_code: string | null
  total_lvl: number | null
  normal_balance: 'debit' | 'credit' | null
  is_active: boolean
  source_system: 'amais' | 'vadim' | 'csv' | 'manual' | null
}

export interface MappingScheme {
  id: number
  name: string
  description: string | null
  is_active: boolean
}

export interface AccountClassification {
  id: number
  account_id: number
  scheme_id: number
  classification_value: string
  sort_order: number | null
}

export interface TrialBalanceEntry {
  id: number
  period_id: number
  account_id: number
  account?: Account
  opening_debit: string
  opening_credit: string
  period_debit: string
  period_credit: string
  ytd_debit: string
  ytd_credit: string
  source: string
  imported_at: string
}

export interface JournalEntry {
  id: number
  period_id: number
  entry_date: string
  reference: string | null
  description: string | null
  entry_type: 'adjusting' | 'reclassifying' | 'elimination' | 'budget_variance'
  prepared_by_user_id: number
  reviewed_by_user_id: number | null
  status: 'draft' | 'posted' | 'approved'
  created_at: string
  lines?: JournalLine[]
}

export interface JournalLine {
  id: number
  journal_entry_id: number
  account_id: number
  account?: Account
  debit: string
  credit: string
  description: string | null
  gl_reference: string | null
}

export interface ExternalConnector {
  id: number
  name: string
  system_type: 'amais' | 'vadim' | 'mssql' | 'postgres' | 'mysql' | 'sqlite'
  host: string | null
  port: number | null
  database_name: string | null
  username: string | null
  schema_name: string | null
  is_active: boolean
  last_tested_at: string | null
  last_pull_at: string | null
}

export interface BudgetYear {
  id: number
  fiscal_year_id: number
  label: string
  submission_deadline: string | null
  status: 'setup' | 'open' | 'under_review' | 'approved' | 'adopted'
  instructions_text: string | null
}

export interface BudgetRequest {
  id: number
  budget_year_id: number
  account_id: number
  account?: Account
  department: string
  prior_year_actual: string | null
  prior_year_budget: string | null
  proposed_amount: string | null
  justification_text: string | null
  submitted_by_user_id: number
  status: 'draft' | 'submitted' | 'approved' | 'modified' | 'rejected'
  approved_amount: string | null
}

export interface WorkingPaper {
  id: number
  fiscal_year_id: number
  folder_path: string
  filename: string
  display_name: string
  file_type: 'pdf' | 'xlsx' | 'docx' | 'img' | 'other'
  file_size: number
  uploaded_by_user_id: number
  uploaded_at: string
  description: string | null
  version_number: number
}

export interface Report {
  id: number
  name: string
  description: string | null
  report_type: string
  is_template: boolean
  is_protected: boolean
  definition: object
  fiscal_year_id: number | null
  created_at: string
}

export interface AuthTokens {
  access_token: string
  token_type: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  size: number
}

export interface SegmentLabel {
  id: number
  segment_key: string
  label: string
  is_active: boolean
}
