import { useAuth } from './auth/AuthContext'
import { useHashLocation } from './hooks/useHashRoute'
import AgentPage from './pages/AgentPage'
import AnalyticsPage from './pages/AnalyticsPage'
import AskPage from './pages/AskPage'
import AdminPage from './pages/AdminPage'
import DocumentPage from './pages/DocumentPage'
import DocumentsPage from './pages/DocumentsPage'
import EvaluationPage from './pages/EvaluationPage'
import UniversePage from './pages/UniversePage'
import DemoBanner from './components/DemoBanner'
import Logo from './components/Logo'
import { useLiquidGlass } from './hooks/useLiquidGlass'
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
  useLiquidGlass('.ds-nav', Boolean(me))
  if (loading)
    return (
      <div className="relative min-h-screen">
        <div className="ds-ambient" aria-hidden="true" />
        <p className="relative z-10 p-6 text-slate-400">Loading…</p>
      </div>
    )
  if (!me) return <LoginPage />

  const workspaceId = me.workspaces[0]?.workspace_id
  const [section, arg] = route
  const initials = (me.user.name || me.user.email)
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join('')
  const link = (href: string, label: string, active: boolean) => (
    <a
      href={href}
      aria-current={active ? 'page' : undefined}
      className={`rounded-lg px-3 py-1.5 whitespace-nowrap ${
        active
          ? 'bg-white/10 font-medium text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]'
          : 'text-slate-400 hover:bg-white/5 hover:text-white'
      }`}
    >
      {label}
    </a>
  )

  return (
    <div className="relative min-h-screen">
      <div className="ds-ambient" aria-hidden="true" />
      <div className="relative z-10 mx-auto flex min-h-screen max-w-6xl flex-col gap-6 px-4 pt-4 pb-16 sm:px-6">
        <DemoBanner />
        <header className="sticky top-3 z-40">
          <nav aria-label="Main" className="ds-nav ds-glass rounded-2xl px-2.5 py-2 text-sm">
            <div className="ds-content flex items-center gap-1 overflow-x-auto">
              <a
                href="#/documents"
                className="mr-2 flex shrink-0 items-center gap-2.5 rounded-lg px-1.5 py-1"
              >
                <Logo size={26} />
                <span className="ds-wordmark text-[15px] text-white">DocSense</span>
              </a>
              <span className="mr-1 h-5 w-px shrink-0 bg-white/10" aria-hidden="true" />
              {link('#/documents', 'Documents', !section || section === 'documents')}
              {link('#/analytics', 'Analytics', section === 'analytics')}
              {link('#/spending', 'Spending AI', section === 'spending')}
              {link('#/universe', 'Universe', section === 'universe')}
              {link('#/ask', 'Ask', section === 'ask')}
              {link('#/evaluation', 'Evaluation', section === 'evaluation')}
              {me.user.is_staff && link('#/admin', 'Admin', section === 'admin')}
              {link('#/settings', 'Settings', section === 'settings')}
              <span
                title={me.user.email}
                className="ml-auto flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-caramel to-cocoa text-xs font-semibold text-cream shadow-[inset_0_1px_0_rgba(255,253,249,0.25)]"
              >
                {initials}
              </span>
            </div>
          </nav>
        </header>
        <main className="flex flex-col gap-5">
          {section === 'settings' ? (
            <SettingsPage />
          ) : section === 'admin' && me.user.is_staff ? (
            <AdminPage />
          ) : section === 'evaluation' ? (
            <EvaluationPage />
          ) : section === 'universe' ? (
            <UniversePage workspaceId={workspaceId} />
          ) : section === 'spending' ? (
            <AgentPage workspaceId={workspaceId} />
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
        </main>
      </div>
    </div>
  )
}
