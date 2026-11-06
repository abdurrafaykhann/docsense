import { useAuth } from './auth/AuthContext'
import { useHashLocation } from './hooks/useHashRoute'
import AnalyticsPage from './pages/AnalyticsPage'
import AskPage from './pages/AskPage'
import AdminPage from './pages/AdminPage'
import DocumentPage from './pages/DocumentPage'
import DocumentsPage from './pages/DocumentsPage'
import EvaluationPage from './pages/EvaluationPage'
import LoginPage from './pages/LoginPage'
import SettingsPage from './pages/SettingsPage'

type Box = [number, number, number, number]

function parseBox(v: string | null): Box | null {
  const n = v?.split(',').map(Number)
  return n && n.length === 4 && n.every(Number.isFinite) ? (n as Box) : null
}

export default function App() {
  const { me, loading } = useAuth()
  const { parts: route, query } = useHashLocation()
  if (loading) return <p className="p-6 text-slate-400">Loading…</p>
  if (!me) return <LoginPage />

  const workspaceId = me.workspaces[0]?.workspace_id
  const [section, arg] = route
  const link = (href: string, label: string, active: boolean) => (
    <a
      href={href}
      className={active ? 'font-semibold text-white' : 'text-slate-400 hover:text-white'}
    >
      {label}
    </a>
  )

  return (
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col gap-5 p-6">
      <nav className="flex items-center gap-5 border-b border-slate-800 pb-3 text-sm">
        <strong className="text-lg">DocSense</strong>
        {link('#/documents', 'Documents', !section || section === 'documents')}
        {link('#/analytics', 'Analytics', section === 'analytics')}
        {link('#/ask', 'Ask', section === 'ask')}
        {link('#/evaluation', 'Evaluation', section === 'evaluation')}
        {me.user.is_staff && link('#/admin', 'Admin', section === 'admin')}
        {link('#/settings', 'Settings', section === 'settings')}
      </nav>
      {section === 'settings' ? (
        <SettingsPage />
      ) : section === 'admin' && me.user.is_staff ? (
        <AdminPage />
      ) : section === 'evaluation' ? (
        <EvaluationPage />
      ) : section === 'analytics' ? (
        <AnalyticsPage workspaceId={workspaceId} />
      ) : section === 'ask' ? (
        <AskPage workspaceId={workspaceId} />
      ) : section === 'documents' && arg ? (
        <DocumentPage
          key={`${arg}-${query.get('page')}-${query.get('hl')}`}
          workspaceId={workspaceId}
          id={Number(arg)}
          initialPage={Number(query.get('page') ?? 1)}
          highlight={parseBox(query.get('hl'))}
        />
      ) : (
        <DocumentsPage workspaceId={workspaceId} />
      )}
    </div>
  )
}
