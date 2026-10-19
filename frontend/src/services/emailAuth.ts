import type { Session, SupabaseClient } from '@supabase/supabase-js'
import type { AuthConfig } from './authConfig'

export type EmailCallback = { kind: 'none' } | { kind: 'invalid' } | { kind: 'pkce'; code: string; flowId?: string } | { kind: 'confirmation' | 'recovery'; accessToken: string; refreshToken: string }
export type EmailAuthState = { callback: 'none' | 'pending' | 'confirmed' | 'recovery' | 'invalid'; recovery: 'locked' | 'ready' | 'updating' | 'complete'; error: string | null }

/** Pure parser. A URL type is routing context only, never recovery authorization. */
export function parseEmailCallback(url: URL): EmailCallback {
  const hash = new URLSearchParams(url.hash.slice(1))
  const sensitive = ['access_token', 'refresh_token', 'provider_token', 'provider_refresh_token', 'token', 'error', 'error_code', 'error_description', 'code', 'token_hash']
  if (!sensitive.some(key => hash.has(key) || url.searchParams.has(key))) return { kind: 'none' }
  if (url.searchParams.has('code')) {
    const code = url.searchParams.get('code') ?? ''
    const flowId = url.searchParams.get('sb_flow_id') ?? undefined
    if (url.searchParams.getAll('code').length !== 1 || !code.trim() || code.length > 4096
      || sensitive.some(key => key !== 'code' && url.searchParams.has(key)) || sensitive.some(key => hash.has(key))
      || url.searchParams.getAll('sb_flow_id').length > 1 || (flowId !== undefined && !/^[A-Za-z0-9-]{1,128}$/.test(flowId))) return { kind: 'invalid' }
    return { kind: 'pkce', code, ...(flowId === undefined ? {} : { flowId }) }
  }
  if (sensitive.some(key => url.searchParams.has(key)) || ['error', 'error_code', 'error_description', 'code', 'token_hash'].some(key => hash.has(key))) return { kind: 'invalid' }
  if (['access_token', 'refresh_token', 'type'].some(key => hash.getAll(key).length !== 1)) return { kind: 'invalid' }
  const type = hash.get('type')
  const accessToken = hash.get('access_token') ?? ''
  const refreshToken = hash.get('refresh_token') ?? ''
  if (!['signup', 'email', 'recovery'].includes(type ?? '') || !accessToken || !refreshToken || accessToken.length > 16384 || refreshToken.length > 4096) return { kind: 'invalid' }
  return { kind: type === 'recovery' ? 'recovery' : 'confirmation', accessToken, refreshToken }
}

export class PasswordRecoveryError extends Error {
  readonly code: 'not_configured' | 'unauthorized' | 'rate_limited' | 'weak_password' | 'same_password' | 'unavailable'
  constructor(code: PasswordRecoveryError['code']) { super(code); this.name = 'PasswordRecoveryError'; this.code = code }
}

function safeFailure(error: { code?: string; status?: number }): PasswordRecoveryError {
  if (error.status === 429 || ['over_request_rate_limit', 'over_email_send_rate_limit'].includes(error.code ?? '')) return new PasswordRecoveryError('rate_limited')
  if (error.code === 'weak_password') return new PasswordRecoveryError('weak_password')
  if (error.code === 'same_password') return new PasswordRecoveryError('same_password')
  if (error.status === 401 || error.status === 403) return new PasswordRecoveryError('unauthorized')
  return new PasswordRecoveryError('unavailable')
}

const LINK_ERROR = 'This link is invalid, expired, already used, or could not be verified. Request a fresh link and try again.'

/** No URL credentials or sessions are exposed through the UI snapshot. */
export class EmailAuthController {
  private state: EmailAuthState = { callback: 'none', recovery: 'locked', error: null }
  private listeners = new Set<() => void>()
  private client: SupabaseClient | null
  private config: AuthConfig | null
  private callback: EmailCallback
  private processing?: Promise<void>
  private grant: { userId: string; sessionId: string; until: number } | null = null
  private expiry?: ReturnType<typeof setTimeout>
  private epoch = 0
  private request?: Promise<void>
  constructor(client: SupabaseClient | null, config: AuthConfig | null, callback: EmailCallback = { kind: 'none' }) {
    this.client = client; this.config = config; this.callback = callback
    if (callback.kind !== 'none') this.state.callback = 'pending'
  }
  getSnapshot = () => this.state
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener) } }
  private publish(patch: Partial<EmailAuthState>) { this.state = { ...this.state, ...patch }; this.listeners.forEach(listener => listener()) }
  dismissCallback = () => { this.publish({ callback: 'none' }) }
  lock = () => {
    this.epoch++; this.grant = null; clearTimeout(this.expiry)
    if (this.state.recovery !== 'complete') this.publish({ recovery: 'locked' })
  }
  observeSession = (session: Session | null, event?: string) => {
    if (event === 'SIGNED_OUT') { this.lock(); return }
    if (this.grant && (!session || session.user.id !== this.grant.userId || (session.expires_at ?? 0) * 1000 <= Date.now())) this.lock()
  }
  private configured() {
    if (!this.client || !this.config) throw new PasswordRecoveryError('not_configured')
    return { auth: this.client.auth, config: this.config }
  }
  private async verified(token: string) {
    const { auth } = this.configured()
    const identity = await auth.getUser(token)
    if (identity.error || !identity.data.user?.email_confirmed_at) throw new PasswordRecoveryError('unauthorized')
    const result = await auth.getClaims(token)
    const claims = result.data?.claims
    if (result.error || !claims || claims.sub !== identity.data.user.id || typeof claims.exp !== 'number' || claims.exp * 1000 <= Date.now()) throw new PasswordRecoveryError('unauthorized')
    return { userId: identity.data.user.id, claims }
  }
  private recoveryUntil(claims: Record<string, unknown>): number {
    const methods = Array.isArray(claims.amr) ? claims.amr : []
    const times = methods.flatMap(item => typeof item === 'object' && item !== null && item.method === 'recovery' && typeof item.timestamp === 'number' ? [item.timestamp] : [])
    const latest = Math.max(...times)
    // A locally bounded authorization window, also bounded by the verified token.
    const until = Math.min(Number(claims.exp) * 1000, latest * 1000 + 15 * 60_000)
    if (!Number.isFinite(latest) || latest * 1000 > Date.now() + 30_000 || until <= Date.now() || typeof claims.session_id !== 'string' || !claims.session_id) throw new PasswordRecoveryError('unauthorized')
    return until
  }
  process = (): Promise<void> => {
    this.processing ??= this.processOnce()
    return this.processing
  }
  private async processOnce() {
    const callback = this.callback
    this.callback = { kind: 'none' } // Drop the captured credentials after this operation.
    if (callback.kind === 'none') return
    const epoch = this.epoch
    try {
      if (callback.kind === 'invalid') throw new PasswordRecoveryError('unauthorized')
      const { auth } = this.configured()
      let kind: 'confirmation' | 'recovery'
      let established: Awaited<ReturnType<EmailAuthController['verified']>>
      let until: number
      if (callback.kind === 'pkce') {
        // SDK validates the single-use code against its stored browser verifier.
        // Forward captured flow correlation explicitly: the URL was scrubbed already.
        const response = await auth.exchangeCodeForSession(callback.code, callback.flowId ? { flowId: callback.flowId } : undefined)
        if (response.error || !response.data.session) throw new PasswordRecoveryError('unauthorized')
        established = await this.verified(response.data.session.access_token)
        // Classify from verified server claims, not a URL flag or an SDK-internal
        // redirectType property (which is absent from the public response type).
        kind = Array.isArray(established.claims.amr) && established.claims.amr.some(method => typeof method === 'object' && method !== null && method.method === 'recovery') ? 'recovery' : 'confirmation'
        until = kind === 'recovery' ? this.recoveryUntil(established.claims) : 0
      } else {
        // Legacy implicit confirmation links remain usable. Generic OTP claims do
        // not prove recovery; old recovery links must not bypass the strict gate.
        const verified = await this.verified(callback.accessToken)
        until = callback.kind === 'recovery' ? this.recoveryUntil(verified.claims) : 0
        if (this.epoch !== epoch) throw new PasswordRecoveryError('unauthorized')
        const response = await auth.setSession({ access_token: callback.accessToken, refresh_token: callback.refreshToken })
        if (response.error || !response.data.session) throw new PasswordRecoveryError('unauthorized')
        established = await this.verified(response.data.session.access_token)
        if (established.userId !== verified.userId || established.claims.session_id !== verified.claims.session_id) throw new PasswordRecoveryError('unauthorized')
        kind = callback.kind
      }
      if (this.epoch !== epoch) throw new PasswordRecoveryError('unauthorized')
      if (kind === 'recovery') {
        const expires = Math.min(until, this.recoveryUntil(established.claims))
        this.grant = { userId: established.userId, sessionId: String(established.claims.session_id), until: expires }
        this.expiry = setTimeout(() => { this.lock(); this.publish({ error: 'Your recovery authorization expired. Request a new reset link.' }) }, Math.max(0, expires - Date.now()))
        this.publish({ callback: 'recovery', recovery: 'ready', error: null })
      } else this.publish({ callback: 'confirmed', error: null })
    } catch {
      if (this.epoch !== epoch) { this.publish({ callback: 'none' }); return }
      this.lock(); this.publish({ callback: 'invalid', error: LINK_ERROR })
    }
  }
  requestReset = (email: string): Promise<void> => {
    this.request ??= this.sendReset(email).finally(() => { this.request = undefined })
    return this.request
  }
  private async sendReset(email: string): Promise<void> {
    const { auth, config } = this.configured()
    try {
      const { error } = await auth.resetPasswordForEmail(email, { redirectTo: `${config.appUrl}/reset-password` })
      if (error) throw safeFailure(error)
    } catch (error) { throw error instanceof PasswordRecoveryError ? error : new PasswordRecoveryError('unavailable') }
  }
  updatePassword = async (password: string): Promise<void> => {
    if (this.state.recovery === 'updating') throw new PasswordRecoveryError('unavailable')
    const { auth } = this.configured()
    const grant = this.grant
    if (!grant || grant.until <= Date.now() || this.state.recovery !== 'ready') { this.lock(); throw new PasswordRecoveryError('unauthorized') }
    const epoch = this.epoch
    this.publish({ recovery: 'updating', error: null })
    const invalidated = () => {
      if (this.epoch !== epoch || this.grant !== grant) return true
      if (grant.until <= Date.now()) { this.lock(); return true }
      return false
    }
    try {
      const current = await auth.getSession()
      if (current.error || !current.data.session) throw new PasswordRecoveryError('unauthorized')
      const verified = await this.verified(current.data.session.access_token)
      this.recoveryUntil(verified.claims)
      if (this.epoch !== epoch || this.grant !== grant || grant.until <= Date.now() || verified.userId !== grant.userId || verified.claims.session_id !== grant.sessionId) throw new PasswordRecoveryError('unauthorized')
      const { data, error } = await auth.updateUser({ password })
      // The remote operation may have succeeded, but a revoked local operation
      // must not update another account/page or restore an expired success view.
      if (invalidated()) return
      if (error) throw safeFailure(error)
      if (!data.user || data.user.id !== grant.userId) throw new PasswordRecoveryError('unavailable')
      this.grant = null; clearTimeout(this.expiry); this.epoch++
      // The callback has finished; navigation must not show its earlier recovery prompt.
      this.publish({ callback: 'none', recovery: 'complete', error: null })
    } catch (error) {
      // Ignore late failures too: revocation does not tell us the remote outcome.
      if (invalidated()) return
      const failure = error instanceof PasswordRecoveryError ? error : new PasswordRecoveryError('unavailable')
      if (failure.code === 'unauthorized') this.lock()
      else if (this.grant === grant && this.epoch === epoch) this.publish({ recovery: 'ready' })
      throw failure
    }
  }
}
