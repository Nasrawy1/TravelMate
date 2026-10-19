import type { Session, SupabaseClient } from '@supabase/supabase-js'

/** Display metadata is untrusted and is never an authorization signal. */
export function safeDisplayName(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const name = value.trim().replace(/\s+/g, ' ')
  return name.length > 0 && name.length <= 48 && /^[\p{L}\p{M}\p{N} .’'-]+$/u.test(name) ? name : null
}

export type AuthSessionState = {
  status: 'checking' | 'anonymous' | 'authenticated' | 'unavailable' | 'not_configured' | 'expired'
  user: { id: string; displayName: string | null } | null
}

/** Only verified identity enters UI state; tokens stay inside the SDK boundary. */
export class AuthSessionController {
  private state: AuthSessionState = { status: 'checking', user: null }
  private listeners = new Set<() => void>()
  private revision = 0
  private timer?: ReturnType<typeof setTimeout>
  private deferred?: ReturnType<typeof setTimeout>
  private active = false
  private client: SupabaseClient | null
  constructor(client: SupabaseClient | null) { this.client = client }
  getSnapshot = () => this.state
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener) } }
  private publish(status: AuthSessionState['status'], user: AuthSessionState['user'] = null) {
    this.state = { status, user }; this.listeners.forEach(listener => listener())
  }
  private async verify(session: Session | null, revision: number) {
    if (!this.active || revision !== this.revision || !this.client) return
    clearTimeout(this.timer)
    if (!session) { this.publish('anonymous'); return }
    const expires = (session.expires_at ?? 0) * 1000
    if (expires <= Date.now()) { this.publish('expired'); return }
    try {
      const { data, error } = await this.client.auth.getUser(session.access_token)
      if (!this.active || revision !== this.revision) return
      if (error || !data.user || data.user.id !== session.user.id || !data.user.email_confirmed_at) {
        this.publish(error?.status === 401 || error?.status === 403 ? 'expired' : 'unavailable'); return
      }
      const remaining = expires - Date.now()
      if (remaining <= 0) { this.publish('expired'); return }
      this.publish('authenticated', { id: data.user.id, displayName: safeDisplayName(data.user.user_metadata?.display_name) })
      this.timer = setTimeout(() => { if (this.active && revision === this.revision) this.publish('expired') }, Math.min(remaining, 2_147_483_647))
    } catch { if (this.active && revision === this.revision) this.publish('unavailable') }
  }
  refresh = async () => {
    if (!this.active || !this.client) return
    const revision = ++this.revision
    clearTimeout(this.timer)
    this.publish('checking')
    try {
      const { data, error } = await this.client.auth.getSession()
      if (!this.active || revision !== this.revision) return
      if (error) { this.publish('unavailable'); return }
      await this.verify(data.session, revision)
    } catch { if (this.active && revision === this.revision) this.publish('unavailable') }
  }
  start = () => {
    this.active = true
    if (!this.client) { this.publish('not_configured'); return () => { this.active = false } }
    const { data } = this.client.auth.onAuthStateChange((_event, session) => {
      const revision = ++this.revision
      clearTimeout(this.timer)
      clearTimeout(this.deferred)
      this.publish(session ? 'checking' : 'anonymous')
      // Never await another Auth call inside the SDK's event callback/lock.
      this.deferred = setTimeout(() => { void this.verify(session, revision) }, 0)
    })
    this.client.auth.startAutoRefresh()
    void this.refresh()
    return () => {
      this.active = false; this.revision++
      clearTimeout(this.timer); clearTimeout(this.deferred)
      data.subscription.unsubscribe()
      this.client?.auth.stopAutoRefresh()
    }
  }
  signOut = async (): Promise<boolean> => {
    if (!this.client) return false
    ++this.revision; clearTimeout(this.timer); this.publish('checking')
    try {
      const { error } = await this.client.auth.signOut({ scope: 'local' })
      if (!this.active) return false
      this.publish(error ? 'unavailable' : 'anonymous')
      return !error
    } catch { if (this.active) this.publish('unavailable'); return false }
  }
}
