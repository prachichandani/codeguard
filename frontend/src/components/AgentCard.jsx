import { AGENTS, describeTool } from '../runState'
import { ACCENTS, Spinner } from './ui'

const TOOL_ICONS = {
  text_search: '🔎', semantic_search: '🧠', symbol_search: '📄', graph_traversal: '🕸️', report_finding: '🚩',
}

function Activity({ agent, now, live }) {
  const { status, activity } = agent
  if (status === 'waiting') {
    const left = live && agent.waitUntil ? Math.max(0, Math.ceil(agent.waitUntil - now)) : Math.round(agent.waitSeconds || 0)
    return (
      <div className="flex items-center gap-2 text-amber-300/90">
        <span className="text-base">⏳</span>
        <span>Waiting for token budget{left ? ` · ${left}s` : ''}</span>
      </div>
    )
  }
  if (status === 'done') return <div className="text-emerald-300/90">✓ Finished</div>
  if (status === 'error') return <div className="truncate text-red-300/90" title={agent.error}>✕ Stopped: {agent.error || 'error'}</div>
  if (status === 'reporting') return <div className="flex items-center gap-2 text-sky-200"><Spinner /> Writing final report…</div>
  if (activity?.kind === 'tool') {
    return (
      <div className="flex items-center gap-2 truncate font-mono text-[13px] text-slate-100" title={describeTool(activity.tool, activity.args)}>
        <span>{TOOL_ICONS[activity.tool] || '🔧'}</span>
        <span className="truncate">{describeTool(activity.tool, activity.args)}</span>
      </div>
    )
  }
  if (status === 'thinking') return <div className="flex items-center gap-2 text-slate-300"><Spinner /> Thinking…</div>
  return <div className="text-slate-500">Waiting to start</div>
}

export default function AgentCard({ agent, now, live }) {
  const meta = AGENTS[agent.name] || { label: agent.name, icon: '🤖', accent: 'slate' }
  const c = ACCENTS[meta.accent] || ACCENTS.slate
  const pct = agent.of ? Math.min(100, (agent.step / agent.of) * 100) : 0
  const busy = ['thinking', 'reporting', 'waiting'].includes(agent.status) && live

  return (
    <div className={`flex flex-col rounded-xl border bg-slate-900/70 p-4 transition-all ${c.border} ${busy ? `ring-1 ${c.ring}` : ''}`}>
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <span className={`flex h-8 w-8 items-center justify-center rounded-lg text-base ${c.bg}`}>{meta.icon}</span>
          <div>
            <div className={`text-sm font-semibold ${c.text}`}>{meta.label}</div>
            <div className="text-[11px] text-slate-500">specialist</div>
          </div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold leading-none text-slate-100">{agent.findings}</div>
          <div className="text-[11px] text-slate-500">finding{agent.findings === 1 ? '' : 's'}</div>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between text-[11px] text-slate-400">
        <span>Step {agent.step || 0} / {agent.of}</span>
        {agent.refused > 0 && <span className="text-slate-500">{agent.refused} refused</span>}
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-800">
        <div className={`h-full rounded-full transition-all duration-500 ${c.bar}`} style={{ width: `${pct}%` }} />
      </div>

      <div className="mt-3 min-h-[1.5rem] text-sm">
        <Activity agent={agent} now={now} live={live} />
      </div>

      <ul className="mt-3 space-y-1 border-t border-slate-800 pt-2">
        {agent.calls.slice(-4).reverse().map((call, i) => (
          <li key={`${call.t}-${i}`} className={`truncate font-mono text-[11px] ${i === 0 ? 'animate-slide-in text-slate-300' : 'text-slate-500'}`}
              title={call.summary || call.error || ''}>
            {TOOL_ICONS[call.tool] || '🔧'} {describeTool(call.tool, call.args)}
          </li>
        ))}
        {!agent.calls.length && <li className="text-[11px] text-slate-600">No searches yet</li>}
      </ul>
    </div>
  )
}
