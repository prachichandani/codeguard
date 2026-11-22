// Calls to the FastAPI backend (server.py)

async function request(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`
    try {
      message = (await res.json()).detail || message
    } catch { /* not JSON */ }
    throw new Error(message)
  }
  return res.json()
}

export const listRuns = () => request('/runs')
export const getRun = (id) => request(`/runs/${id}`)
export const getEvents = (id) => request(`/runs/${id}/events`)
export const startRun = (url) => request('/runs', { method: 'POST', body: JSON.stringify({ url }) })
export const stopRun = (id) => request(`/runs/${id}/stop`, { method: 'POST' })
export const streamUrl = (id) => `/api/runs/${id}/stream`
