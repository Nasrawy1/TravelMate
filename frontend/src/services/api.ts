import { createApiClient } from './apiClient'
import { getSupabaseClient } from './supabase'

/** Construction is inert. Only the temporary DEV probe calls this; product/demo flows do not. */
export const api = createApiClient({
  baseUrl: import.meta.env.VITE_API_BASE_URL,
  getAuth: () => getSupabaseClient()?.auth ?? null,
})
