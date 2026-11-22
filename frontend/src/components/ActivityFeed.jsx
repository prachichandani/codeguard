import { useEffect, useRef } from 'react'
import { AGENTS, formatDuration } from '../runState'
import { ACCENTS, Panel } from './ui'

const TYPE_STYLE = {
  finding: 'text-emerald-300',
  agent_error: 'text-red-300',
  run_failed: 'text-red-300',
  quota_exhausted: 'text-amber-300 font-semibold',
  budget_wait: 'text-amber-300/80',
  retry: 'text-amber-300/80',
  stage: 'text-sky-300',
}

// Live log of everything happening, newest at the bottom
export default function ActivityFeed({ feed }) {
  const bottom = useRef(null)
  useEffect(() => { bottom.current?.scrollIntoView({ block: 'nearest' }) }, [feed.length])

  return (
    <Panel title="Activity" className="flex min-h-0 flex-col">
      <ol className="h-[420px] space-y-0.5 overflow-y-auto p-3 font-mono text-[11px]">
        {feed.map((item, i) => {
          const meta = AGENTS[item.agent]
          const accent = meta ? ACCENTS[meta.accent].text : 'text-slate-400'
          const style = item.type === 'finding' && !item.recorded ? 'text-slate-500' : (TYPE_STYLE[item.type] || 'text-slate-300')
          return (
            <li key={i} className="flex gap-2 leading-relaxed">
              <span className="w-12 shrink-0 text-right text-slate-600">{formatDuration(item.t)}</span>
              {meta ? <span className={`w-20 shrink-0 truncate ${accent}`}>{meta.label}</span> : <span className="w-20 shrink-0 text-slate-500">pipeline</span>}
              <span className={`min-w-0 break-words ${style}`}>{item.text}</span>
            </li>
          )
        })}
        <li ref={bottom} />
      </ol>
    </Panel>
  )
}
