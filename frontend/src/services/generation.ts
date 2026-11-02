import type { TripGenerateRequest } from '../types/trip'
import type { TripField, TripFormErrors } from '../utils/tripPlanner'
import type { AuthSessionState } from './authSession'

/** Observe every verified identity transition, even when React batches A → B → A.
 * Rechecking the same identity is not a change; definitive loss of identity is.
 * The caller invalidates its local operation token, never server-side processing. */
export function watchGenerationIdentity(source: {
  getSnapshot: () => AuthSessionState
  subscribe: (listener: () => void) => () => void
}, invalidate: () => void): () => void {
  const identity = (state: AuthSessionState) => state.status === 'authenticated' ? state.user?.id ?? null : null
  let owner = identity(source.getSnapshot())
  const check = () => {
    const state = source.getSnapshot()
    if (state.status === 'checking') return
    const next = identity(state)
    if (next === owner) return
    owner = next
    invalidate()
  }
  const unsubscribe = source.subscribe(check)
  check()
  return unsubscribe
}

export interface GenerationContext {
  contract_version: '0.4'
  data_mode: 'api' | 'structural_mock' | 'development_example'
  live_evidence: false
  fixture?: { file: string; manifest: unknown; case: unknown }
}

/** Raw development fixture transport; real adapters supply normalized outcomes below. */
export interface GenerationService {
  readonly context: GenerationContext
  generate(request: Readonly<TripGenerateRequest>, options: { signal: AbortSignal }): Promise<{
    status: number
    headers: Readonly<Record<string, string>>
    body: unknown
  }>
}

/** Validated endpoint boundary; failures are already sanitized by the shared API adapter. */
export interface ValidatedGenerationService<T extends { generation_status: 'complete' }> {
  readonly context: GenerationContext
  generate(request: Readonly<TripGenerateRequest>, options: { signal: AbortSignal }): Promise<
    { ok: true; status: 200; response: T } | { ok: false; error: GenerationFailure }
  >
}

export interface GenerationErrorEnvelope {
  error: { code: string; message: string; details: Record<string, unknown> | null }
  request_id: string
}

// Success requires a caller-supplied, full v0.4 schema AND semantic validator.
// Keeping the response unknown at the transport boundary prevents an unchecked HTTP 200 cast.
export type ResponseValidator<T extends { generation_status: 'complete' }> = (body: unknown, request: TripGenerateRequest) => T | null

export interface GenerationFailure {
  code: string
  httpStatus?: number
  title: string
  message: string
  requestId?: string
  fields: TripFormErrors
  canRetry: boolean
  signIn?: boolean
  retryAt?: number
}

export type GenerationState<T extends { generation_status: 'complete' }> =
  | { status: 'idle' }
  | { status: 'pending'; request: TripGenerateRequest; context: GenerationContext }
  | { status: 'success'; request: TripGenerateRequest; context: GenerationContext; response: T }
  | { status: 'error'; request: TripGenerateRequest; context: GenerationContext; error: GenerationFailure }

const ERROR_COPY: Record<string, { status: number; title: string; message: string; canRetry: boolean; signIn?: boolean }> = {
  VALIDATION_ERROR: { status: 422, title: 'Please fix the highlighted fields.', message: 'Check your trip details before trying again.', canRetry: false },
  UNSUPPORTED_LOCATION: { status: 400, title: 'We can’t price this route yet', message: 'Try another city. Live provider coverage has not been confirmed.', canRetry: false },
  INVALID_TRIP_DATES: { status: 400, title: 'Check your dates', message: 'Start after today in UTC and choose a stay of 1–7 nights.', canRetry: false },
  UNAUTHORIZED: { status: 401, title: 'Please sign in again', message: 'Sign-in is required to generate a trip. Your form details are kept on this page.', canRetry: false, signIn: true },
  RATE_LIMITED: { status: 429, title: 'Too many requests right now', message: 'Please wait before trying again. Retrying always requires your action.', canRetry: true },
  AI_GENERATION_FAILED: { status: 502, title: 'We couldn’t build your plan', message: 'A complete itinerary was not returned. Your trip details are kept, so you can try again.', canRetry: true },
  PROVIDER_UNAVAILABLE: { status: 503, title: 'The planning service is unavailable', message: 'A service we rely on is unavailable. Try again later. Your trip details are kept.', canRetry: true },
  GENERATION_TIMEOUT: { status: 504, title: 'This is taking too long', message: 'Trip generation passed its time limit. Your details are kept; try again in a moment.', canRetry: true },
  INTERNAL_ERROR: { status: 500, title: 'Something went wrong on our side', message: 'Please try again. If it keeps happening, share the reference below with the team.', canRetry: true },
  FORBIDDEN: { status: 403, title: 'This request is not allowed', message: 'Return to your trip details or contact the team.', canRetry: false },
  NOT_FOUND: { status: 404, title: 'The requested service was not found', message: 'Return to your trip details or contact the team.', canRetry: false },
}

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function header(headers: Readonly<Record<string, string>>, name: string): string | undefined {
  return Object.entries(headers).find(([key]) => key.toLowerCase() === name.toLowerCase())?.[1]
}

function safeId(value: unknown): string | undefined {
  return typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value) ? value : undefined
}

/** Retry-After supports delta seconds and HTTP dates, calculated from receipt time. */
export function retryDeadline(value: string | undefined, now: number): number | undefined {
  if (!value?.trim()) return undefined
  const text = value.trim()
  if (/^\d+$/.test(text)) {
    const deadline = now + Number(text) * 1000
    return Number.isSafeInteger(deadline) ? deadline : undefined
  }
  if (!/^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} [A-Za-z]{3} \d{4} \d{2}:\d{2}:\d{2} GMT$/.test(text)) return undefined
  const date = Date.parse(text)
  return Number.isFinite(date) ? Math.max(now, date) : undefined
}

function localFailure(code: string, title: string, message: string): GenerationFailure {
  return { code, title, message, fields: {}, canRetry: true }
}

export function normalizeGenerationError(status: number, headers: Readonly<Record<string, string>>, body: unknown, now = Date.now()): GenerationFailure {
  // An invalid envelope cannot supply trusted codes or field details, but its HTTP
  // status still determines whether retrying the same request is appropriate.
  const statusCopy = status === 401 ? ERROR_COPY.UNAUTHORIZED
    : status === 422 ? { title: 'Check your trip details', message: 'Review and edit your trip details before trying again.', canRetry: false }
    : status === 400 ? { title: 'Check your cities and dates', message: 'Review and edit your cities and travel dates before trying again.', canRetry: false }
    : status === 403 ? ERROR_COPY.FORBIDDEN
    : status === 404 ? ERROR_COPY.NOT_FOUND : undefined
  const fallback: GenerationFailure = { ...localFailure('INVALID_RESPONSE', 'We couldn’t read the response', 'The service returned an unexpected response. Your details are kept. Please try again later.'),
    ...statusCopy, httpStatus: status, requestId: safeId(header(headers, 'X-Request-ID')),
    retryAt: status === 429 ? retryDeadline(header(headers, 'Retry-After'), now) : undefined }
  const requestId = fallback.requestId
  if (!object(body) || !object(body.error) || !safeId(body.request_id)
    || Object.keys(body).some(key => !['error', 'request_id'].includes(key))
    || Object.keys(body.error).some(key => !['code', 'message', 'details'].includes(key))
    || typeof body.error.code !== 'string' || typeof body.error.message !== 'string' || !body.error.message.trim()
    || !(body.error.details === null || object(body.error.details))
    || requestId === undefined || requestId !== body.request_id) return fallback
  const code = body.error.code
  const copy = Object.hasOwn(ERROR_COPY, code) ? ERROR_COPY[code] : undefined
  if (!copy || copy.status !== status) return fallback
  const fields: TripFormErrors = {}
  // Never render arbitrary server/debug messages. Map recognized field names to safe copy.
  const fieldCopy: Record<TripField, string> = {
    departure_city: 'Check your departure city.', destination_city: 'Check your destination city.',
    start_date: 'Check your start date.', return_date: 'Check your return date.',
    adults: 'Choose between 1 and 4 adults (a whole number).', budget_usd: 'Enter a finite, positive whole-trip budget in USD.',
  }
  if (['VALIDATION_ERROR', 'UNSUPPORTED_LOCATION', 'INVALID_TRIP_DATES'].includes(code) && object(body.error.details) && Array.isArray(body.error.details.fields)) {
    for (const item of body.error.details.fields) {
      if (object(item) && typeof item.field === 'string' && Object.hasOwn(fieldCopy, item.field)) {
        fields[item.field as TripField] = fieldCopy[item.field as TripField]
      }
    }
  }
  return { ...copy, code, httpStatus: status, requestId: safeId(body.request_id), fields,
    retryAt: code === 'RATE_LIMITED' ? retryDeadline(header(headers, 'Retry-After'), now) : undefined }
}

/** Single-flight lifecycle; no network, automatic retries, persistence or auth side effects. */
export class GenerationController<T extends { generation_status: 'complete' }> {
  private state: GenerationState<T> = { status: 'idle' }
  private listeners = new Set<() => void>()
  private operation?: AbortController
  private retryAt = 0
  private readonly validate: ResponseValidator<T>
  private readonly now: () => number
  private readonly timeoutMs: number
  constructor(validate: ResponseValidator<T>, now = Date.now, timeoutMs = 70_000) {
    this.validate = validate
    this.now = now
    this.timeoutMs = timeoutMs
  }
  getSnapshot = (): GenerationState<T> => this.state
  getRetryAt = (): number => this.retryAt
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener) } }
  private publish(state: GenerationState<T>) { this.state = state; this.listeners.forEach(listener => listener()) }
  cancel = () => {
    const operation = this.operation
    this.operation = undefined
    operation?.abort()
    this.publish({ status: 'idle' })
  }
  async start(request: TripGenerateRequest, service: GenerationService | ValidatedGenerationService<T>): Promise<boolean> {
    if (this.operation || this.now() < this.retryAt || (this.state.status === 'error' && !this.state.error.canRetry)) return false
    const operation = new AbortController()
    this.operation = operation // Synchronous gate, including same-tick double clicks.
    const input = Object.freeze({ ...request })
    this.publish({ status: 'pending', request: input, context: service.context })
    let timer: ReturnType<typeof setTimeout> | undefined
    const deadlineError = new Error('transport deadline')
    try {
      const aborted = new Promise<never>((_, reject) => {
        operation.signal.addEventListener('abort', () => reject(new Error('cancelled')), { once: true })
      })
      const timeout = new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(deadlineError), this.timeoutMs)
      })
      const result = await Promise.race([service.generate(input, { signal: operation.signal }), timeout, aborted])
      if (this.operation !== operation) return false
      if ('ok' in result) {
        if (result.ok) this.publish({ status: 'success', request: input, context: service.context, response: result.response })
        else {
          this.retryAt = Math.max(this.retryAt, result.error.retryAt ?? 0)
          this.publish({ status: 'error', request: input, context: service.context, error: result.error })
        }
      } else if (result.status === 200) {
        let response: T | null = null
        try { response = this.validate(result.body, input) } catch { /* Validation failure is not a successful trip. */ }
        if (!response || response.generation_status !== 'complete') {
          this.publish({ status: 'error', request: input, context: service.context,
            error: localFailure('INVALID_RESPONSE', 'We couldn’t verify the trip response', 'A complete, contract-valid response is required. No trip has been marked ready.') })
        } else this.publish({ status: 'success', request: input, context: service.context, response })
      } else {
        const error = normalizeGenerationError(result.status, result.headers, result.body, this.now())
        this.retryAt = Math.max(this.retryAt, error.retryAt ?? 0)
        this.publish({ status: 'error', request: input, context: service.context, error })
      }
    } catch (error) {
      if (this.operation !== operation) return false
      const deadline = error === deadlineError
      this.publish({ status: 'error', request: input, context: service.context, error: deadline
        ? localFailure('TRANSPORT_TIMEOUT', 'This is taking too long', 'The 70-second connection allowance expired. Your form details are kept. Cancelling locally does not guarantee server cancellation.')
        : localFailure('CONNECTION_ERROR', 'We couldn’t reach the planning service', 'Check your connection and try again when you are ready. Your form details are kept.') })
    } finally {
      clearTimeout(timer)
      if (this.operation === operation) this.operation = undefined
      operation.abort()
    }
    return true
  }
}
