import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { api, tokens } from '../api/client'
import type { Me } from '../api/types'

interface AuthState {
  me: Me | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  signup: (email: string, password: string, name: string, workspaceName: string) => Promise<void>
  logout: () => void
}

const Ctx = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(Boolean(tokens.access))

  const loadMe = useCallback(async () => {
    try {
      setMe(await api<Me>('/me/'))
    } catch {
      tokens.clear()
      setMe(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (tokens.access) void loadMe()
  }, [loadMe])

  const value = useMemo<AuthState>(
    () => ({
      me,
      loading,
      async login(email, password) {
        const t = await api<{ access: string; refresh: string }>('/auth/login/', {
          method: 'POST',
          json: { email, password },
        })
        tokens.set(t.access, t.refresh)
        await loadMe()
      },
      async signup(email, password, name, workspace_name) {
        const t = await api<{ access: string; refresh: string }>('/auth/signup/', {
          method: 'POST',
          json: { email, password, name, workspace_name },
        })
        tokens.set(t.access, t.refresh)
        await loadMe()
      },
      logout() {
        tokens.clear()
        setMe(null)
      },
    }),
    [me, loading, loadMe],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAuth outside AuthProvider')
  return ctx
}
