export interface SignInCredentials {
  email: string
  password: string
}

import { createAuthActions } from './authActions'
import { authConfig, getSupabaseClient } from './supabase'
export { AuthError as SignInError } from './authActions'

export async function signIn(credentials: SignInCredentials): Promise<void> {
  return createAuthActions(getSupabaseClient(), authConfig).signIn(credentials)
}
