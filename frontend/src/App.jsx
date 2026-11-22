import { useCallback, useEffect, useMemo, useState } from 'react'
import { getRun, listRuns, stopRun } from './api'
import { AGENT_ORDER, buildState, formatDuration } from './runState'
import { useNow, useRunEvents } from './useRunEvents'
import ActivityFeed from './components/ActivityFeed'
import AgentCard from './components/AgentCard'
import FindingsList from './components/FindingsList'
import NewRunForm from './components/NewRunForm'
import RunHeader from './components/RunHeader'
import RunHistory from './components/RunHistory'
import StageBar from './components/StageBar'
import TokenGauge from './components/TokenGauge'

const ACTIVE = ['starting', 'running']

export default function App() {
  const [runs, setRuns] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [serverError, setServerError] = useState(null)

  const refreshRuns = useCallback(async () => {
    try {
      const list = await listRuns()
      setRuns(list)
      setServerError(null)
      setSelectedId((id) => id ?? list[0]?.id ?? null)
    } catch (e) {
      setServerError(e.message)
    }
  }, [])

  useEffect(() => {
    refreshRuns()
    const id = setInterval(refreshRuns, 4000)
    return () => clearInterval(id)
  }, [refreshRuns])

  const anyActive = runs.some((r) => ACTIVE.includes(r.status))

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center gap-6 border-b border-slate-800 bg-slate-950/80 px-5 py-3 backdrop-blur">
        <div className="flex items-center gap-2">
          <span className="text-2xl">🛡️</span>
          <div>
            <div className="font-semibold tracking-tight text-slate-100">CodeGuard</div>
            <div className="text-[11px] text-slate-500">multi-agent code auditor</div>
          </div>
        </div>
        <NewRunForm busy={anyActive} onStarted={(id) => { setSelectedId(id); refreshRuns() }} />
      </header>

      {serverError && (
        <div className="border-b border-red-500/30 bg-red-500/10 px-5 py-2 text-sm text-red-200">
          Can't reach the CodeGuard server ({serverError}). Is <code className="font-mono">python server.py</code> running?
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <aside className="w-72 shrink-0 border-r border-slate-800 bg-slate-950">
          <RunHistory runs={runs} selectedId={selectedId} onSelect={setSelectedId} />
        </aside>
        <main className="min-w-0 flex-1 overflow-y-auto">
          {selectedId
            ? <RunView key={selectedId} runId={selectedId} listedMeta={runs.find((r) => r.id === selectedId)} onChanged={refreshRuns} />
            : <EmptyState />}
        </main>
      </div>
    </div>
  )
}

function RunView({ runId, listedMeta, onChanged }) {
  const [meta, setMeta] = useState(listedMeta)
  const [stopping, setStopping] = useState(false)

  // Fetch status once on open; after that the list refresh (every 4s) keeps it current
  useEffect(() => { getRun(runId).then(setMeta).catch(() => {}) }, [runId])
  useEffect(() => { if (listedMeta) setMeta(listedMeta) }, [listedMeta])

  const active = ACTIVE.includes(meta?.status)
  const { events, live, replaying, replay, stopReplay, error } = useRunEvents(runId, active)
  const state = useMemo(() => buildState(events), [events])
  const now = useNow(live)

  const elapsed = live && state.startTs ? now - state.startTs
    : state.startTs && state.lastTs ? state.lastTs - state.startTs : null
  const agents = AGENT_ORDER.filter((n) => state.agents[n]).map((n) => state.agents[n])
    .concat(Object.values(state.agents).filter((a) => !AGENT_ORDER.includes(a.name)))

  async function stop() {
    setStopping(true)
    try { await stopRun(runId); onChanged() } catch (e) { alert(e.message) } finally { setStopping(false) }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6">
      <RunHeader state={state} meta={meta} elapsed={elapsed} live={live} replaying={replaying}
                 onReplay={replay} onStopReplay={stopReplay} onStop={stop} stopping={stopping} />
      <StageBar stage={state.stage} status={replaying ? 'running' : state.status} />

      {state.quota && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          <b>Groq's daily token limit was reached</b> {formatDuration(state.quota.ts - state.startTs)} into this audit, so
          the agents stopped early and <b>these results are incomplete</b>.
          {state.quota.resetsIn ? ` Groq said enough quota frees up in about ${formatDuration(state.quota.resetsIn)}.` : ''}
          {' '}The free tier allows roughly 2–3 full audits per day.
        </div>
      )}
      {error && <p className="text-sm text-red-300">Couldn't load events: {error}</p>}
      {state.error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{state.error}</div>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_1fr_1fr_minmax(240px,0.9fr)]">
        {agents.length
          ? agents.map((a) => <AgentCard key={a.name} agent={a} now={now} live={live || replaying} />)
          : <div className="col-span-3 flex items-center justify-center rounded-xl border border-dashed border-slate-800 p-10 text-sm text-slate-500">
              {state.stage ? 'Preparing the code index… agents start after indexing.' : 'Waiting for the audit to start…'}
            </div>}
        <TokenGauge tokens={state.tokens} />
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div><FindingsList state={state} /></div>
        <ActivityFeed feed={state.feed} />
      </div>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
      <span className="text-5xl">🛡️</span>
      <h2 className="text-lg font-semibold text-slate-200">No audits yet</h2>
      <p className="max-w-sm text-sm text-slate-500">
        Paste a GitHub repository URL above and press <b>Run audit</b>. Three specialist agents will
        investigate it live, then a judge verifies every finding.
      </p>
    </div>
  )
}
