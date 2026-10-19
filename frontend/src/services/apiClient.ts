import type { SupabaseClient } from '@supabase/supabase-js'

type SessionAuth = Pick<SupabaseClient['auth'], 'getSession' | 'refreshSession'>
type ApiErrorCode = 'API_NOT_CONFIGURED' | 'INVALID_REQUEST' | 'AUTH_NOT_CONFIGURED'
  | 'SESSION_REQUIRED' | 'SESSION_EXPIRED' | 'AUTH_UNAVAILABLE' | 'UNAUTHORIZED'
  | 'HTTP_ERROR' | 'NETWORK_ERROR' | 'ABORTED' | 'INVALID_RESPONSE'

const messages: Record<ApiErrorCode, string> = {
  API_NOT_CONFIGURED: 'The API connection has not been configured.',
  INVALID_REQUEST: 'This API request is not allowed.',
  AUTH_NOT_CONFIGURED: 'Sign-in is unavailable until authentication is configured.',
  SESSION_REQUIRED: 'Please sign in to continue.',
  SESSION_EXPIRED: 'Your session expired. Please sign in again.',
  AUTH_UNAVAILABLE: 'Unable to verify your session right now. Please try again later.',
  UNAUTHORIZED: 'The API could not authorize this request. Please sign in again.',
  HTTP_ERROR: 'The API could not complete this request. Please try again later.',
  NETWORK_ERROR: 'Unable to reach the API. Check your connection and try again.',
  ABORTED: 'The request was cancelled.',
  INVALID_RESPONSE: 'The API returned an unreadable response.',
}

/** No response bodies, URLs, Auth errors or credentials are retained in errors. */
export class ApiError extends Error {
  readonly code: ApiErrorCode
  readonly status?: number
  readonly requestId?: string
  constructor(code: ApiErrorCode, status?: number, requestId?: string) {
    super(messages[code]); this.name = 'ApiError'
    this.code = code; this.status = status; this.requestId = requestId
  }
}

export interface ApiRequestOptions {
  /** Protected by default. Public calls never initialize Supabase or attach a token. */
  auth?: 'required' | 'none'
  method?: 'GET' | 'POST'
  body?: unknown
  signal?: AbortSignal
}

export interface ApiResponse {
  status: number
  /** Transport JSON only. An endpoint adapter must validate before use. */
  body: unknown
  requestId?: string
}

/** Configure one trusted origin, without a path, credentials, query or fragment. */
export function readApiOrigin(value: unknown): string | null {
  if (typeof value !== 'string' || !value.trim()) return null
  try {
    const url = new URL(value.trim())
    if (url.username || url.password || url.pathname !== '/' || url.search || url.hash) return null
    if (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname))) return null
    return url.origin
  } catch { return null }
}

export function createApiClient(dependencies: {
  baseUrl: unknown
  getAuth: () => SessionAuth | null
  fetch?: typeof fetch
  now?: () => number
}) {
  const origin = readApiOrigin(dependencies.baseUrl)
  const send = dependencies.fetch ?? globalThis.fetch
  const now = dependencies.now ?? Date.now

  async function accessToken(): Promise<string> {
    try {
      const auth = dependencies.getAuth()
      if (!auth) throw new ApiError('AUTH_NOT_CONFIGURED')
      const current = await auth.getSession()
      const expired = (error: { status?: number; code?: string }) => error.status === 401 || error.status === 403
        || ['refresh_token_not_found', 'refresh_token_already_used', 'session_not_found'].includes(error.code ?? '')
      if (current.error) throw new ApiError(expired(current.error) ? 'SESSION_EXPIRED' : 'AUTH_UNAVAILABLE')
      let session = current.data.session
      if (!session) throw new ApiError('SESSION_REQUIRED')
      // getSession already refreshes expired sessions in the SDK. Explicitly refresh
      // a nearly expired result too; never replay a FastAPI operation after a 401.
      if (typeof session.expires_at !== 'number' || !Number.isFinite(session.expires_at)) throw new ApiError('SESSION_EXPIRED')
      if (session.expires_at * 1000 <= now() + 30_000) {
        const refreshed = await auth.refreshSession()
        if (refreshed.error) throw new ApiError(expired(refreshed.error) ? 'SESSION_EXPIRED' : 'AUTH_UNAVAILABLE')
        if (!refreshed.data.session) throw new ApiError('SESSION_EXPIRED')
        session = refreshed.data.session
      }
      if (typeof session.expires_at !== 'number' || !Number.isFinite(session.expires_at) || session.expires_at * 1000 <= now()) throw new ApiError('SESSION_EXPIRED')
      if (typeof session.access_token !== 'string' || !/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(session.access_token)) throw new ApiError('AUTH_UNAVAILABLE')
      return session.access_token
    } catch (error) { throw error instanceof ApiError ? error : new ApiError('AUTH_UNAVAILABLE') }
  }

  return {
    async request(path: string, options: ApiRequestOptions = {}): Promise<ApiResponse> {
      if (!origin) throw new ApiError('API_NOT_CONFIGURED')
      // Root-relative paths only. Never accept an external URL or caller headers.
      if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//') || /[\\\s#]/.test(path)) throw new ApiError('INVALID_REQUEST')
      const url = new URL(path, origin)
      if (url.origin !== origin) throw new ApiError('INVALID_REQUEST')
      const method = options.method ?? 'GET'
      if (!['GET', 'POST'].includes(method) || (options.auth !== undefined && !['required', 'none'].includes(options.auth))) throw new ApiError('INVALID_REQUEST')
      let body: string | undefined
      if (options.body !== undefined) {
        if (method !== 'POST') throw new ApiError('INVALID_REQUEST')
        try { body = JSON.stringify(options.body) } catch { throw new ApiError('INVALID_REQUEST') }
        if (body === undefined) throw new ApiError('INVALID_REQUEST')
      }
      const checkAbort = () => { if (options.signal?.aborted) throw new ApiError('ABORTED') }
      checkAbort()
      const headers = new Headers({ Accept: 'application/json' })
      if (body !== undefined) headers.set('Content-Type', 'application/json')
      if (options.auth !== 'none') headers.set('Authorization', `Bearer ${await accessToken()}`)
      checkAbort()
      let response: Response
      try {
        response = await send(url.href, {
          method, headers, body, signal: options.signal,
          credentials: 'omit', redirect: 'error', cache: 'no-store', mode: 'cors', referrerPolicy: 'no-referrer',
        })
      } catch { checkAbort(); throw new ApiError('NETWORK_ERROR') }
      checkAbort()
      // Do not interpret followed redirects or opaque responses as API success.
      if (response.redirected || response.type === 'opaqueredirect') throw new ApiError('INVALID_RESPONSE')
      const reference = response.headers.get('X-Request-ID')
      const requestId = reference && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(reference) ? reference : undefined
      // Status takes precedence even when an error envelope is absent or malformed.
      if (response.status === 401) throw new ApiError('UNAUTHORIZED', 401, requestId)
      if (!response.ok) throw new ApiError('HTTP_ERROR', response.status, requestId)
      if (response.status === 204) return { status: 204, body: null, requestId }
      try { return { status: response.status, body: await response.json() as unknown, requestId } }
      catch { checkAbort(); throw new ApiError('INVALID_RESPONSE', response.status, requestId) }
    },
  }
}
