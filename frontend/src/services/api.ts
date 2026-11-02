import { createApiClient } from './apiClient'
import { createTripGenerationApi } from './tripGenerationApi'
import { getSupabaseClient } from './supabase'

/** Construction is inert. Requests acquire Auth only when explicitly invoked; importing never sends requests. */
export const api = createApiClient({
  baseUrl: import.meta.env.VITE_API_BASE_URL,
  getAuth: () => getSupabaseClient()?.auth ?? null,
})

/** Explicit user submissions only; never invoked on mount. */
export const tripGenerationApi = createTripGenerationApi(api)

export const realGenerationService = {
  context: { contract_version: '0.4', data_mode: 'api', live_evidence: false } as const,
  generate: tripGenerationApi.generate,
}
