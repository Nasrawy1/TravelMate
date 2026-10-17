import manifest from '../../../docs/fixtures/manifest.json' with { type: 'json' }
import unauthorized from '../../../docs/fixtures/unauthorized.json' with { type: 'json' }
import validation from '../../../docs/fixtures/validation-error.json' with { type: 'json' }
import aiFailure from '../../../docs/fixtures/ai-failure.json' with { type: 'json' }
import timeout from '../../../docs/fixtures/timeout.json' with { type: 'json' }
import rateLimited from '../../../docs/fixtures/rate-limited.json' with { type: 'json' }
import type { GenerationErrorEnvelope, GenerationService } from '../services/generation'

const bodies: Record<string, unknown> = {
  'unauthorized.json': unauthorized, 'validation-error.json': validation,
  'ai-failure.json': aiFailure, 'timeout.json': timeout, 'rate-limited.json': rateLimited,
}

export const GENERATION_PREVIEWS = [
  ['pending', 'Loading only · MOCK operation'],
  ['validation-error.json', '422 · Validation · repository fixture'],
  ['unauthorized.json', '401 · Unauthorized · repository fixture'],
  ['rate-limited.json', '429 · Rate limited · repository fixture'],
  ['ai-failure.json', '502 · AI failure · repository fixture'],
  ['timeout.json', '504 · Timeout · repository fixture'],
  ['UNSUPPORTED_LOCATION', '400 · Unsupported location · frontend example'],
  ['INVALID_TRIP_DATES', '400 · Invalid dates · frontend example'],
  ['PROVIDER_UNAVAILABLE', '503 · Service unavailable · frontend example'],
  ['INTERNAL_ERROR', '500 · Internal error · frontend example'],
] as const

/** Development only: never returns a fabricated successful itinerary. */
export function createGenerationMock(scenario: string): GenerationService {
  const fixtureCase = manifest.cases.find(item => item.file === scenario && item.schema === 'error')
  const context: GenerationService['context'] = fixtureCase
    ? { contract_version: '0.4', data_mode: 'structural_mock', live_evidence: false, fixture: { file: scenario, manifest, case: fixtureCase } }
    : { contract_version: '0.4', data_mode: 'development_example', live_evidence: false }
  return { context, generate: (_request, { signal }) => new Promise((resolve, reject) => {
    let timer: ReturnType<typeof setTimeout> | undefined
    const abort = () => { clearTimeout(timer); reject(new Error('cancelled')) }
    if (signal.aborted) { abort(); return }
    signal.addEventListener('abort', abort, { once: true })
    if (scenario === 'pending') return // Explicit indefinite loading inspection; controller still has its 70s deadline.
    timer = setTimeout(() => {
      signal.removeEventListener('abort', abort)
      if (fixtureCase && typeof fixtureCase.http_status === 'number' && Object.hasOwn(bodies, scenario)) {
        const headers: Record<string, string> = {}
        for (const [key, value] of Object.entries(fixtureCase.headers ?? {})) if (typeof value === 'string') headers[key] = value
        resolve({ status: fixtureCase.http_status, headers, body: bodies[scenario] })
        return
      }
      const status = scenario === 'PROVIDER_UNAVAILABLE' ? 503 : scenario === 'INTERNAL_ERROR' ? 500 : 400
      const body: GenerationErrorEnvelope = { error: { code: scenario, message: 'Frontend-only development example.', details: null }, request_id: `example-${scenario.toLowerCase()}` }
      resolve({ status, headers: { 'X-Request-ID': body.request_id }, body })
    }, 700)
  }) }
}
