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
  /** Optimistic-locking token: echo it back on update or the save is rejected with 409. */
  version: number
  updated_at?: string | null
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
  version?: number
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
  /** Optimistic-locking token: echo it back when editing, or the save is rejected with 409. */
  version: number
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

export type SignOffState = 'draft' | 'prepared' | 'approved' | 'reapproval_required'

export interface WorkingPaper {
  id: number
  root_id: number
  fiscal_year_id: number
  folder_path: string
  filename: string
  display_name: string
  file_type: 'pdf' | 'xlsx' | 'docx' | 'img' | 'other'
  file_size: number
  uploaded_by_user_id: number
  uploaded_by_username: string | null
  uploaded_at: string
  description: string | null
  version_number: number
  version_count: number
  parent_version_id: number | null
  superseded_at: string | null
  sign_off_state: SignOffState
  requires_reapproval: boolean
  preparer_signed_off_by_user_id: number | null
  preparer_signed_off_by_username: string | null
  preparer_signed_off_at: string | null
  reviewer_signed_off_by_user_id: number | null
  reviewer_signed_off_by_username: string | null
  reviewer_signed_off_at: string | null
}

export interface FolderNode {
  path: string
  label: string
  fiscal_year_id: number | null
  fiscal_year_status: string | null
  document_count: number
  unsigned_count: number
  children: FolderNode[]
}

export interface WPAnnotation {
  id: number
  working_paper_id: number
  user_id: number
  username: string | null
  text: string
  created_at: string
  is_resolved: boolean
  resolved_by_user_id: number | null
  resolved_by_username: string | null
  resolved_at: string | null
}

export interface AuditLogEntry {
  id: number
  user_id: number | null
  username: string | null
  action: string
  resource_type: string
  resource_id: number | null
  old_values: Record<string, unknown> | null
  new_values: Record<string, unknown> | null
  ip_address: string | null
  timestamp: string
  description: string
}

export interface AuditLogPage {
  items: AuditLogEntry[]
  limit: number
  offset: number
  has_more: boolean
}

export interface ActivityNotification {
  id: number
  timestamp: string
  action: string
  resource_type: string
  resource_id: number | null
  message: string
  user_id: number | null
  username: string | null
}

export interface UnpostedEntry {
  id: number
  reference: string | null
  status: string
  entry_type: string
}

export interface UnsignedDocument {
  document_id: number
  display_name: string
  folder_path: string
  state: SignOffState
}

export interface PreCloseCheck {
  period_id: number
  fiscal_year_id: number
  already_closed: boolean
  ready: boolean
  unposted_journal_entries: UnpostedEntry[]
  unsigned_documents: UnsignedDocument[]
}

export interface PeriodCloseBalance {
  account_id: number
  acct_fmtd: string
  opening: string
  ytd_debit: string
  ytd_credit: string
  period_debit: string
  period_credit: string
  aje_debit: string
  aje_credit: string
  rje_debit: string
  rje_credit: string
  closing: string
}

export interface PeriodClose {
  id: number
  period_id: number
  period_name: string | null
  fiscal_year_label: string | null
  closed_by_user_id: number
  closed_by_username: string | null
  closed_at: string
  notes: string | null
  journal_entry_count: number
  account_count: number
  total_debits: string
  total_credits: string
  is_balanced: boolean
  overrides: string | null
  reopened_at: string | null
  reopened_by_user_id: number | null
  balances: PeriodCloseBalance[]
}

export interface RollForwardResult {
  fiscal_year: FiscalYear
  periods_created: number
  accounts_copied: number
  account_mappings_copied: number
  classifications_copied: number
  opening_balances_posted: number
  opening_debits: string
  opening_credits: string
  balanced: boolean
  net_surplus: string
  surplus_account: string | null
  warnings: string[]
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

/** PS 3150 tangible capital asset schedule (PLAN §5.2). */
export interface TcaLine {
  id: number
  fiscal_year_id: number
  asset_class: string
  sort_order: number
  notes: string | null
  cost_opening: string
  cost_additions: string
  cost_disposals: string
  cost_closing: string
  amort_opening: string
  amort_expense: string
  amort_disposals: string
  amort_closing: string
  nbv_opening: string
  nbv_closing: string
  source: string
}

/** Editable amounts for one asset class (the derived figures are computed server-side). */
export interface TcaLineInput {
  asset_class: string
  cost_opening: string
  cost_additions: string
  cost_disposals: string
  amort_opening: string
  amort_expense: string
  amort_disposals: string
  notes?: string | null
}

export interface TcaReconciliation {
  available: boolean
  reason?: string
  gl_cost?: string
  gl_accumulated_amortization?: string
  schedule_cost?: string
  schedule_accumulated_amortization?: string
  cost_difference?: string
  amortization_difference?: string
  agrees?: boolean
}

export interface TcaScheduleReport extends ReportOutput {
  layout: 'continuity' | 'summary'
  reconciliation: TcaReconciliation
  line_count: number
}

export interface TcaRollForwardResult {
  applied: number
  created: number
  prior_year: string | null
  warnings: string[]
}
