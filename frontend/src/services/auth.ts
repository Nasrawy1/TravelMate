export interface SignInCredentials {
  email: string
  password: string
}

export type SignInErrorCode = 'not_configured' | 'invalid_credentials' | 'unavailable'

export class SignInError extends Error {
  constructor(public readonly code: SignInErrorCode) {
    super(code)
    this.name = 'SignInError'
  }
}

// Supabase integration belongs at this boundary. Until configured, do not send,
// store or log credentials, establish a session, or simulate authentication.
export async function signIn(_credentials: SignInCredentials): Promise<void> {
  throw new SignInError('not_configured')
}
