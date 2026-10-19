// Synthetic SDK/fetch doubles only; no configured Supabase client or live API.
import assert from 'node:assert/strict'
import test from 'node:test'
import { ApiError, createApiClient, readApiOrigin } from '../src/services/apiClient.ts'

const now = 1_000_000
const session = (token = 'UNIT.ACCESS.ONE', expires = now / 1000 + 3600) => ({ access_token: token, expires_at: expires })
const reference = '12345678-1234-4234-8234-123456789abc'
const json = (body, status = 200, headers = {}) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } })
function setup(overrides = {}) {
  const calls = { auth: 0, sessions: 0, refreshes: 0, http: [] }
  const auth = {
    getSession: async () => { calls.sessions++; return { data: { session: session() }, error: null } },
    refreshSession: async () => { calls.refreshes++; return { data: { session: session('UNIT.ACCESS.REFRESHED') }, error: null } },
  }
  const api = createApiClient({ baseUrl: 'https://api.example.invalid', now: () => now,
    getAuth: () => { calls.auth++; return auth },
    fetch: async (url, init) => { calls.http.push({ url, init }); return json({ test_only: true }) },
    ...overrides,
  })
  return { api, calls, auth }
}

test('trusted API config accepts HTTPS/loopback origins and rejects credentials, paths and unsafe URLs', () => {
  for (const origin of ['https://api.example.invalid', 'http://localhost:8000', 'http://127.0.0.1:8000', 'http://[::1]:8000']) assert.equal(readApiOrigin(origin), origin)
  for (const value of [undefined, '', '<fastapi-origin>', 'http://api.example.invalid', '//api.example.invalid', 'https://user:password@api.example.invalid', 'https://api.example.invalid/api/v1', 'https://api.example.invalid/?key=value', 'https://api.example.invalid/#value', 'javascript:alert(1)']) assert.equal(readApiOrigin(value), null)
})

test('construction and public health requests never initialize Auth or attach Authorization', async () => {
  const { api, calls } = setup({ getAuth: () => { throw new Error('AUTH_MUST_NOT_INITIALIZE') } })
  assert.equal(calls.http.length, 0)
  const result = await api.request('/api/v1/health', { auth: 'none' })
  assert.equal(calls.http[0].init.headers.has('Authorization'), false)
  assert.equal(calls.sessions, 0)
  assert.deepEqual(result.body, { test_only: true })
})

test('protected requests get the current token each time and prevent redirects/cookies/cache/referrer leakage', async () => {
  const { api, auth, calls } = setup()
  await api.request('/unit-test-only')
  auth.getSession = async () => { calls.sessions++; return { data: { session: session('UNIT.ACCESS.TWO') }, error: null } }
  await api.request('/unit-test-only')
  assert.equal(calls.sessions, 2)
  assert.equal(calls.http[0].init.headers.get('Authorization'), 'Bearer UNIT.ACCESS.ONE')
  assert.equal(calls.http[1].init.headers.get('Authorization'), 'Bearer UNIT.ACCESS.TWO')
  for (const { url, init } of calls.http) {
    assert.equal(new URL(url).origin, 'https://api.example.invalid')
    assert.equal(init.credentials, 'omit'); assert.equal(init.redirect, 'error')
    assert.equal(init.cache, 'no-store'); assert.equal(init.referrerPolicy, 'no-referrer')
    assert.equal(init.mode, 'cors'); assert.equal(url.includes('UNIT.ACCESS'), false)
    assert.equal(init.body, undefined)
  }
})

for (const path of ['https://other.example.invalid/path', '//other.example.invalid/path', '/\\other.example.invalid', 'relative', '/bad\npath', '/path#fragment']) {
  test('unsafe destination rejected before Auth or HTTP: ' + JSON.stringify(path), async () => {
    const { api, calls } = setup()
    await assert.rejects(api.request(path), { code: 'INVALID_REQUEST' })
    assert.equal(calls.auth, 0); assert.equal(calls.http.length, 0)
  })
}

test('missing API configuration fails before Auth or HTTP', async () => {
  const { api, calls } = setup({ baseUrl: '' })
  await assert.rejects(api.request('/unit-test-only'), { code: 'API_NOT_CONFIGURED' })
  assert.equal(calls.auth, 0); assert.equal(calls.http.length, 0)
})

test('missing Auth configuration and missing sessions never send a protected request', async () => {
  const missing = setup({ getAuth: () => null })
  await assert.rejects(missing.api.request('/unit-test-only'), { code: 'AUTH_NOT_CONFIGURED' })
  const { api, auth, calls } = setup()
  auth.getSession = async () => ({ data: { session: null }, error: null })
  await assert.rejects(api.request('/unit-test-only'), { code: 'SESSION_REQUIRED' })
  assert.equal(calls.http.length, 0); assert.equal(missing.calls.http.length, 0)
})

for (const expiry of [now / 1000 - 1, now / 1000 + 20]) {
  test(`expired/nearly expired sessions refresh through the SDK before HTTP: ${expiry}`, async () => {
    const { api, auth, calls } = setup()
    auth.getSession = async () => ({ data: { session: session('UNIT.ACCESS.OLD', expiry) }, error: null })
    await api.request('/unit-test-only')
    assert.equal(calls.refreshes, 1); assert.equal(calls.http.length, 1)
    assert.equal(calls.http[0].init.headers.get('Authorization'), 'Bearer UNIT.ACCESS.REFRESHED')
  })
}

for (const result of [
  { data: { session: null }, error: null },
  { data: { session: null }, error: { status: 401, message: 'RAW_PRIVATE_VALUE' } },
  { data: { session: session('UNIT.ACCESS.OLD', 1) }, error: null },
]) {
  test('unsuccessful refresh cannot send an expired token', async () => {
    const { api, auth, calls } = setup()
    auth.getSession = async () => ({ data: { session: session('UNIT.ACCESS.OLD', 1) }, error: null })
    auth.refreshSession = async () => result
    await assert.rejects(api.request('/unit-test-only'), { code: 'SESSION_EXPIRED' })
    assert.equal(calls.http.length, 0)
  })
}

test('revoked refresh credentials and Auth transport failures are safe and never sent to FastAPI', async () => {
  const { api, auth, calls } = setup()
  auth.getSession = async () => ({ data: { session: null }, error: { status: 400, code: 'refresh_token_not_found' } })
  await assert.rejects(api.request('/unit-test-only'), { code: 'SESSION_EXPIRED' })
  auth.getSession = async () => { throw new Error('RAW_PRIVATE_VALUE') }
  await assert.rejects(api.request('/unit-test-only'), error => error.code === 'AUTH_UNAVAILABLE' && !String(error).includes('RAW_PRIVATE_VALUE'))
  assert.equal(calls.http.length, 0)
})

test('malformed/missing token or expiry fails closed', async () => {
  const { api, auth, calls } = setup()
  for (const value of [session('bad\r\nvalue'), session(''), { access_token: 'UNIT.ACCESS.ONE' }, session('UNIT.ACCESS.ONE', NaN)]) {
    auth.getSession = async () => ({ data: { session: value }, error: null })
    await assert.rejects(api.request('/unit-test-only'), ApiError)
  }
  assert.equal(calls.http.length, 0)
})

for (const response of [json({ error: { code: 'UNAUTHORIZED', message: 'RAW_PRIVATE_VALUE', details: null }, request_id: reference }, 401, { 'X-Request-ID': reference }), new Response('invalid body', { status: 401 })]) {
  test('API 401 stays unauthorized with valid or malformed envelopes; no refresh/replay/signout', async () => {
    let requests = 0
    const { api, auth, calls } = setup({ fetch: async () => { requests++; return response } })
    auth.signOut = () => { throw new Error('SIGNOUT_FORBIDDEN') }
    await assert.rejects(api.request('/unit-test-only'), error => error.code === 'UNAUTHORIZED' && error.status === 401 && !JSON.stringify(error).includes('RAW_PRIVATE_VALUE'))
    assert.equal(requests, 1); assert.equal(calls.refreshes, 0)
  })
}

for (const status of [400, 403, 422, 429, 500, 502, 503, 504]) {
  test(`HTTP ${status} keeps status and a safe reference, never raw response messages or automatic retries`, async () => {
    let requests = 0
    const { api } = setup({ fetch: async () => { requests++; return json({ error: { message: 'RAW_PRIVATE_VALUE' } }, status, { 'X-Request-ID': reference }) } })
    await assert.rejects(api.request('/unit-test-only'), error => error.code === 'HTTP_ERROR' && error.status === status && error.requestId === reference && !String(error).includes('RAW_PRIVATE_VALUE'))
    assert.equal(requests, 1)
  })
}

test('unsafe/missing/inaccessible request IDs are omitted without hiding a 401', async () => {
  const { api } = setup({ fetch: async () => json({}, 401, { 'X-Request-ID': 'untrusted.value' }) })
  await assert.rejects(api.request('/unit-test-only'), error => error.code === 'UNAUTHORIZED' && error.requestId === undefined)
})

test('network failures have safe errors and no retries', async () => {
  let requests = 0
  const { api } = setup({ fetch: async () => { requests++; throw new Error('RAW_PRIVATE_VALUE') } })
  await assert.rejects(api.request('/unit-test-only'), error => error.code === 'NETWORK_ERROR' && !String(error).includes('RAW_PRIVATE_VALUE'))
  assert.equal(requests, 1)
})

test('cancellation is respected before Auth, during Auth and during fetch', async () => {
  const abort = new AbortController(); abort.abort()
  const { api, calls } = setup()
  await assert.rejects(api.request('/unit-test-only', { signal: abort.signal }), { code: 'ABORTED' })
  assert.equal(calls.auth, 0)
  const during = new AbortController()
  const next = setup()
  next.auth.getSession = async () => { during.abort(); return { data: { session: session() }, error: null } }
  await assert.rejects(next.api.request('/unit-test-only', { signal: during.signal }), { code: 'ABORTED' })
  assert.equal(next.calls.http.length, 0)
  const inFlight = new AbortController()
  const final = setup({ fetch: async () => { inFlight.abort(); throw new Error('Synthetic abort') } })
  await assert.rejects(final.api.request('/unit-test-only', { signal: inFlight.signal }), { code: 'ABORTED' })
})

test('JSON POST and empty success are supported; unreadable success requires adapter attention', async () => {
  const { api, calls } = setup()
  await api.request('/unit-test-only', { method: 'POST', body: { test_only: true } })
  assert.equal(calls.http[0].init.headers.get('Content-Type'), 'application/json')
  assert.equal(calls.http[0].init.body, '{"test_only":true}')
  const empty = setup({ fetch: async () => new Response(null, { status: 204 }) })
  assert.equal((await empty.api.request('/unit-test-only')).body, null)
  const invalid = setup({ fetch: async () => new Response('<html>RAW_PRIVATE_VALUE</html>') })
  await assert.rejects(invalid.api.request('/unit-test-only'), { code: 'INVALID_RESPONSE' })
})

test('invalid method/body/auth options fail before acquiring a token', async () => {
  const { api, calls } = setup()
  const cyclic = {}; cyclic.self = cyclic
  for (const options of [{ method: 'DELETE' }, { body: {} }, { method: 'POST', body: cyclic }, { auth: 'unknown' }]) await assert.rejects(api.request('/unit-test-only', options), { code: 'INVALID_REQUEST' })
  assert.equal(calls.auth, 0); assert.equal(calls.http.length, 0)
})
