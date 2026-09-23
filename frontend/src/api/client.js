const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

async function request(path, options) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed: ${res.status}`)
  }
  return res.json()
}

export function postQuery(query) {
  return request('/api/query', { method: 'POST', body: JSON.stringify({ query }) })
}

export function postFeedback(payload) {
  return request('/api/feedback', { method: 'POST', body: JSON.stringify(payload) })
}

export function getExamples() {
  return request('/api/examples')
}

export function getHealth() {
  return request('/api/health')
}
