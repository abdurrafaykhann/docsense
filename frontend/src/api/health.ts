export interface Health {
  status: 'ok' | 'degraded'
  db: boolean
  service: string
}

export async function fetchHealth(signal?: AbortSignal): Promise<Health> {
  const res = await fetch('/api/v1/health/', { signal })
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`)
  return res.json()
}
