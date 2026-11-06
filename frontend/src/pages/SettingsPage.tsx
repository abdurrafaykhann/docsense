import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ApiKeyRow, Member, Usage } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import WebhooksSection from '../components/WebhooksSection'

const card = 'rounded-xl border border-slate-800 bg-slate-900 p-4'

export default function SettingsPage() {
  const { me, logout } = useAuth()
  const [wsId, setWsId] = useState<number | null>(me?.workspaces[0]?.workspace_id ?? null)
  const [members, setMembers] = useState<Member[]>([])
  const [keys, setKeys] = useState<ApiKeyRow[]>([])
  const [usage, setUsage] = useState<Usage | null>(null)
  const [newKey, setNewKey] = useState<string | null>(null)
  const [keyName, setKeyName] = useState('')

  const membership = me?.workspaces.find((w) => w.workspace_id === wsId)
  const isOwner = membership?.role === 'owner'

  const load = useCallback(async () => {
    if (wsId == null) return
    const base = `/workspaces/${wsId}`
    setUsage(await api<Usage>(`${base}/usage/`))
    setMembers(await api<Member[]>(`${base}/members/`))
    setKeys(isOwner ? await api<ApiKeyRow[]>(`${base}/api-keys/`) : [])
  }, [wsId, isOwner])

  useEffect(() => {
    void load()
  }, [load])

  async function createKey() {
    const row = await api<ApiKeyRow>(`/workspaces/${wsId}/api-keys/`, {
      method: 'POST',
      json: { name: keyName || 'default' },
    })
    setNewKey(row.key ?? null)
    setKeyName('')
    await load()
  }

  async function revoke(id: number) {
    await api(`/workspaces/${wsId}/api-keys/${id}/`, { method: 'DELETE' })
    await load()
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-5 p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Settings</h1>
        <div className="flex items-center gap-3 text-sm">
          <span className="text-slate-400">{me?.user.email}</span>
          <button onClick={logout} className="underline">
            Log out
          </button>
        </div>
      </header>

      <select
        aria-label="Workspace"
        className="w-fit rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
        value={wsId ?? ''}
        onChange={(e) => setWsId(Number(e.target.value))}
      >
        {me?.workspaces.map((w) => (
          <option key={w.workspace_id} value={w.workspace_id}>
            {w.name} ({w.role})
          </option>
        ))}
      </select>

      {usage && (
        <section className={card} aria-label="Usage">
          <h2 className="mb-2 font-semibold">Usage today</h2>
          <p className="text-sm text-slate-300">
            Uploads: {usage.today.uploads} / {usage.limits.daily_uploads} · API requests:{' '}
            {usage.today.api_requests} · Max file: {usage.limits.max_upload_mb} MB
          </p>
        </section>
      )}

      <section className={card} aria-label="Members">
        <h2 className="mb-2 font-semibold">Members</h2>
        <ul className="text-sm">
          {members.map((m) => (
            <li key={m.id} className="flex justify-between py-1">
              <span>{m.email}</span>
              <span className="text-slate-400">{m.role}</span>
            </li>
          ))}
        </ul>
      </section>

      {isOwner && (
        <section className={card} aria-label="API keys">
          <h2 className="mb-2 font-semibold">API keys</h2>
          {newKey && (
            <p
              role="status"
              className="mb-3 break-all rounded bg-emerald-950 p-2 text-sm text-emerald-300"
            >
              Copy now, it will not be shown again: <code>{newKey}</code>
            </p>
          )}
          <ul className="mb-3 text-sm">
            {keys.map((k) => (
              <li key={k.id} className="flex items-center justify-between py-1">
                <span>
                  {k.name} <code className="text-slate-500">ds_{k.prefix}…</code>
                  {k.revoked && <em className="ml-2 text-rose-400">revoked</em>}
                </span>
                {!k.revoked && (
                  <button onClick={() => revoke(k.id)} className="text-rose-400 underline">
                    Revoke
                  </button>
                )}
              </li>
            ))}
          </ul>
          <div className="flex gap-2">
            <input
              aria-label="Key name"
              placeholder="Key name (e.g. n8n)"
              value={keyName}
              onChange={(e) => setKeyName(e.target.value)}
              className="flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            />
            <button
              onClick={createKey}
              className="rounded-lg bg-indigo-500 px-3 py-2 text-sm font-medium"
            >
              Create key
            </button>
          </div>
        </section>
      )}
      {isOwner && wsId != null && <WebhooksSection workspaceId={wsId} />}
    </main>
  )
}
