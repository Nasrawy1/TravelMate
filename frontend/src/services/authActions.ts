import type { SupabaseClient } from '@supabase/supabase-js'
import type { AuthConfig } from './authConfig'

export type AuthErrorCode = 'not_configured' | 'invalid_credentials' | 'email_not_confirmed' | 'weak_password' | 'rate_limited' | 'unavailable'
export class AuthError extends Error {
  readonly code: AuthErrorCode
  constructor(code: AuthErrorCode) { super(code); this.code = code; this.name = 'AuthError' }
}

function failure(error: { code?: string; status?: number }): AuthError {
  if (error.status === 429 || error.code === 'over_request_rate_limit' || error.code === 'over_email_send_rate_limit') return new AuthError('rate_limited')
  if (error.code === 'invalid_credentials') return new AuthError('invalid_credentials')
  if (error.code === 'email_not_confirmed') return new AuthError('email_not_confirmed')
  if (error.code === 'weak_password') return new AuthError('weak_password')
  return new AuthError('unavailable')
}

/** Injectable for tests; production passes the one shared client. No raw errors escape. */
export function createAuthActions(client: SupabaseClient | null, config: AuthConfig | null) {
  function configured() {
    if (!client || !config) throw new AuthError('not_configured')
    return { auth: client.auth, config }
  }
  return {
    async signIn(credentials: { email: string; password: string }): Promise<void> {
      const { auth } = configured()
      try {
        const { data, error } = await auth.signInWithPassword(credentials)
        if (error) throw failure(error)
        if (!data.session) throw new AuthError('unavailable')
      } catch (error) { throw error instanceof AuthError ? error : new AuthError('unavailable') }
    },
    async signUp(details: { name: string; email: string; password: string }): Promise<'confirmation_required' | 'session_received'> {
      const { auth, config } = configured()
      try {
        const { data, error } = await auth.signUp({ email: details.email, password: details.password,
          options: { data: { display_name: details.name }, emailRedirectTo: `${config.appUrl}/login` } })
        if (error) throw failure(error)
        if (!data.user) throw new AuthError('unavailable')
        // A user object alone does not prove a new account, delivery, or a session.
        return data.session ? 'session_received' : 'confirmation_required'
      } catch (error) { throw error instanceof AuthError ? error : new AuthError('unavailable') }
    },
  }
}
