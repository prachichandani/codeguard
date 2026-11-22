import { formatDuration } from '../runState'
import { StatusBadge } from './ui'

function when(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function RunHistory({ runs, selectedId, onSelect }) {
  return (
    <nav className="flex h-full flex-col">
      <h2 className="px-4 pb-2 pt-4 text-xs font-semibold uppercase tracking-wider text-slate-500">Runs</h2>
      <ul className="flex-1 space-y-1 overflow-y-auto px-2 pb-4">
        {runs.map((r) => {
          const duration = r.ended && r.started ? formatDuration(r.ended - r.started) : null
          return (
            <li key={r.id}>
              <button onClick={() => onSelect(r.id)}
                      className={`w-full rounded-lg px-3 py-2.5 text-left transition ${r.id === selectedId ? 'bg-slate-800 ring-1 ring-slate-700' : 'hover:bg-slate-800/50'}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium text-slate-200">{r.repo}</span>
                  <StatusBadge status={r.status} />
                </div>
                <div className="mt-1 flex items-center justify-between text-[11px] text-slate-500">
                  <span>{when(r.started)}{duration ? ` · ${duration}` : ''}</span>
                  <span>
                    {r.quota_exhausted && <span className="mr-1.5 text-amber-400/90" title="Groq's daily token limit was hit; results incomplete">⚠ quota</span>}
                    {r.accepted != null && <span className="text-emerald-400/80">{r.accepted} accepted</span>}
                  </span>
                </div>
              </button>
            </li>
          )
        })}
        {!runs.length && <li className="px-3 py-6 text-center text-xs text-slate-600">No runs yet</li>}
      </ul>
    </nav>
  )
}
