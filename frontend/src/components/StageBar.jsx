import { STAGES } from '../runState'
import { Spinner } from './ui'

// Clone → Scan → Parse → Index → Agents → Judge → Done
export default function StageBar({ stage, status }) {
  const current = STAGES.findIndex((s) => s.key === stage)
  const failed = status === 'failed' || status === 'stopped' || status === 'interrupted'

  return (
    <ol className="flex items-center gap-1 overflow-x-auto">
      {STAGES.map((s, i) => {
        const done = i < current || (s.key === 'done' && stage === 'done')
        const active = i === current && stage !== 'done'
        const broke = active && failed
        const cls = broke
          ? 'bg-red-500/15 text-red-300 ring-red-500/40'
          : done
            ? 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/30'
            : active
              ? 'bg-sky-500/15 text-sky-200 ring-sky-400/60 shadow-[0_0_12px_rgba(56,189,248,0.25)]'
              : 'bg-slate-800/40 text-slate-500 ring-slate-700'
        return (
          <li key={s.key} className="flex items-center gap-1">
            <span className={`flex items-center gap-1.5 whitespace-nowrap rounded-md px-2.5 py-1 text-xs font-medium ring-1 transition-all ${cls}`}>
              {broke ? '✕' : done ? '✓' : active ? <Spinner className="h-3 w-3" /> : <span className="opacity-50">{i + 1}</span>}
              {s.label}
            </span>
            {i < STAGES.length - 1 && <span className={`h-px w-4 ${i < current ? 'bg-emerald-500/50' : 'bg-slate-700'}`} />}
          </li>
        )
      })}
    </ol>
  )
}
