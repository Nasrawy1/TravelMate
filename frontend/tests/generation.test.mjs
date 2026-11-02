// node --experimental-strip-types --test tests/*.test.mjs
import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { GenerationController, normalizeGenerationError, retryDeadline } from '../src/services/generation.ts'
import { createGenerationMock } from '../src/fixtures/generationMocks.ts'

const readFixture = file => JSON.parse(readFileSync(new URL(`../../docs/fixtures/${file}`, import.meta.url), 'utf8'))
const request = readFixture('request.json')
const manifest = readFixture('manifest.json')
const context = { contract_version: '0.4', data_mode: 'development_example', live_evidence: false }
const envelope = (code, details = null) => ({ error: { code, message: 'DO_NOT_RENDER_RAW_DEBUG', details }, request_id: 'test-reference' })
const result = (code, status, extraHeaders = {}) => ({ status, headers: { 'X-Request-ID': 'test-reference', ...extraHeaders }, body: envelope(code) })
const service = generate => ({ context, generate })
const tick = () => new Promise(resolve => setTimeout(resolve, 0))

test('repository fixtures retain original response, manifest, case, HTTP status and headers', async () => {
  await Promise.all(['validation-error.json', 'unauthorized.json', 'rate-limited.json', 'ai-failure.json', 'timeout.json'].map(async file => {
    const mock = createGenerationMock(file)
    const fixtureCase = manifest.cases.find(item => item.file === file)
    assert.deepEqual(mock.context.fixture.manifest, manifest)
    assert.deepEqual(mock.context.fixture.case, fixtureCase)
    assert.equal(mock.context.data_mode, manifest.data_mode)
    assert.equal(mock.context.live_evidence, false)
    const response = await mock.generate(request, { signal: new AbortController().signal })
    assert.deepEqual(response.body, readFixture(file))
    assert.deepEqual(response.headers, fixtureCase.headers)
    assert.equal(response.status, fixtureCase.http_status)
    const error = normalizeGenerationError(response.status, response.headers, response.body, 1000)
    assert.equal(error.code, response.body.error.code)
    assert.equal(error.requestId, response.body.request_id)
  }))
})

for (const [code, status, retry] of [
  ['VALIDATION_ERROR', 422, false], ['UNSUPPORTED_LOCATION', 400, false], ['INVALID_TRIP_DATES', 400, false],
  ['UNAUTHORIZED', 401, false], ['RATE_LIMITED', 429, true], ['AI_GENERATION_FAILED', 502, true],
  ['PROVIDER_UNAVAILABLE', 503, true], ['GENERATION_TIMEOUT', 504, true], ['INTERNAL_ERROR', 500, true],
]) test(`${status} ${code} has safe copy and appropriate manual actions`, () => {
  const response = result(code, status)
  const error = normalizeGenerationError(response.status, response.headers, response.body)
  assert.equal(error.code, code)
  assert.equal(error.canRetry, retry)
  assert.equal(Boolean(error.signIn), code === 'UNAUTHORIZED')
  assert.ok(!JSON.stringify(error).includes('DO_NOT_RENDER_RAW_DEBUG'))
})

test('validation maps only recognized fields, without exposing server/debug text', () => {
  const error = normalizeGenerationError(422, { 'x-request-id': 'test-reference' }, envelope('VALIDATION_ERROR', {
    fields: [{ field: 'adults', message: 'DO_NOT_RENDER_RAW_DEBUG' }, { field: '__proto__', message: 'bad' }, { field: 'unknown', message: 'bad' }],
  }))
  assert.deepEqual(error.fields, { adults: 'Choose between 1 and 4 adults (a whole number).' })
  assert.ok(!JSON.stringify(error).includes('DO_NOT_RENDER_RAW_DEBUG'))
})

test('rejects malformed envelopes, mismatched codes/statuses, references and extra properties', () => {
  for (const response of [
    { status: 500, headers: {}, body: '<html>debug</html>' },
    result('UNAUTHORIZED', 500),
    { ...result('INTERNAL_ERROR', 500), headers: {} },
    { ...result('INTERNAL_ERROR', 500), headers: { 'X-Request-ID': 'different-reference' } },
    { ...result('INTERNAL_ERROR', 500), body: { ...envelope('INTERNAL_ERROR'), debug: 'secret' } },
    { ...result('INTERNAL_ERROR', 500), body: { ...envelope('INTERNAL_ERROR'), request_id: '<script>unsafe</script>' } },
  ]) assert.equal(normalizeGenerationError(response.status, response.headers, response.body).code, 'INVALID_RESPONSE')
})

for (const [code, status] of [
  ['UNAUTHORIZED', 401], ['VALIDATION_ERROR', 422], ['UNSUPPORTED_LOCATION', 400], ['INVALID_TRIP_DATES', 400],
]) test(`${status} ${code} preserves safe actions with missing/inaccessible references or malformed responses`, () => {
  const body = envelope(code, { fields: [{ field: 'adults', message: 'DO_NOT_RENDER_RAW_DEBUG' }] })
  for (const response of [
    // A browser adapter cannot read a header that CORS does not expose.
    { headers: {}, body },
    { headers: { 'Retry-After': '30' }, body },
    { headers: { 'X-Request-ID': '<unsafe>' }, body },
    { headers: {}, body: null },
    { headers: {}, body: '<html>DO_NOT_RENDER_RAW_DEBUG</html>' },
    { headers: { 'x-request-id': 'test-reference' }, body: { ...body, debug: 'DO_NOT_RENDER_RAW_DEBUG' } },
    { headers: { 'X-Request-ID': 'test-reference' }, body: envelope('INTERNAL_ERROR') },
    { headers: { 'X-Request-ID': 'header-reference' }, body },
  ]) {
    const error = normalizeGenerationError(status, response.headers, response.body)
    assert.equal(error.code, 'INVALID_RESPONSE')
    assert.equal(error.httpStatus, status)
    assert.equal(error.canRetry, false)
    assert.equal(Boolean(error.signIn), status === 401)
    assert.deepEqual(error.fields, {})
    assert.equal(error.retryAt, undefined)
    const reference = response.headers['X-Request-ID'] ?? response.headers['x-request-id']
    assert.equal(error.requestId, reference === '<unsafe>' ? undefined : reference)
    assert.ok(!JSON.stringify(error).includes('DO_NOT_RENDER_RAW_DEBUG'))
    assert.match(error.message, status === 401 ? /Sign-in is required/ : /edit/)
  }
})

test('malformed server errors remain manually retryable without inventing references', () => {
  for (const status of [500, 502, 503, 504]) {
    const error = normalizeGenerationError(status, {}, envelope('INTERNAL_ERROR'))
    assert.equal(error.code, 'INVALID_RESPONSE')
    assert.equal(error.canRetry, true)
    assert.equal(error.requestId, undefined)
    assert.equal(error.signIn, undefined)
  }
})

test('malformed auth and input errors block resubmission until edit', async () => {
  for (const status of [401, 422, 400]) {
    let calls = 0
    const adapter = service(async () => { calls++; return { status, headers: {}, body: 'invalid' } })
    const controller = new GenerationController(() => null)
    await controller.start(request, adapter)
    assert.deepEqual(controller.getSnapshot().request, request)
    assert.equal(await controller.start(request, adapter), false)
    assert.equal(calls, 1)
    controller.cancel()
    await controller.start(request, adapter)
    assert.equal(calls, 2)
  }
})

test('Retry-After supports seconds, HTTP dates and safe invalid/missing handling', () => {
  const now = Date.parse('2026-10-16T12:00:00Z')
  assert.equal(retryDeadline('30', now), now + 30_000)
  assert.equal(retryDeadline('Fri, 16 Oct 2026 12:00:15 GMT', now), now + 15_000)
  assert.equal(retryDeadline('Fri, 16 Oct 2026 11:59:00 GMT', now), now)
  for (const value of [undefined, '', '-1', '1.5', 'Infinity', '999999999999999999999', 'bad']) assert.equal(retryDeadline(value, now), undefined)
})

test('duplicate submissions are blocked synchronously and the original request is preserved', async () => {
  let complete
  let calls = 0
  const adapter = service((input) => { calls++; assert.deepEqual(input, request); return new Promise(resolve => { complete = resolve }) })
  const controller = new GenerationController(() => null)
  const first = controller.start(request, adapter)
  assert.equal(controller.getSnapshot().status, 'pending')
  assert.equal(await controller.start(request, adapter), false)
  assert.equal(calls, 1)
  complete(result('AI_GENERATION_FAILED', 502))
  await first
  assert.equal(controller.getSnapshot().status, 'error')
  assert.deepEqual(controller.getSnapshot().request, request)
  assert.equal(calls, 1)
})

test('countdown expiry never retries; the controller also enforces cooldown after edit', async () => {
  let now = 1000
  let calls = 0
  const adapter = service(async () => { calls++; return result('RATE_LIMITED', 429, { 'Retry-After': '2' }) })
  const controller = new GenerationController(() => null, () => now)
  await controller.start(request, adapter)
  assert.equal(controller.getSnapshot().error.retryAt, 3000)
  assert.equal(await controller.start(request, adapter), false)
  controller.cancel()
  assert.equal(await controller.start(request, adapter), false)
  now = 4000
  await tick()
  assert.equal(calls, 1)
  await controller.start(request, adapter)
  assert.equal(calls, 2)
})

test('auth/validation/unsupported inputs require edit before another operation', async () => {
  for (const [code, status] of [['UNAUTHORIZED', 401], ['VALIDATION_ERROR', 422], ['UNSUPPORTED_LOCATION', 400], ['INVALID_TRIP_DATES', 400]]) {
    let calls = 0
    const adapter = service(async () => { calls++; return result(code, status) })
    const controller = new GenerationController(() => null)
    await controller.start(request, adapter)
    assert.equal(await controller.start(request, adapter), false)
    assert.equal(calls, 1)
    controller.cancel()
    await controller.start(request, adapter)
    assert.equal(calls, 2)
  }
})

test('429 cooldown is honored even when its response body is malformed', async () => {
  const controller = new GenerationController(() => null, () => 1000)
  const adapter = service(async () => ({ status: 429, headers: { 'Retry-After': '30' }, body: 'invalid' }))
  await controller.start(request, adapter)
  assert.equal(controller.getSnapshot().error.retryAt, 31_000)
  assert.equal(await controller.start(request, adapter), false)
})

test('cancel aborts and ignores late results even when the service ignores AbortSignal', async () => {
  let complete
  let signal
  const controller = new GenerationController(() => null)
  const pending = controller.start(request, service((_request, options) => { signal = options.signal; return new Promise(resolve => { complete = resolve }) }))
  controller.cancel()
  assert.equal(signal.aborted, true)
  assert.equal(controller.getSnapshot().status, 'idle')
  await controller.start(request, service(async () => result('INTERNAL_ERROR', 500)))
  complete(result('AI_GENERATION_FAILED', 502))
  await pending
  assert.equal(controller.getSnapshot().error.code, 'INTERNAL_ERROR')
})

test('transport deadline aborts without retrying or marking success', async () => {
  let signal
  let calls = 0
  const controller = new GenerationController(() => null, Date.now, 5)
  await controller.start(request, service((_request, options) => { calls++; signal = options.signal; return new Promise(() => {}) }))
  assert.equal(controller.getSnapshot().error.code, 'TRANSPORT_TIMEOUT')
  assert.equal(signal.aborted, true)
  assert.equal(calls, 1)
})

test('unchecked 200, validator exceptions and rejected responses never become successful trips', async () => {
  for (const validator of [() => null, () => { throw new Error('DO_NOT_RENDER_RAW_DEBUG') }]) {
    const controller = new GenerationController(validator)
    await controller.start(request, service(async () => ({ status: 200, headers: {}, body: { generation_status: 'complete' } })))
    assert.equal(controller.getSnapshot().error.code, 'INVALID_RESPONSE')
  }
})

test('success state is reachable only through the injected validator (unit stub; no trip fixture)', async () => {
  const approvedByTestValidator = { generation_status: 'complete', testOnly: true }
  const controller = new GenerationController((body, input) => { assert.deepEqual(input, request); return body === approvedByTestValidator ? body : null })
  await controller.start(request, service(async () => ({ status: 200, headers: {}, body: approvedByTestValidator })))
  assert.equal(controller.getSnapshot().status, 'success')
})

test('service exceptions are safe, never leak debug text and do not retry', async () => {
  let calls = 0
  const controller = new GenerationController(() => null)
  await controller.start(request, service(async () => { calls++; throw new Error('DO_NOT_RENDER_RAW_DEBUG') }))
  assert.equal(controller.getSnapshot().error.code, 'CONNECTION_ERROR')
  assert.ok(!JSON.stringify(controller.getSnapshot()).includes('DO_NOT_RENDER_RAW_DEBUG'))
  assert.equal(calls, 1)
})

test('missing repository cases are explicitly development examples, never structural fixtures', () => {
  for (const scenario of ['UNSUPPORTED_LOCATION', 'INVALID_TRIP_DATES', 'PROVIDER_UNAVAILABLE', 'INTERNAL_ERROR']) {
    const mock = createGenerationMock(scenario)
    assert.equal(mock.context.data_mode, 'development_example')
    assert.equal(mock.context.fixture, undefined)
    assert.equal(mock.context.live_evidence, false)
  }
})

// Real boundary outcomes: no HTTP, Supabase or chargeable generation in these tests.
const apiContext = { contract_version: '0.4', data_mode: 'api', live_evidence: false }
const validatedService = generate => ({ context: apiContext, generate })
const safeFailure = (code, extra = {}) => ({ ok: false, error: { code, title: 'Safe error', message: 'Safe error', fields: {}, canRetry: true, ...extra } })

test('real lifecycle publishes loading synchronously, prevents duplicates and retains exact validated response', async () => {
  let finish, calls = 0
  const response = readFixture('within-budget.json')
  const before = structuredClone(response)
  const controller = new GenerationController(() => null)
  const service = validatedService(async (input, { signal }) => {
    calls++; assert.deepEqual(input, request); assert.equal(signal.aborted, false)
    return await new Promise(resolve => { finish = resolve })
  })
  const first = controller.start(request, service)
  assert.equal(controller.getSnapshot().status, 'pending')
  assert.equal(await controller.start(request, service), false)
  assert.equal(calls, 1)
  finish({ ok: true, status: 200, response }); await first
  assert.equal(controller.getSnapshot().status, 'success')
  assert.equal(controller.getSnapshot().response, response)
  assert.deepEqual(response, before)
  assert.equal(controller.getSnapshot().context.data_mode, 'api')
})
for (const [code, extra] of [
  ['VALIDATION_ERROR', { httpStatus: 422, canRetry: false, fields: { destination_city: 'Choose a different city.' } }],
  ['UNSUPPORTED_LOCATION', { httpStatus: 400, canRetry: false, fields: { departure_city: 'Choose a supported city.' } }],
  ['UNAUTHORIZED', { httpStatus: 401, canRetry: false, signIn: true }],
  ['SESSION_EXPIRED', { canRetry: false, signIn: true }],
  ['NETWORK_ERROR', {}], ['PROVIDER_UNAVAILABLE', { httpStatus: 503 }],
  ['AI_GENERATION_FAILED', { httpStatus: 502 }], ['GENERATION_TIMEOUT', { httpStatus: 504 }],
]) test(`real ${code} preserves inputs and safe details without automatic retry`, async () => {
  const input = structuredClone(request)
  let calls = 0
  const outcome = safeFailure(code, extra)
  const controller = new GenerationController(() => null)
  const service = validatedService(async () => { calls++; return outcome })
  await controller.start(input, service)
  assert.equal(calls, 1)
  assert.deepEqual(input, request)
  assert.deepEqual(controller.getSnapshot().request, request)
  assert.equal(controller.getSnapshot().error, outcome.error)
  if (!outcome.error.canRetry) {
    assert.equal(await controller.start(input, service), false)
    controller.cancel() // Edit action re-enables submission with preserved form inputs.
  }
  assert.equal(calls, 1)
  await controller.start(input, service) // Only this deliberate action can send again.
  assert.equal(calls, 2)
})
test('real rate limit survives edit and expires without firing generation automatically', async () => {
  let now = 1000, calls = 0
  const controller = new GenerationController(() => null, () => now)
  const service = validatedService(async () => { calls++; return safeFailure('RATE_LIMITED', { httpStatus: 429, retryAt: 61000 }) })
  await controller.start(request, service)
  controller.cancel()
  assert.equal(await controller.start(request, service), false)
  now = 61000
  assert.equal(calls, 1)
  assert.equal(await controller.start(request, service), true)
  assert.equal(calls, 2)
})
test('late real success after cancel/unmount cannot publish or replace retained state', async () => {
  let finish
  const controller = new GenerationController(() => null)
  const running = controller.start(request, validatedService(() => new Promise(resolve => { finish = resolve })))
  controller.cancel()
  finish({ ok: true, status: 200, response: readFixture('within-budget.json') })
  await running
  assert.equal(controller.getSnapshot().status, 'idle')
})
