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
  total_debit?: string
  total_credit?: string
  is_balanced?: boolean
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
  supporting_notes: string | null
  submitted_by_user_id: number
  submitted_at: string | null
  reviewed_by_user_id: number | null
  review_comment: string | null
  status: 'draft' | 'submitted' | 'approved' | 'modified' | 'rejected'
  approved_amount: string | null
}

export type TrafficLight = 'green' | 'amber' | 'red'

export interface BudgetVarianceRow {
  account_id: number
  acct_fmtd: string
  description: string | null
  department: string
  classification: string | null
  kind: 'revenue' | 'expense'
  original_budget: string
  amended_budget: string
  ytd_actual: string
  variance: string
  variance_pct: string | null
  percent_used: string | null
  status: TrafficLight
}

export interface BudgetVarianceGroup {
  group: string
  kind: 'revenue' | 'expense'
  original_budget: string
  amended_budget: string
  ytd_actual: string
  variance: string
  variance_pct: string | null
  status: TrafficLight
  accounts: number
}

export interface BudgetVarianceReport {
  budget_year_id: number
  budget_year: string
  fiscal_year: string | null
  through_period: number
  percent_of_year: string | null
  group_by: string
  department: string | null
  rows: BudgetVarianceRow[]
  groups: BudgetVarianceGroup[] | null
  total_revenue_budget: string
  total_revenue_actual: string
  total_expense_budget: string
  total_expense_actual: string
}

export interface BudgetAmendment {
  id: number
  budget_year_id: number
  amendment_number: number
  approval_reference: string | null
  rationale: string | null
  status: 'draft' | 'approved'
  approved_date: string | null
  created_by_user_id: number
  approved_by_user_id: number | null
  created_at: string
  lines: { id: number; account_id: number; amount: string; description: string | null }[]
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
  definition: Record<string, unknown>
  fiscal_year_id: number | null
  created_at: string
  updated_at?: string
}

/** Common tabular output of the report engine, working papers, budget and SOFI schedules. */
export interface ReportOutputRow {
  id?: string
  type?: string
  label: string
  level: number
  style: { bold?: boolean; italic?: boolean; underline?: 'single' | 'double' }
  values: Record<string, string | number | null>
  text?: Record<string, string>
  acct_fmtd?: string
}

export interface ReportOutput {
  title: string
  subtitle: string | null
  organization?: string | null
  number_format?: { decimals?: number; currency_symbol?: string }
  columns: { key: string; label: string; percent?: boolean }[]
  text_columns?: { key: string; label: string }[]
  rows: ReportOutputRow[]
  warnings?: string[]
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
