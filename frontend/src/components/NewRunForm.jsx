import { useState } from 'react'
import { startRun } from '../api'
import { Spinner } from './ui'

export default function NewRunForm({ onStarted, busy }) {
  const [url, setUrl] = useState('https://github.com/anxolerd/dvpwa')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  async function submit(e) {
    e.preventDefault()
    setSubmitting(true); setError(null)
    try {
      const { id } = await startRun(url)
      onStarted(id)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-1 items-center gap-2">
      <div className="relative max-w-xl flex-1">
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://github.com/owner/repo"
               className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 font-mono text-sm text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-sky-500 focus:ring-2 focus:ring-sky-500/20" />
        {error && <p className="absolute left-0 top-full mt-1 text-xs text-red-300">{error}</p>}
      </div>
      <button type="submit" disabled={submitting || busy || !url.trim()}
              title={busy ? 'An audit is already running' : ''}
              className="flex items-center gap-2 rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-40">
        {submitting ? <Spinner /> : '▶'} Run audit
      </button>
    </form>
  )
}
