import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { useAuthStore } from '@/store/auth'
import { LoginPage } from '@/pages/Login'
import { DashboardPage } from '@/pages/Dashboard'
import { TrialBalancePage } from '@/pages/TrialBalance'
import { JournalEntriesPage } from '@/pages/JournalEntries'
import { ReportsPage } from '@/pages/Reports'
import { BudgetPage } from '@/pages/Budget'
import { DocumentsPage } from '@/pages/Documents'
import { AdminPage } from '@/pages/Admin'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated())
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const hasRole = useAuthStore((s) => s.hasRole(['finance_admin']))
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated())
  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (!hasRole) return <Navigate to="/" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary>
        <Routes>
          <Route path="/login" element={<LoginPage />} />

          <Route
            element={
              <ProtectedRoute>
                <AppShell />
              </ProtectedRoute>
            }
          >
            <Route index element={<DashboardPage />} />
            <Route path="trial-balance" element={<TrialBalancePage />} />
            <Route path="journal-entries" element={<JournalEntriesPage />} />
            <Route path="reports" element={<ReportsPage />} />
            <Route path="budget" element={<BudgetPage />} />
            <Route path="documents" element={<DocumentsPage />} />
            <Route
              path="admin"
              element={
                <AdminRoute>
                  <AdminPage />
                </AdminRoute>
              }
            />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </ErrorBoundary>
    </BrowserRouter>
  )
}
