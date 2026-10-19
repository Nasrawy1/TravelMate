import { createClient } from '@supabase/supabase-js'
import type { SupabaseClient } from '@supabase/supabase-js'
import { readAuthConfig } from './authConfig'

export const authConfig = readAuthConfig(import.meta.env)
let client: SupabaseClient | null = null

// Importing this module creates no client. Only the online route boundary calls it.
export function getSupabaseClient(): SupabaseClient | null {
  if (!authConfig) return null
  client ??= createClient(authConfig.url, authConfig.publishableKey, {
    auth: { persistSession: true, autoRefreshToken: true, flowType: 'pkce', detectSessionInUrl: false },
  })
  return client
}
