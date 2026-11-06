import { useAuth } from './auth/AuthContext'
import { useHashRoute } from './hooks/useHashRoute'
import DocumentPage from './pages/DocumentPage'
import DocumentsPage from './pages/DocumentsPage'
import EvaluationPage from './pages/EvaluationPage'
import LoginPage from './pages/LoginPage'
import SettingsPage from './pages/SettingsPage'

export default function App() {
  const { me, loading } = useAuth()
  const route = useHashRoute()
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
        {link('#/evaluation', 'Evaluation', section === 'evaluation')}
        {link('#/settings', 'Settings', section === 'settings')}
      </nav>
      {section === 'settings' ? (
        <SettingsPage />
      ) : section === 'evaluation' ? (
        <EvaluationPage />
      ) : section === 'documents' && arg ? (
        <DocumentPage workspaceId={workspaceId} id={Number(arg)} />
      ) : (
        <DocumentsPage workspaceId={workspaceId} />
      )}
    </div>
  )
}
