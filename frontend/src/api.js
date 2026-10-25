// Set VITE_API_BASE_URL at build time for production (see frontend/.env.example).
const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

let authToken = null
let onUnauthorized = () => {}

export const setAuthToken = (token) => {
  authToken = token
}

// Called when the server rejects our token (expired or invalid), so the app can log out.
export const setUnauthorizedHandler = (handler) => {
  onUnauthorized = handler
}

const authHeaders = () => (authToken ? { Authorization: `Bearer ${authToken}` } : {})

async function toError(response) {
  const data = await response.json().catch(() => ({}))
  if (response.status === 401 && authToken) onUnauthorized()

  // FastAPI returns `detail` as a string for our errors, or a list for validation errors.
  let message = `Request failed (${response.status})`
  if (typeof data.detail === 'string') message = data.detail
  else if (Array.isArray(data.detail)) {
    message = data.detail.map((d) => `${d.loc?.at(-1) ?? 'input'}: ${d.msg}`).join('; ')
  }
  const error = new Error(message)
  error.status = response.status
  return error
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...authHeaders(), ...options.headers },
  })
  if (!response.ok) throw await toError(response)
  if (response.status === 204) return null
  return response.json()
}

const jsonPost = (path, body) =>
  request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

// ---------- Auth ----------

// The login endpoint follows the OAuth2 password flow, so it takes form data.
export const login = (email, password) =>
  request('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username: email, password }),
  })

export const register = (email, password) => jsonPost('/api/auth/register', { email, password })

// ---------- Chat ----------

// Parse one SSE block ("event: x\ndata: {...}") into { name, data }.
function parseEvent(block) {
  let name = 'message'
  let data = ''
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) name = line.slice(6).trim()
    else if (line.startsWith('data:')) data += line.slice(5).trim()
  }
  return data ? { name, data: JSON.parse(data) } : null
}

/**
 * POST a question and receive the answer as Server-Sent Events.
 * EventSource only supports GET, so we read the fetch() body stream ourselves.
 *
 * onEvent(name, data) is called for: meta, status, route, delta, replace, done, error.
 * Pass an AbortController's signal to cancel; fetch then rejects with AbortError.
 */
export async function streamQuestion(body, { signal, onEvent }) {
  const response = await fetch(`${API_BASE}/api/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
    signal,
  })
  if (!response.ok) throw await toError(response)

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value.replace(/\r\n/g, '\n')

    // Events are separated by a blank line; keep any incomplete event in the buffer.
    let boundary
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const event = parseEvent(buffer.slice(0, boundary))
      buffer = buffer.slice(boundary + 2)
      if (event) onEvent(event.name, event.data)
    }
  }
}

export const getSession = (sessionId) => request(`/api/chat/sessions/${sessionId}`)

// ---------- Documents ----------

export const listDocuments = () => request('/api/documents')

export const uploadDocument = (file) => {
  const form = new FormData()
  form.append('file', file)
  return request('/api/documents/upload', { method: 'POST', body: form })
}

export const deleteDocument = (documentId) =>
  request(`/api/documents/${documentId}`, { method: 'DELETE' })
