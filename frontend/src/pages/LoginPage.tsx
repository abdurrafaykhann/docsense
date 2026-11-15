import { useState } from 'react'
import type { FormEvent } from 'react'
import { errorMessage } from '../api/client'
import DemoBanner from '../components/DemoBanner'
import Logo from '../components/Logo'
import { useLiquidGlass } from '../hooks/useLiquidGlass'
import { useAuth } from '../auth/AuthContext'

const errorText = (e: unknown) => errorMessage(e)

const FEATURES = [
  {
    title: 'Reads photos and PDFs',
    text: 'OCR plus a layout model find the vendor, totals and line items.',
    dot: '#6b4f3a',
  },
  {
    title: 'Checks the maths',
    text: 'Line totals, 18% GST and NTN/STRN formats are verified in code.',
    dot: '#71835e',
  },
  {
    title: 'Answers with sources',
    text: 'Every answer cites the page it came from, or says it does not know.',
    dot: '#a67c5b',
  },
  {
    title: 'Spots problems',
    text: 'Duplicates, price creep and unusual amounts are flagged for you.',
    dot: '#c08a35',
  },
]

export default function LoginPage() {
  const { login, signup } = useAuth()
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [workspace, setWorkspace] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  useLiquidGlass('.ds-login', true, { tilt: true, tiltFactor: 2 })

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (mode === 'login') await login(email, password)
      else await signup(email, password, name, workspace)
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  const input =
    'w-full rounded-xl border border-line bg-cream px-3.5 py-2.5 text-sm text-espresso placeholder:text-slate-500 outline-none focus:border-indigo-400'

  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="ds-ambient" aria-hidden="true" />
      <main className="relative z-10 mx-auto grid min-h-screen max-w-6xl items-center gap-12 px-6 py-12 lg:grid-cols-[1.15fr_0.85fr] lg:gap-16">
        <section className="flex flex-col gap-8">
          <div className="flex items-center gap-3">
            <Logo size={34} />
            <span className="ds-wordmark text-xl text-white">DocSense</span>
          </div>
          <div className="flex flex-col gap-4">
            <p className="ds-eyebrow text-slate-500">
              Document intelligence for invoices and receipts
            </p>
            <h1 className="max-w-[16ch] text-4xl leading-[1.05] font-semibold sm:text-5xl">
              Invoices in. Checked, structured data out.
            </h1>
            <p className="max-w-[52ch] text-base leading-relaxed text-slate-400">
              Upload a PDF or a phone photo. DocSense reads it, finds the layout, fills a strict
              schema and checks the result with rules written in code, so you only review what it is
              unsure about.
            </p>
          </div>
          <ul className="grid max-w-xl gap-3 text-sm sm:grid-cols-2">
            {FEATURES.map((f) => (
              <li
                key={f.title}
                className="rounded-xl border border-white/[0.07] bg-white/[0.03] p-3.5"
              >
                <p className="flex items-center gap-2 font-medium text-slate-100">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: f.dot }} />
                  {f.title}
                </p>
                <p className="mt-1 text-slate-400">{f.text}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="ds-login ds-glass w-full rounded-3xl p-7 sm:p-8">
          <div className="ds-content flex flex-col gap-5">
            <div>
              <h2 className="text-xl font-semibold text-white">
                {mode === 'login' ? 'Sign in' : 'Create your workspace'}
              </h2>
              <p className="mt-1 text-sm text-slate-400">
                {mode === 'login'
                  ? 'Welcome back. Your documents are waiting.'
                  : 'Start with an empty workspace for your documents.'}
              </p>
            </div>
            <DemoBanner withLogin />
            <form onSubmit={submit} className="flex flex-col gap-3" aria-label={mode}>
              {mode === 'signup' && (
                <>
                  <input
                    className={input}
                    placeholder="Your name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                  <input
                    className={input}
                    placeholder="Workspace name"
                    value={workspace}
                    onChange={(e) => setWorkspace(e.target.value)}
                  />
                </>
              )}
              <input
                className={input}
                type="email"
                placeholder="Email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <input
                className={input}
                type="password"
                placeholder="Password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              {error && (
                <p role="alert" className="text-sm text-rose-400">
                  {error}
                </p>
              )}
              <button
                disabled={busy}
                className="mt-1 rounded-xl bg-indigo-500 px-3 py-2.5 font-medium text-white disabled:opacity-50"
              >
                {mode === 'login' ? 'Log in' : 'Create account'}
              </button>
            </form>
            <button
              type="button"
              className="text-sm text-slate-400 hover:text-white"
              onClick={() => setMode(mode === 'login' ? 'signup' : 'login')}
            >
              {mode === 'login' ? 'Need an account? Sign up' : 'Have an account? Log in'}
            </button>
          </div>
        </section>
      </main>
    </div>
  )
}
