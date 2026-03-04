import { Link } from 'react-router-dom'
import { Calendar, PenLine, BarChart3, Folder, Table2, FileText, ArrowRight } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { PageHeader } from '@/components/shared/PageHeader'
import { useFiscalYears } from '@/hooks/useFiscalYears'
import { useAllJournalEntries } from '@/hooks/useJournalEntries'
import { useBudgetYears } from '@/hooks/useBudget'
import { formatDate, formatCurrency } from '@/lib/utils'
import { useAuthStore } from '@/store/auth'

function FiscalYearStatusBadge({ status }: { status: string }) {
  const variants: Record<string, 'success' | 'warning' | 'secondary'> = {
    open: 'success',
    closed: 'secondary',
    locked: 'warning',
  }
  return <Badge variant={variants[status] ?? 'secondary'}>{status}</Badge>
}

function BudgetYearStatusBadge({ status }: { status: string }) {
  const variants: Record<string, 'success' | 'info' | 'warning' | 'secondary'> = {
    setup: 'secondary',
    open: 'info',
    under_review: 'warning',
    approved: 'success',
    adopted: 'success',
  }
  return <Badge variant={variants[status] ?? 'secondary'}>{status.replace('_', ' ')}</Badge>
}

const quickLinks = [
  { to: '/trial-balance', icon: Table2, label: 'Trial Balance', desc: 'View and import TB data' },
  { to: '/journal-entries', icon: PenLine, label: 'Journal Entries', desc: 'Create and post entries' },
  { to: '/reports', icon: FileText, label: 'Reports', desc: 'Financial statements' },
  { to: '/budget', icon: BarChart3, label: 'Budget', desc: 'Budget requests and actuals' },
  { to: '/documents', icon: Folder, label: 'Documents', desc: 'Working papers and files' },
]

export function DashboardPage() {
  const { user } = useAuthStore()
  const { data: fiscalYears, isLoading: fyLoading } = useFiscalYears()
  const { data: recentEntries, isLoading: jeLoading } = useAllJournalEntries({ limit: 5 })
  const { data: budgetYears, isLoading: byLoading } = useBudgetYears()

  const currentFY = fiscalYears?.find((fy) => fy.status === 'open')
  const activeBudgetYear = budgetYears?.find(
    (by) => by.status === 'open' || by.status === 'under_review'
  )

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Welcome back, ${user?.username ?? 'User'}`}
        description="OpenTrail WP — BC Municipal Financial Reporting & Working Paper System"
      />

      {/* Summary cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {/* Fiscal Year Card */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Current Fiscal Year</CardTitle>
            <Calendar className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {fyLoading ? (
              <LoadingSpinner size="sm" />
            ) : currentFY ? (
              <div className="space-y-1">
                <p className="text-2xl font-bold">{currentFY.label}</p>
                <div className="flex items-center gap-2">
                  <FiscalYearStatusBadge status={currentFY.status} />
                  <span className="text-xs text-muted-foreground">
                    {formatDate(currentFY.start_date)} – {formatDate(currentFY.end_date)}
                  </span>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No open fiscal year</p>
            )}
          </CardContent>
        </Card>

        {/* Journal Entries Card */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Recent Journal Entries</CardTitle>
            <PenLine className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {jeLoading ? (
              <LoadingSpinner size="sm" />
            ) : recentEntries && recentEntries.length > 0 ? (
              <div className="space-y-2">
                <p className="text-2xl font-bold">{recentEntries.length}</p>
                <p className="text-xs text-muted-foreground">entries (recent)</p>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No journal entries</p>
            )}
          </CardContent>
        </Card>

        {/* Budget Card */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Budget Year</CardTitle>
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {byLoading ? (
              <LoadingSpinner size="sm" />
            ) : activeBudgetYear ? (
              <div className="space-y-1">
                <p className="text-2xl font-bold">{activeBudgetYear.label}</p>
                <div className="flex items-center gap-2">
                  <BudgetYearStatusBadge status={activeBudgetYear.status} />
                  {activeBudgetYear.submission_deadline && (
                    <span className="text-xs text-muted-foreground">
                      Due {formatDate(activeBudgetYear.submission_deadline)}
                    </span>
                  )}
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No active budget year</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent Journal Entries */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Recent Journal Entries</CardTitle>
            <CardDescription>Last 5 entries across all periods</CardDescription>
          </div>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/journal-entries">
              View all <ArrowRight className="ml-1 h-3 w-3" />
            </Link>
          </Button>
        </CardHeader>
        <CardContent>
          {jeLoading ? (
            <LoadingSpinner fullPage />
          ) : recentEntries && recentEntries.length > 0 ? (
            <div className="space-y-2">
              {recentEntries.map((entry) => (
                <div
                  key={entry.id}
                  className="flex items-center justify-between rounded-md border px-4 py-2"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">
                      {entry.reference ?? `Entry #${entry.id}`}
                    </p>
                    <p className="text-xs text-muted-foreground truncate">
                      {entry.description ?? entry.entry_type} · {formatDate(entry.entry_date)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0 ml-4">
                    <Badge
                      variant={
                        entry.status === 'approved'
                          ? 'success'
                          : entry.status === 'posted'
                          ? 'info'
                          : 'secondary'
                      }
                    >
                      {entry.status}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="py-4 text-center text-sm text-muted-foreground">
              No journal entries found.{' '}
              <Link to="/journal-entries" className="text-primary hover:underline">
                Create one
              </Link>
            </p>
          )}
        </CardContent>
      </Card>

      {/* Quick Links */}
      <div>
        <h2 className="mb-3 text-sm font-semibold text-muted-foreground uppercase tracking-wide">
          Quick Access
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {quickLinks.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className="flex flex-col items-start gap-2 rounded-lg border bg-card p-4 hover:bg-accent transition-colors"
            >
              <link.icon className="h-5 w-5 text-primary" />
              <div>
                <p className="text-sm font-medium">{link.label}</p>
                <p className="text-xs text-muted-foreground">{link.desc}</p>
              </div>
            </Link>
          ))}
        </div>
      </div>

      {/* Fiscal Years list */}
      {fiscalYears && fiscalYears.length > 1 && (
        <Card>
          <CardHeader>
            <CardTitle>All Fiscal Years</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {fiscalYears.map((fy) => (
                <div
                  key={fy.id}
                  className="flex items-center justify-between rounded-md border px-4 py-2"
                >
                  <span className="text-sm font-medium">{fy.label}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground">
                      {formatDate(fy.start_date)} – {formatDate(fy.end_date)}
                    </span>
                    <FiscalYearStatusBadge status={fy.status} />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// Suppress unused import warning — formatCurrency imported for potential future use
void formatCurrency
