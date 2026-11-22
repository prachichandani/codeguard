import { formatDuration } from '../runState'
import { StatusBadge } from './ui'

export default function RunHeader({ state, meta, elapsed, live, replaying, onReplay, onStopReplay, onStop, stopping }) {
  const status = replaying ? 'running' : (meta?.status || state.status)
  const accepted = state.report?.accepted.length
  const canReplay = !live && !replaying && state.lastTs

  return (
    <div className="flex flex-wrap items-center gap-4">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-3">
          <h1 className="truncate text-xl font-semibold text-slate-100">{state.repo || meta?.repo || '…'}</h1>
          <StatusBadge status={status} />
          {replaying && <span className="rounded-full bg-violet-500/15 px-2 py-0.5 text-xs font-medium text-violet-300">Replay ×12</span>}
        </div>
        <a href={state.url || meta?.url} target="_blank" rel="noreferrer" className="text-xs text-slate-500 hover:text-slate-300">
          {state.url || meta?.url}
        </a>
      </div>

      <dl className="flex gap-6 text-right">
        <Metric label="Elapsed" value={formatDuration(elapsed)} />
        {state.stats.files != null && <Metric label="Files" value={state.stats.files} />}
        {state.stats.entities != null && <Metric label="Functions" value={state.stats.entities} />}
        {accepted != null && <Metric label="Accepted" value={accepted} highlight />}
      </dl>

      <div className="flex gap-2">
        {live && (
          <button onClick={onStop} disabled={stopping}
                  className="rounded-lg border border-red-500/40 px-3 py-1.5 text-sm text-red-300 transition hover:bg-red-500/10 disabled:opacity-50">
            {stopping ? 'Stopping…' : 'Stop'}
          </button>
        )}
        {canReplay && (
          <button onClick={onReplay} className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-300 transition hover:bg-slate-800">
            ▶ Replay
          </button>
        )}
        {replaying && (
          <button onClick={onStopReplay} className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-300 transition hover:bg-slate-800">
            Skip to end
          </button>
        )}
      </div>
    </div>
  )
}

function Metric({ label, value, highlight }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wider text-slate-500">{label}</dt>
      <dd className={`font-mono text-lg ${highlight ? 'text-emerald-300' : 'text-slate-100'}`}>{value}</dd>
    </div>
  )
}
