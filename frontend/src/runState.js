// Turns the raw event list from events.jsonl into what the dashboard shows.
// Pure function: the same events always give the same state, so live view,
// finished runs and replays all use it.

export const STAGES = [
  { key: 'clone', label: 'Clone' },
  { key: 'scan', label: 'Scan' },
  { key: 'parse', label: 'Parse' },
  { key: 'index', label: 'Index' },
  { key: 'agents', label: 'Agents' },
  { key: 'judge', label: 'Judge' },
  { key: 'done', label: 'Done' },
]

export const AGENTS = {
  security: { label: 'Security', icon: '🔒', accent: 'rose' },
  architecture: { label: 'Architecture', icon: '🏛️', accent: 'violet' },
  production: { label: 'Production', icon: '⚙️', accent: 'amber' },
}
export const AGENT_ORDER = Object.keys(AGENTS)

const MAX_CALLS_KEPT = 6
const MAX_FEED = 150

function newAgent(name) {
  return {
    name, step: 0, of: 10, status: 'idle', // idle | thinking | waiting | reporting | done | error
    activity: null, waitUntil: null, findings: 0, refused: 0, error: null, lastRetry: null, calls: [],
  }
}

function shortArgs(args = {}) {
  const main = args.pattern ?? args.query ?? args.name ?? ''
  const extra = args.direction ? ` (${args.direction})` : ''
  return `${main}${extra}`
}

export function describeTool(tool, args) {
  return `${tool}("${shortArgs(args)}")`
}

function feedText(e) {
  switch (e.type) {
    case 'run_started': return `Audit started for ${e.repo}`
    case 'stage': return {
      clone: 'Cloning repository…', scan: 'Scanning for Python files…',
      parse: `Parsing ${e.files ?? ''} files into functions/classes…`,
      index: `Embedding ${e.entities ?? ''} functions/classes into the vector index…`,
      agents: 'Specialist agents started', judge: `Judge reviewing ${e.findings ?? ''} findings…`,
      done: 'Audit complete',
    }[e.stage]
    case 'tool_call': return describeTool(e.tool, e.args)
    case 'budget_wait': return e.rate_limited ? `rate limited, waiting ${Math.round(e.seconds)}s` : `waiting ${Math.round(e.seconds)}s for token budget`
    case 'finding': return e.recorded ? `reported: ${e.title}` : `finding refused (${e.reason})`
    case 'retry': return `${e.message}, retrying`
    case 'agent_error': return `error: ${e.error}`
    case 'agent_finished': return `finished with ${e.findings} finding${e.findings === 1 ? '' : 's'}`
    case 'judge_evidence': return `evidence check: ${e.passed} passed${e.quote_mismatches ? ` (${e.quote_mismatches} with inaccurate quotes, checked on real code)` : ''}, ${e.rejected} rejected`
    case 'judge_done': return `judge: ${e.accepted} accepted, ${e.rejected} rejected`
    case 'run_failed': return `Audit failed: ${e.error}`
    case 'run_stopped': return 'Audit stopped'
    case 'quota_exhausted': return 'Daily Groq token limit reached; stopping all agents'
    default: return null
  }
}

export function buildState(events) {
  const s = {
    url: null, repo: null, startTs: null, lastTs: null, status: 'running', error: null,
    stage: null, stats: {}, agents: {},
    tokens: { calls: 0, prompt: 0, completion: 0, remaining: null, limit: 8000, waited: 0 },
    findings: [], judge: null, report: null, feed: [], quota: null,
  }
  const agent = (name) => (s.agents[name] ??= newAgent(name))

  for (const e of events) {
    s.lastTs = e.ts
    // Only specialists get a card; the judge's events go to the activity log
    const a = e.agent && e.agent !== 'judge' ? agent(e.agent) : null
    switch (e.type) {
      case 'run_started':
        s.url = e.url; s.repo = e.repo; s.startTs = e.ts
        break
      case 'stage':
        s.stage = e.stage
        if (e.files != null) s.stats.files = e.files
        if (e.entities != null) s.stats.entities = e.entities
        if (e.agents) e.agents.forEach(agent)
        break
      case 'agent_started':
        a.status = 'thinking'
        break
      case 'agent_step':
        a.step = e.step; a.of = e.of
        a.status = e.final ? 'reporting' : 'thinking'
        a.waitUntil = null
        a.activity = e.final ? { kind: 'reporting' } : { kind: 'thinking' }
        break
      case 'tool_call':
        a.activity = { kind: 'tool', tool: e.tool, args: e.args }
        a.calls = [...a.calls, { tool: e.tool, args: e.args, t: e.t }].slice(-MAX_CALLS_KEPT)
        break
      case 'tool_result': {
        const last = a.calls[a.calls.length - 1]
        if (last && last.tool === e.tool) a.calls[a.calls.length - 1] = { ...last, summary: e.summary, error: e.error }
        break
      }
      case 'budget_wait':
        if (a && a.status !== 'done') { a.status = 'waiting'; a.waitUntil = e.ts + e.seconds; a.waitSeconds = e.seconds }
        s.tokens.waited += e.seconds
        break
      case 'llm_call':
        s.tokens.calls += 1
        s.tokens.prompt += e.prompt_tokens || 0
        s.tokens.completion += e.completion_tokens || 0
        if (e.remaining != null) s.tokens.remaining = Number(e.remaining)
        if (e.limit != null) s.tokens.limit = Number(e.limit)
        if (a && a.status === 'waiting') { a.status = 'thinking'; a.waitUntil = null }
        break
      case 'retry':
        if (a) a.lastRetry = e.message
        break
      case 'finding':
        s.findings.push({ ...e, key: `${e.agent}-${s.findings.length}` })
        if (a) e.recorded ? (a.findings += 1) : (a.refused += 1)
        break
      case 'agent_error':
        if (a) a.error = e.error
        break
      case 'quota_exhausted':
        s.quota = { resetsIn: e.resets_in, ts: e.ts }
        break
      case 'agent_finished':
        if (!a) break
        a.status = e.error ? 'error' : 'done'
        a.error = e.error || a.error
        a.findings = e.findings
        a.activity = null; a.waitUntil = null
        break
      case 'judge_evidence':
        s.judge = { passed: e.passed, rejected: e.rejected, results: e.results }
        break
      case 'judge_done':
        s.judge = { ...s.judge, accepted: e.accepted, rejectedTotal: e.rejected }
        break
      case 'run_finished':
        s.status = 'finished'
        s.report = { accepted: e.accepted || [], rejected: e.rejected || [] }
        break
      case 'run_failed':
        s.status = 'failed'; s.error = e.error
        break
      case 'run_stopped':
        s.status = 'stopped'
        break
    }
    const text = feedText(e)
    if (text) s.feed.push({ t: e.t, agent: e.agent, type: e.type, text, recorded: e.recorded })
  }
  if (s.feed.length > MAX_FEED) s.feed = s.feed.slice(-MAX_FEED)
  if (s.status !== 'running') {
    // A finished/stopped run: nobody is still thinking or waiting
    for (const a of Object.values(s.agents)) {
      if (!['done', 'error'].includes(a.status)) { a.status = s.status === 'finished' ? 'done' : 'error'; a.activity = null }
    }
  }
  return s
}

export function formatDuration(seconds) {
  if (seconds == null || Number.isNaN(seconds)) return '–'
  const s = Math.max(0, Math.round(seconds))
  const m = Math.floor(s / 60)
  return m ? `${m}m ${String(s % 60).padStart(2, '0')}s` : `${s}s`
}
