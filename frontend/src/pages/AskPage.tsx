import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ask, citationHref } from '../api/chat'
import type { Citation } from '../api/chat'

interface Turn {
  question: string
  answer?: string
  grounded?: boolean
  citations?: Citation[]
}

export default function AskPage({ workspaceId }: { workspaceId: number }) {
  const [turns, setTurns] = useState<Turn[]>([])
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const conversation = useRef<number | undefined>(undefined)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const q = question.trim()
    if (!q) return
    setBusy(true)
    setError(null)
    setQuestion('')
    setTurns((t) => [...t, { question: q }])
    try {
      const res = await ask(workspaceId, q, conversation.current)
      conversation.current = res.conversation_id
      setTurns((t) =>
        t.map((turn, i) =>
          i === t.length - 1
            ? { ...turn, answer: res.answer, grounded: res.grounded, citations: res.citations }
            : turn,
        ),
      )
    } catch {
      setError('Something went wrong. Try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">Ask your documents</h1>
      <ul className="flex flex-col gap-4" aria-label="Conversation">
        {turns.length === 0 && (
          <li className="text-sm text-slate-500">
            Try: “What is the warranty period?” Answers cite the page they came from; if the
            documents do not say, the assistant says so instead of guessing.
          </li>
        )}
        {turns.map((t, i) => (
          <li key={i} className="flex flex-col gap-2">
            <p className="self-end rounded-xl bg-indigo-600 px-3 py-2 text-sm">{t.question}</p>
            {t.answer === undefined ? (
              <p className="text-sm text-slate-500">Searching…</p>
            ) : (
              <div
                className={`rounded-xl border p-3 text-sm ${t.grounded ? 'border-slate-700 bg-slate-900' : 'border-amber-900 bg-amber-950/30 text-amber-100'}`}
                data-grounded={t.grounded}
              >
                <p>{t.answer}</p>
                {t.citations && t.citations.length > 0 && (
                  <ul className="mt-2 flex flex-wrap gap-2" aria-label="Citations">
                    {t.citations.map((c, k) => (
                      <li key={k}>
                        <a
                          href={citationHref(c)}
                          title={c.quote}
                          className="rounded-full border border-slate-600 px-2 py-0.5 text-xs hover:bg-slate-800"
                        >
                          {c.document} · p.{c.page}
                        </a>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
      {error && (
        <p role="alert" className="text-sm text-rose-400">
          {error}
        </p>
      )}
      <form onSubmit={submit} className="flex gap-2">
        <input
          aria-label="Question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about your documents…"
          className="flex-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm outline-none focus:border-indigo-400"
        />
        <button
          disabled={busy}
          className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium disabled:opacity-50"
        >
          Ask
        </button>
      </form>
    </section>
  )
}
