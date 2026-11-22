import { formatDuration } from '../runState'
import { Panel } from './ui'

// Groq's tokens-per-minute budget: how much was left at the last call, and how
// much time the agents spent waiting for it (the main reason audits are slow).
export default function TokenGauge({ tokens }) {
  const { remaining, limit, calls, prompt, completion, waited } = tokens
  const used = remaining == null ? 0 : Math.max(0, limit - remaining)
  const pct = Math.min(100, (used / limit) * 100)
  const barColor = pct > 85 ? 'bg-red-400' : pct > 60 ? 'bg-amber-400' : 'bg-emerald-400'

  return (
    <Panel title="Groq token budget">
      <div className="space-y-4 p-4">
        <div>
          <div className="flex items-baseline justify-between text-xs text-slate-400">
            <span>Used this minute</span>
            <span className="font-mono text-slate-200">{remaining == null ? '–' : `${used.toLocaleString()} / ${limit.toLocaleString()}`}</span>
          </div>
          <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-800">
            <div className={`h-full rounded-full transition-all duration-500 ${barColor}`} style={{ width: `${pct}%` }} />
          </div>
        </div>
        <dl className="grid grid-cols-2 gap-3 text-xs">
          <Stat label="LLM calls" value={calls} />
          <Stat label="Tokens sent" value={prompt.toLocaleString()} />
          <Stat label="Tokens received" value={completion.toLocaleString()} />
          <Stat label="Time waiting" value={formatDuration(waited)} hint="summed across agents" />
        </dl>
      </div>
    </Panel>
  )
}

function Stat({ label, value, hint }) {
  return (
    <div className="rounded-lg bg-slate-800/40 px-3 py-2">
      <dt className="text-slate-500">{label}</dt>
      <dd className="mt-0.5 font-mono text-sm text-slate-100">{value}</dd>
      {hint && <dd className="text-[10px] text-slate-500">{hint}</dd>}
    </div>
  )
}
