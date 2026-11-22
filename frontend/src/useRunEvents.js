import { useCallback, useEffect, useRef, useState } from 'react'
import { getEvents, streamUrl } from './api'

const REPLAY_SPEED = 12      // 12x real time
const REPLAY_MAX_GAP = 1.5   // seconds; long waits (token budget) are compressed to this

// Events for one run.
// - Running run: streams live from the server (Server-Sent Events).
// - Finished run: loads all events at once; replay() plays them back with
//   their original timing (sped up), which is handy for demos.
export function useRunEvents(runId, active) {
  const [events, setEvents] = useState([])
  const [live, setLive] = useState(false)
  const [replaying, setReplaying] = useState(false)
  const [error, setError] = useState(null)
  const allEvents = useRef([])
  const replayTimer = useRef(null)

  const stopReplay = useCallback(() => {
    clearTimeout(replayTimer.current)
    replayTimer.current = null
    setReplaying(false)
    setEvents(allEvents.current)
  }, [])

  useEffect(() => {
    setEvents([]); setError(null); setReplaying(false)
    allEvents.current = []
    clearTimeout(replayTimer.current)
    if (!runId) return

    if (active) {
      const source = new EventSource(streamUrl(runId))
      const buffer = []
      let flushTimer = null
      setLive(true)
      // Batch updates: the stream sends the whole history first, often hundreds of lines
      const flush = () => {
        flushTimer = null
        allEvents.current = [...allEvents.current, ...buffer.splice(0)]
        setEvents(allEvents.current)
      }
      source.onmessage = (msg) => {
        try { buffer.push(JSON.parse(msg.data)) } catch { return }
        flushTimer ??= setTimeout(flush, 100)
      }
      source.addEventListener('end', () => { source.close(); setLive(false) })
      source.onerror = () => {
        // The browser reconnects by itself; a reconnect replays history, so start over
        if (source.readyState === EventSource.CONNECTING) {
          allEvents.current = []; buffer.length = 0
        } else {
          setLive(false)
        }
      }
      return () => { source.close(); clearTimeout(flushTimer); setLive(false) }
    }

    let cancelled = false
    setLive(false)
    getEvents(runId)
      .then((evts) => { if (!cancelled) { allEvents.current = evts; setEvents(evts) } })
      .catch((e) => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [runId, active])

  const replay = useCallback(() => {
    const all = allEvents.current
    if (!all.length) return
    clearTimeout(replayTimer.current)
    setReplaying(true)
    setEvents([])
    let i = 0
    const next = () => {
      i += 1
      setEvents(all.slice(0, i))
      if (i >= all.length) { setReplaying(false); replayTimer.current = null; return }
      const gap = Math.min(all[i].t - all[i - 1].t, REPLAY_MAX_GAP * REPLAY_SPEED) / REPLAY_SPEED
      replayTimer.current = setTimeout(next, Math.max(gap * 1000, 15))
    }
    replayTimer.current = setTimeout(next, 300)
  }, [])

  useEffect(() => () => clearTimeout(replayTimer.current), [])

  return { events, live, replaying, replay, stopReplay, error }
}

// Re-renders every `ms` while enabled (for elapsed time and countdowns)
export function useNow(enabled, ms = 1000) {
  const [now, setNow] = useState(() => Date.now() / 1000)
  useEffect(() => {
    if (!enabled) return
    const id = setInterval(() => setNow(Date.now() / 1000), ms)
    return () => clearInterval(id)
  }, [enabled, ms])
  return now
}
