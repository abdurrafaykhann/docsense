const ACCESS = 'ds_access'
const REFRESH = 'ds_refresh'

export const tokens = {
  get access() {
    return localStorage.getItem(ACCESS)
  },
  get refresh() {
    return localStorage.getItem(REFRESH)
  },
  set(access: string, refresh?: string) {
    localStorage.setItem(ACCESS, access)
    if (refresh) localStorage.setItem(REFRESH, refresh)
  },
  clear() {
    localStorage.removeItem(ACCESS)
    localStorage.removeItem(REFRESH)
  },
}

export class ApiError extends Error {
  status: number
  body: unknown
  constructor(status: number, body: unknown) {
    super(`API error ${status}`)
    this.status = status
    this.body = body
  }
}

async function refreshAccess(): Promise<boolean> {
  const refresh = tokens.refresh
  if (!refresh) return false
  const res = await fetch('/api/v1/auth/refresh/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  })
  if (!res.ok) return false
  tokens.set((await res.json()).access)
  return true
}

export async function api<T>(
  path: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const doFetch = () => {
    const headers = new Headers(init.headers)
    if (init.json !== undefined) headers.set('Content-Type', 'application/json')
    if (tokens.access) headers.set('Authorization', `Bearer ${tokens.access}`)
    return fetch(`/api/v1${path}`, {
      ...init,
      headers,
      body: init.json !== undefined ? JSON.stringify(init.json) : init.body,
    })
  }
  let res = await doFetch()
  if (res.status === 401 && (await refreshAccess())) res = await doFetch()
  if (res.status === 204) return undefined as T
  const body = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, body)
  return body as T
}
