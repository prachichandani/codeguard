import { useState } from 'react'
import { AGENTS } from '../runState'
import FindingDetail from './FindingDetail'
import { Panel, SeverityBadge } from './ui'

const SEVERITY_ORDER = { high: 0, medium: 1, low: 2 }
const bySeverity = (a, b) => (SEVERITY_ORDER[a.severity] ?? 3) - (SEVERITY_ORDER[b.severity] ?? 3)

function AgentTag({ name }) {
  const meta = AGENTS[name]
  return <span className="text-[11px] text-slate-500">{meta ? `${meta.icon} ${meta.label}` : name}</span>
}

function Location({ f }) {
  if (!f.file_path) return null
  const path = String(f.file_path).replaceAll('\\', '/')
  return <span className="font-mono text-[11px] text-slate-400">{path}{f.start_line ? `:${f.start_line}` : ''}</span>
}

// Before the judge: findings as agents report them. After: the judge's verdicts.
export default function FindingsList({ state }) {
  const [selected, setSelected] = useState(null)
  const { report, findings } = state

  if (!report) {
    const recorded = findings.filter((f) => f.recorded)
    const refused = findings.filter((f) => !f.recorded)
    return (
      <Panel title={`Findings reported · ${recorded.length}`}
             right={<span className="text-[11px] text-slate-500">verified by the judge at the end</span>}>
        <ul className="divide-y divide-slate-800">
          {recorded.map((f) => (
            <li key={f.key} className="animate-slide-in flex items-center gap-3 px-4 py-2.5">
              <SeverityBadge severity={f.severity} />
              <span className="flex-1 truncate text-sm text-slate-100">{f.title}</span>
              <Location f={f} />
              <AgentTag name={f.agent} />
            </li>
          ))}
          {refused.map((f) => (
            <li key={f.key} className="flex items-center gap-3 px-4 py-2 text-slate-500">
              <span className="text-[10px] font-bold uppercase">refused</span>
              <span className="flex-1 truncate text-xs line-through">{f.title}</span>
              <span className="truncate text-[11px]" title={f.reason}>{f.reason}</span>
            </li>
          ))}
          {!findings.length && (
            <li className="px-4 py-8 text-center text-sm text-slate-500">
              {state.status === 'running' ? 'No findings yet. Agents report problems as they confirm them.' : 'No findings.'}
            </li>
          )}
        </ul>
      </Panel>
    )
  }

  const accepted = [...report.accepted].sort(bySeverity)
  const rejected = report.rejected
  return (
    <>
      <Panel title={`Accepted findings · ${accepted.length}`}>
        <ul className="divide-y divide-slate-800">
          {accepted.map((f) => (
            <li key={f.id}>
              <button onClick={() => setSelected(f)}
                      className="animate-slide-in flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-slate-800/50">
                <span className="text-emerald-400">✓</span>
                <SeverityBadge severity={f.severity} />
                <span className="flex-1 truncate text-sm font-medium text-slate-100">{f.title}</span>
                {f.unreviewed && (
                  <span title={f.judge_reason} className="rounded bg-slate-500/20 px-1.5 py-0.5 text-[10px] text-slate-300">not reviewed by judge</span>
                )}
                {f.quote_mismatch && (
                  <span title="The agent's quote was inaccurate; verified against the real code instead"
                        className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-300">verified on real code</span>
                )}
                <Location f={f} />
                <AgentTag name={f.specialist} />
                {f.also_reported_by?.length > 0 && <span className="text-[10px] text-slate-500">+{f.also_reported_by.length}</span>}
                <span className="text-slate-600">›</span>
              </button>
            </li>
          ))}
          {!accepted.length && <li className="px-4 py-8 text-center text-sm text-slate-500">No findings were accepted.</li>}
        </ul>
      </Panel>

      {rejected.length > 0 && (
        <Panel title={`Rejected · ${rejected.length}`} className="mt-4">
          <ul className="divide-y divide-slate-800">
            {rejected.map((f) => (
              <li key={f.id}>
                <button onClick={() => setSelected(f)}
                        className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-slate-400 transition hover:bg-slate-800/50">
                  <span className="text-red-400/80">✕</span>
                  <span className="flex-1 truncate text-sm">{f.title}</span>
                  <span className="max-w-[40%] truncate text-[11px] text-slate-500" title={f.reason}>
                    {f.rejected_by}: {f.reason}
                  </span>
                  <AgentTag name={f.specialist} />
                </button>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      {selected && <FindingDetail finding={selected} onClose={() => setSelected(null)} />}
    </>
  )
}
