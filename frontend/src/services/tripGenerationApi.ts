import { ApiError } from './apiClient'
import type { ApiRequestOptions, ApiResponse } from './apiClient'
import { normalizeGenerationError } from './generation'
import type { GenerationFailure } from './generation'
import { validGenerationRequest, validateGenerationResponse } from './generationValidation'
import type { TripGenerateRequest } from '../types/trip'
import type { TripResult } from '../types/results'

export type TripGenerationOutcome =
  | { ok: true; status: 200; response: TripResult }
  | { ok: false; error: GenerationFailure }
type Client = { request(path: string, options: ApiRequestOptions): Promise<ApiResponse> }
const failure = (code: string, message: string, canRetry = false): TripGenerationOutcome => ({ ok: false,
  error: { code, title: message, message, fields: {}, canRetry } })

/** Inject the shared `api` singleton. No SDK initialization on import, retry, sample fallback,
 * UI mutation or provenance claim. An HTTP response does not prove live provider evidence. */
export function createTripGenerationApi(client: Client, now = Date.now) {
  return {
    async generate(request: TripGenerateRequest, options: { signal: AbortSignal }): Promise<TripGenerationOutcome> {
      if (!validGenerationRequest(request, new Date(now()).toISOString().slice(0, 10))) return failure('INVALID_REQUEST', 'Review your trip details before generating.')
      try {
        const result = await client.request('/api/v1/trips/generate', {
          auth: 'required', method: 'POST', body: { ...request }, signal: options.signal, responseMode: 'endpoint',
        })
        if (result.status !== 200) return { ok: false, error: normalizeGenerationError(result.status, result.headers ?? {}, result.body, now()) }
        const response = validateGenerationResponse(result.body, request)
        return response ? { ok: true, status: 200, response } : failure('INVALID_RESPONSE', 'The service returned a trip that could not be verified.')
      } catch (error) {
        if (!(error instanceof ApiError)) return failure('CONNECTION_ERROR', 'Unable to complete this request.', true)
        if (['SESSION_REQUIRED', 'SESSION_EXPIRED', 'UNAUTHORIZED', 'AUTH_NOT_CONFIGURED'].includes(error.code)) {
          return { ok: false, error: { code: error.code, title: 'Please sign in again', message: error.message,
            fields: {}, canRetry: false, signIn: true, httpStatus: error.status, requestId: error.requestId } }
        }
        return failure(error.code, error.message, ['NETWORK_ERROR', 'AUTH_UNAVAILABLE'].includes(error.code))
      }
    },
  }
}
