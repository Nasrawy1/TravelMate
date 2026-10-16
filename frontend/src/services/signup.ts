export interface SignUpDetails {
  // Display name only; future Supabase user metadata, never trip traveler data.
  name: string
  email: string
  password: string
}

export type SignUpErrorCode = 'not_configured' | 'email_taken' | 'unavailable'

export class SignUpError extends Error {
  constructor(public readonly code: SignUpErrorCode) {
    super(code)
    this.name = 'SignUpError'
  }
}

// Replace this boundary with real Supabase Auth integration later. Do not send,
// persist or log credentials, or claim an account/confirmation email exists.
export async function signUp(_details: SignUpDetails): Promise<void> {
  throw new SignUpError('not_configured')
}
