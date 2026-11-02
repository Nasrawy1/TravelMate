import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { mkdir, readFile, unlink, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { build } from 'vite'

import { validateGenerationResponse, validGenerationRequest } from '../src/services/generationValidation.ts'
const cache = new URL('../node_modules/.cache/', import.meta.url)
await mkdir(cache, { recursive: true })
const compiled = new URL(`trip-generation-${process.pid}.mjs`, cache)
const output = await build({ root: fileURLToPath(new URL('../', import.meta.url)), envDir: false, configFile: false, logLevel: 'silent', plugins: [{ name: 'boundary-test-entry', resolveId(id) { if (id.endsWith('boundary-test-entry')) return 'boundary-test-entry' }, load(id) { if (id === 'boundary-test-entry') return "export { createApiClient } from '/src/services/apiClient.ts'; export { createTripGenerationApi } from '/src/services/tripGenerationApi.ts';" } }], build: { ssr: 'boundary-test-entry', write: false, minify: false } })
await writeFile(compiled, output.output.find(i => i.type === 'chunk' && i.isEntry).code)
after(() => unlink(compiled))
const { createTripGenerationApi, createApiClient } = await import(compiled.href)
const read = async name => JSON.parse(await readFile(new URL(`../../docs/fixtures/${name}`, import.meta.url), 'utf8'))
const manifest = await read('manifest.json')
const request = await read('request.json')
const sample = await read('within-budget.json')
const now = Date.parse('2026-10-15T00:00:00Z')
const options = () => ({ signal: new AbortController().signal })
for (const [submitted, returned] of [
  [1500.129, 1500.13], [1500.125, 1500.12], [1500.135, 1500.14],
  [1500.1249, 1500.12], [1500.1251, 1500.13],
  [1.005, 1], [1.015, 1.02], [1.0049999999999997, 1], [1.0050000000000001, 1.01],
  [0.0051, 0.01], [0.015, 0.02], [1.2345e3, 1234.5], [1.2345e-2, 0.01],
  [1e21, 1e21], [1e25, 1e25], [9.999999999999999e25, 9.999999999999999e25],
]) test(`half-even budget echo accepted: ${submitted} -> ${returned}, payload unchanged`, async () => {
  const input = { ...request, budget_usd: submitted }
  const body = structuredClone(sample)
  body.budget.budget_usd = returned
  const before = structuredClone(body), inputBefore = structuredClone(input)
  assert.equal(validateGenerationResponse(body, input), body)
  let calls = 0
  const service = createTripGenerationApi({ request: async (_path, options) => {
    calls++
    assert.deepEqual(options.body, inputBefore)
    return { status: 200, body }
  } }, () => now)
  const result = await service.generate(input, options())
  assert.equal(result.ok, true)
  assert.equal(result.response, body)
  assert.deepEqual(body, before) // Includes totals, expenses, taxes, estimates and status.
  assert.deepEqual(input, inputBefore)
  assert.equal(calls, 1)
})
for (const [submitted, returned] of [
  [1500.129, 1500.12], [1500.129, 1500.14], [1500.129, 1600],
  [1500.125, 1500.13], [1500.135, 1500.13], [1.005, 1.01], [1.015, 1.01],
  [1500.129, 1500.129], [1500.129, 1500.1301],
  [1500.129, '1500.13'], [1500.129, null], [1500.129, NaN], [1500.129, Infinity],
  [0.004, 0.01], [0.005, 0.01], [1e-7, 0.01], [Number.MIN_VALUE, 0.01],
  [1e26, 1e26], [1e28, 1e28], [Number.MAX_VALUE, Number.MAX_VALUE],
]) test(`invalid or mismatched budget echo rejected: ${submitted} -> ${returned}`, async () => {
  const input = { ...request, budget_usd: submitted }
  const body = structuredClone(sample)
  body.budget.budget_usd = returned
  assert.equal(validateGenerationResponse(body, input), null)
  let calls = 0
  const service = createTripGenerationApi({ request: async () => {
    calls++
    return { status: 200, body }
  } }, () => now)
  const result = await service.generate(input, options())
  assert.equal(result.ok, false)
  assert.equal(result.error.code, 'INVALID_RESPONSE')
  assert.equal(calls, 1)
})
test('nonpositive and nonfinite submitted budgets cannot match a valid response', () => {
  for (const budget of [0, -1, -0.005, NaN, Infinity, -Infinity]) {
    assert.equal(validateGenerationResponse(sample, { ...request, budget_usd: budget }), null)
  }
})
for (const c of manifest.cases.filter(c => c.schema === 'response')) {
  test(`valid ${c.file}: exact backend payload retained, including null and explicit zero`, async () => {
    const body = await read(c.file), before = structuredClone(body)
    assert.equal(validateGenerationResponse(body, c.request), body)
    assert.deepEqual(body, before)
    const result = await createTripGenerationApi({ request: async () => ({ status: 200, body }) }, () => now).generate(c.request, options())
    assert.equal(result.ok, true); assert.deepEqual(result.response, before)
  })
}
const mutations = [
  r => { r.unexpected = true }, r => { delete r.warnings }, r => { r.budget.selected_flight_offer_id = 'absent' },
  r => { r.itinerary.pop() }, r => { r.itinerary[0].date = '2026-02-30' },
  r => { r.travel_options.hotels.offers[0].occupancy_adults = 4 },
  r => { r.travel_options.flights.offers[0].retrieved_at = '2026-02-30T12:00:00Z' },
  r => { r.budget.cost_items.push(structuredClone(r.budget.cost_items[0])) },
  r => { r.budget.cost_items[0].amount_usd = null }, r => { r.budget.provider_subtotal_usd = Infinity },
  r => { r.trip.departure_city = 'another city' }, r => { r.travel_options.flights.status = 'unavailable' },
]
for (const [index, mutate] of mutations.entries()) test(`malformed response rejected ${index + 1}`, () => {
  const body = structuredClone(sample); mutate(body)
  assert.equal(validateGenerationResponse(body, request), null)
})
test('request validation rejects extras, invalid dates, numeric strings and blank/oversized city text', () => {
  assert.equal(validGenerationRequest(request, '2026-10-15'), true)
  for (const change of [{ user_id: 'not-allowed' }, { adults: '2' }, { start_date: '2026-02-30' }, { departure_city: ' ' }, { departure_city: 'x'.repeat(201) }, { budget_usd: Infinity }, { destination_city: request.departure_city }]) assert.equal(validGenerationRequest({ ...request, ...change }, '2026-10-15'), false)
})
function setup(status, body, headers = {}, session = true) {
  let calls = 0
  const api = createApiClient({ baseUrl: 'https://api.example.invalid', now: () => now,
    getAuth: () => ({ getSession: async () => ({ data: { session: session ? { access_token: 'UNIT.ACCESS.TEST', expires_at: now / 1000 + 3600 } : null }, error: null }) }),
    fetch: async (url, init) => {
      calls++
      assert.equal(url, 'https://api.example.invalid/api/v1/trips/generate')
      assert.equal(init.headers.get('Authorization'), 'Bearer UNIT.ACCESS.TEST')
      assert.equal(init.method, 'POST'); assert.deepEqual(JSON.parse(init.body), request)
      return new Response(JSON.stringify(body), { status, headers })
    },
  })
  return { service: createTripGenerationApi(api, () => now), count: () => calls }
}
for (const [status, code] of [[401, 'UNAUTHORIZED'], [422, 'VALIDATION_ERROR'], [400, 'UNSUPPORTED_LOCATION'], [400, 'INVALID_TRIP_DATES'], [429, 'RATE_LIMITED'], [502, 'AI_GENERATION_FAILED'], [503, 'PROVIDER_UNAVAILABLE'], [504, 'GENERATION_TIMEOUT'], [500, 'INTERNAL_ERROR']]) {
  test(`safe ${status} ${code} with field details, reference and no automatic retry`, async () => {
    const { service, count } = setup(status, { error: { code, message: 'PRIVATE_DEBUG_DO_NOT_RENDER', details: { fields: [{ field: 'destination_city', message: 'PRIVATE_DEBUG_DO_NOT_RENDER' }] } }, request_id: 'reference-123' }, { 'X-Request-ID': 'reference-123', 'Retry-After': '60' })
    const result = await service.generate(request, options())
    assert.equal(result.ok, false); assert.equal(result.error.code, code); assert.equal(result.error.httpStatus, status)
    assert.equal(result.error.requestId, 'reference-123'); assert.equal(count(), 1)
    assert.ok(!JSON.stringify(result).includes('PRIVATE_DEBUG'))
    if (status === 401) assert.equal(result.error.signIn, true)
    if ([400, 422].includes(status)) assert.ok(result.error.fields.destination_city)
    if (status === 429) assert.equal(result.error.retryAt, now + 60000)
  })
}
test('missing session never sends HTTP', async () => {
  const { service, count } = setup(200, sample, {}, false)
  const result = await service.generate(request, options())
  assert.equal(result.error.code, 'SESSION_REQUIRED'); assert.equal(result.error.signIn, true); assert.equal(count(), 0)
})
for (const status of [401, 400, 422, 429]) test(`malformed/missing-header ${status} preserves safe status action`, async () => {
  const { service } = setup(status, { debug: 'PRIVATE_DEBUG' }, { 'Retry-After': '60' })
  const { error } = await service.generate(request, options())
  assert.equal(error.httpStatus, status); assert.equal(error.requestId, undefined)
  assert.equal(error.canRetry, status === 429)
  if (status === 401) assert.equal(error.signIn, true)
  if (status === 429) assert.equal(error.retryAt, now + 60000)
})
test('successful transport uses shared auth and malformed 200 cannot become success', async () => {
  assert.equal((await setup(200, sample).service.generate(request, options())).ok, true)
  assert.equal((await setup(200, { generation_status: 'complete' }).service.generate(request, options())).error.code, 'INVALID_RESPONSE')
})
test('schema vocabulary remains covered by the dependency-free shape validator', async () => {
  const schema = JSON.parse(await readFile(new URL('../../docs/contracts/api-v0.4.schema.json', import.meta.url), 'utf8'))
  const keys = new Set(['type', 'enum', 'anyOf', 'properties', 'required', 'additionalProperties', 'items', 'uniqueItems', 'minimum', 'maximum', 'exclusiveMinimum', 'minLength', 'maxLength', 'pattern', 'format', 'description'])
  function visit(s) {
    for (const key of Object.keys(s)) assert.ok(keys.has(key), `unsupported schema keyword: ${key}`)
    Object.values(s.properties ?? {}).forEach(visit)
    s.anyOf?.forEach(visit); if (s.items) visit(s.items)
  }
  Object.values(schema.$defs).forEach(visit)
})



test('backend totals and selected offers are not recalculated or replaced', () => {
  const body = structuredClone(sample)
  body.budget.provider_subtotal_usd = 123.45
  assert.equal(validateGenerationResponse(body, request), body)
  assert.equal(body.budget.provider_subtotal_usd, 123.45)
})
test('network and cancellation failures are safe and never replayed', async () => {
  for (const code of ['NETWORK_ERROR', 'ABORTED', 'SESSION_EXPIRED']) {
    let calls = 0
    const api = createApiClient({ baseUrl: 'https://api.example.invalid', now: () => now,
      getAuth: () => ({ getSession: async () => ({ data: { session: null }, error: { status: 401 } }) }),
      fetch: async () => { calls++; throw new Error('PRIVATE_DEBUG') },
    })
    const signal = new AbortController()
    if (code === 'ABORTED') signal.abort()
    const client = code === 'NETWORK_ERROR' ? createApiClient({ baseUrl: 'https://api.example.invalid', now: () => now,
      getAuth: () => ({ getSession: async () => ({ data: { session: { access_token: 'UNIT.ACCESS.TEST', expires_at: now / 1000 + 3600 } }, error: null }) }),
      fetch: async () => { calls++; throw new Error('PRIVATE_DEBUG') },
    }) : api
    const result = await createTripGenerationApi(client, () => now).generate(request, { signal: signal.signal })
    assert.equal(result.error.code, code); assert.ok(!JSON.stringify(result).includes('PRIVATE_DEBUG'))
    assert.equal(calls, code === 'NETWORK_ERROR' ? 1 : 0)
  }
})
