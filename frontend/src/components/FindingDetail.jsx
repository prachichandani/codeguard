import { useEffect } from 'react'
import { AGENTS } from '../runState'
import { SeverityBadge } from './ui'

// Everything about one judged finding: the agent's claim, its quoted evidence,
// the code the judge actually saw (cited lines marked ">"), and the verdict.
export default function FindingDetail({ finding: f, onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const accepted = !f.rejected_by
  const agent = AGENTS[f.specialist]
  const path = String(f.file_path || '').replaceAll('\\', '/')

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-6 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-3xl rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <header className="flex items-start gap-3 border-b border-slate-800 p-5">
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <SeverityBadge severity={f.severity} />
              <span className={`text-xs font-semibold ${accepted ? 'text-emerald-300' : 'text-red-300'}`}>
                {accepted ? '✓ ACCEPTED' : `✕ REJECTED by ${f.rejected_by}`}
              </span>
            </div>
            <h3 className="mt-2 text-lg font-semibold text-slate-100">{f.title}</h3>
            <div className="mt-1 flex flex-wrap gap-x-3 text-xs text-slate-400">
              <span className="font-mono">{path}:{f.start_line}{f.end_line && f.end_line !== f.start_line ? `-${f.end_line}` : ''}</span>
              <span>found by {agent ? `${agent.icon} ${agent.label}` : f.specialist}</span>
              {f.also_reported_by?.length > 0 && <span>also reported by {f.also_reported_by.join(', ')}</span>}
            </div>
          </div>
          <button onClick={onClose} className="rounded-lg px-2 py-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200">✕</button>
        </header>

        <div className="space-y-5 p-5">
          <Section title="Why it's a problem">
            <p className="text-sm leading-relaxed text-slate-300">{f.explanation || '–'}</p>
          </Section>

          <Section title="Evidence quoted by the agent">
            {f.quote_mismatch && (
              <p className="mb-2 rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                ⚠ This quote does not match the real code at that location. The agent likely reconstructed it
                from memory, so the judge ignored it and decided only from the real code below.
              </p>
            )}
            <pre className={`overflow-x-auto rounded-lg bg-slate-950 p-3 font-mono text-xs ${f.quote_mismatch ? 'text-slate-500 line-through decoration-slate-600' : 'text-slate-300'}`}>{f.evidence || '–'}</pre>
          </Section>

          {f.code_shown && (
            <Section title="Code the judge saw">
              <pre className="overflow-x-auto rounded-lg bg-slate-950 p-3 font-mono text-xs leading-relaxed">
                {f.code_shown.split('\n').map((line, i) => (
                  <div key={i} className={line.startsWith('>') ? 'bg-amber-500/10 text-amber-100' : 'text-slate-400'}>{line}</div>
                ))}
              </pre>
            </Section>
          )}

          <Section title={accepted ? "Judge's reasoning" : 'Why it was rejected'}>
            <p className={`rounded-lg p-3 text-sm ${accepted ? 'bg-emerald-500/10 text-emerald-200' : 'bg-red-500/10 text-red-200'}`}>
              {accepted ? f.judge_reason : f.reason}
            </p>
          </Section>
        </div>
      </div>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div>
      <h4 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">{title}</h4>
      {children}
    </div>
  )
}
