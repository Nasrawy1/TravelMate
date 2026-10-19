export interface SignUpDetails {
  // Display name only; Supabase user metadata, never trip traveler data.
  name: string
  email: string
  password: string
}

import { createAuthActions } from './authActions'
import { authConfig, getSupabaseClient } from './supabase'
export { AuthError as SignUpError } from './authActions'

export async function signUp(details: SignUpDetails) {
  return createAuthActions(getSupabaseClient(), authConfig).signUp(details)
}
