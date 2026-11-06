import { useAuth } from './auth/AuthContext'
import LoginPage from './pages/LoginPage'
import SettingsPage from './pages/SettingsPage'

export default function App() {
  const { me, loading } = useAuth()
  if (loading) return <p className="p-6 text-slate-400">Loading…</p>
  return me ? <SettingsPage /> : <LoginPage />
}
