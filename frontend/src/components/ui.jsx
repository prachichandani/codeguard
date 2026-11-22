// Small shared pieces. Tailwind needs full class names written out, so colour
// variants are looked up from these maps rather than built from strings.

export const ACCENTS = {
  rose: { text: 'text-rose-300', border: 'border-rose-500/40', bg: 'bg-rose-500/10', bar: 'bg-rose-400', ring: 'ring-rose-400/40' },
  violet: { text: 'text-violet-300', border: 'border-violet-500/40', bg: 'bg-violet-500/10', bar: 'bg-violet-400', ring: 'ring-violet-400/40' },
  amber: { text: 'text-amber-300', border: 'border-amber-500/40', bg: 'bg-amber-500/10', bar: 'bg-amber-400', ring: 'ring-amber-400/40' },
  slate: { text: 'text-slate-300', border: 'border-slate-600', bg: 'bg-slate-500/10', bar: 'bg-slate-400', ring: 'ring-slate-400/40' },
}

const SEVERITY = {
  high: 'bg-red-500/15 text-red-300 ring-red-500/30',
  medium: 'bg-amber-500/15 text-amber-300 ring-amber-500/30',
  low: 'bg-sky-500/15 text-sky-300 ring-sky-500/30',
}

export function SeverityBadge({ severity }) {
  const cls = SEVERITY[String(severity).toLowerCase()] || 'bg-slate-500/15 text-slate-300 ring-slate-500/30'
  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ring-1 ${cls}`}>
      {severity || '?'}
    </span>
  )
}

const STATUS = {
  starting: ['bg-sky-500/15 text-sky-300', 'Starting'],
  running: ['bg-sky-500/15 text-sky-300', 'Running'],
  finished: ['bg-emerald-500/15 text-emerald-300', 'Finished'],
  failed: ['bg-red-500/15 text-red-300', 'Failed'],
  stopped: ['bg-slate-500/20 text-slate-300', 'Stopped'],
  interrupted: ['bg-slate-500/20 text-slate-300', 'Interrupted'],
}

export function StatusBadge({ status }) {
  const [cls, label] = STATUS[status] || ['bg-slate-500/20 text-slate-300', status || 'unknown']
  const active = status === 'running' || status === 'starting'
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {active && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-sky-400" />}
      {label}
    </span>
  )
}

export function Panel({ title, right, children, className = '' }) {
  return (
    <section className={`rounded-xl border border-slate-800 bg-slate-900/60 ${className}`}>
      {(title || right) && (
        <header className="flex items-center justify-between border-b border-slate-800 px-4 py-2.5">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">{title}</h2>
          {right}
        </header>
      )}
      {children}
    </section>
  )
}

export function Spinner({ className = 'h-3.5 w-3.5' }) {
  return <span className={`inline-block animate-spin rounded-full border-2 border-current border-t-transparent ${className}`} />
}
