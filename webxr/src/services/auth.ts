const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')
const ACCESS_KEY = 'webxr.access'
const REFRESH_KEY = 'webxr.refresh'

type TokenPair = { access_token: string; refresh_token: string; expires_in: number }
type ApiError = { detail?: string }

async function request<T>(path: string, init: RequestInit = {}, authenticated = false): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  if (authenticated) {
    let access = sessionStorage.getItem(ACCESS_KEY)
    if (!access || Number(sessionStorage.getItem('webxr.expires') || 0) <= Date.now()) {
      access = await refreshAccessToken()
    }
    headers.set('Authorization', `Bearer ${access}`)
  }
  let response = await fetch(`${API_BASE}${path}`, { ...init, headers, credentials: 'omit', redirect: 'error' })
  if (response.status === 401 && authenticated) {
    const access = await refreshAccessToken()
    headers.set('Authorization', `Bearer ${access}`)
    response = await fetch(`${API_BASE}${path}`, { ...init, headers, credentials: 'omit', redirect: 'error' })
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({})) as ApiError
    throw new Error(error.detail || 'The request could not be completed.')
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>
}

function saveTokens(tokens: TokenPair) {
  sessionStorage.setItem(ACCESS_KEY, tokens.access_token)
  sessionStorage.setItem(REFRESH_KEY, tokens.refresh_token)
  sessionStorage.setItem('webxr.expires', String(Date.now() + tokens.expires_in * 1000 - 30_000))
}

async function refreshAccessToken(): Promise<string> {
  const refresh = sessionStorage.getItem(REFRESH_KEY)
  if (!refresh) { clearSession(); throw new Error('Please sign in to continue.') }
  try {
    const tokens = await request<TokenPair>('/auth/refresh', { method: 'POST', body: JSON.stringify({ refresh_token: refresh }) })
    saveTokens(tokens)
    return tokens.access_token
  } catch (error) { clearSession(); throw error }
}

export function clearSession() {
  sessionStorage.removeItem(ACCESS_KEY)
  sessionStorage.removeItem(REFRESH_KEY)
  sessionStorage.removeItem('webxr.expires')
}

export const authApi = {
  register: (payload: { email: string; password: string; display_name: string }) => request('/auth/register', { method: 'POST', body: JSON.stringify(payload) }),
  login: async (email: string, password: string) => saveTokens(await request<TokenPair>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })),
  forgot: (email: string) => request('/auth/password/forgot', { method: 'POST', body: JSON.stringify({ email }) }),
  reset: (token: string, new_password: string) => request('/auth/password/reset', { method: 'POST', body: JSON.stringify({ token, new_password }) }),
  verify: async (token: string) => saveTokens(await request<TokenPair>('/auth/verify-email', { method: 'POST', body: JSON.stringify({ token }) })),
  me: () => request('/auth/me', {}, true),
  logout: async () => {
    const refresh = sessionStorage.getItem(REFRESH_KEY)
    clearSession()
    if (refresh) await request('/auth/logout', { method: 'POST', body: JSON.stringify({ refresh_token: refresh }) }).catch(() => undefined)
  },
}
