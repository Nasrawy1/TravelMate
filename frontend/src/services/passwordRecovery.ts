export class PasswordRecoveryError extends Error {
  constructor(public readonly code: 'not_configured' | 'unavailable') {
    super(code)
    this.name = 'PasswordRecoveryError'
  }
}

// Integration boundary only. Never send/log/store these values or imply success.
// Future Supabase integration must use a configured redirect to /reset-password
// and return account-neutral messaging after a real accepted reset request.
export async function requestPasswordReset(_email: string): Promise<void> {
  throw new PasswordRecoveryError('not_configured')
}

// A future implementation MUST verify a valid Supabase recovery session before
// updating credentials. Visiting /reset-password is not proof of authorization.
export async function updatePassword(_newPassword: string): Promise<void> {
  throw new PasswordRecoveryError('not_configured')
}
