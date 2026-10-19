// Explicit unit doubles: no accounts, emails, real tokens or password changes.
import assert from 'node:assert/strict'
import test from 'node:test'
import { createHash } from 'node:crypto'
import { createClient } from '@supabase/supabase-js'
import { EmailAuthController, parseEmailCallback } from '../src/services/emailAuth.ts'

const config = { url: 'https://unit.supabase.co', publishableKey: 'sb_publishable_UNIT_TEST_ONLY', appUrl: 'http://localhost:5173' }
const callback = kind => ({ kind, accessToken: 'UNIT_ACCESS', refreshToken: 'UNIT_REFRESH' })
const validUser = { id: 'unit-user', email_confirmed_at: '2026-10-17T00:00:00Z' }
function setup(t, input = callback('recovery'), overrides = {}) {
  const claims = { sub: validUser.id, exp: Math.floor(Date.now() / 1000) + 3600, session_id: 'unit-session', amr: [{ method: 'recovery', timestamp: Math.floor(Date.now() / 1000) }] }
  const session = { access_token: 'UNIT_ACCESS', refresh_token: 'UNIT_REFRESH', expires_at: claims.exp, user: validUser }
  const calls = { set: 0, updates: 0, reset: 0 }
  const auth = {
    getUser: async () => ({ data: { user: validUser }, error: null }),
    getClaims: async () => ({ data: { claims }, error: null }),
    setSession: async () => { calls.set++; return { data: { session }, error: null } },
    getSession: async () => ({ data: { session }, error: null }),
    updateUser: async input => { calls.updates++; calls.updateInput = input; return { data: { user: validUser }, error: null } },
    resetPasswordForEmail: async (email, options) => { calls.reset++; calls.resetOptions = options; return { data: {}, error: null } },
    ...overrides,
  }
  const controller = new EmailAuthController({ auth }, config, input)
  t.after(() => controller.lock())
  return { controller, auth, claims, calls, session }
}

test('implicit callbacks parse only complete unambiguous fragment credentials', () => {
  assert.equal(parseEmailCallback(new URL('http://localhost:5173/login')).kind, 'none')
  for (const type of ['signup', 'email', 'recovery']) assert.equal(parseEmailCallback(new URL(`http://localhost:5173/login#access_token=UNIT&refresh_token=UNIT&type=${type}`)).kind, type === 'recovery' ? 'recovery' : 'confirmation')
  for (const suffix of ['#type=recovery&access_token=UNIT', '#access_token=UNIT&refresh_token=UNIT', '#access_token=UNIT&access_token=OTHER&refresh_token=UNIT&type=recovery', '?access_token=UNIT', '?code=', '#token_hash=UNIT&type=recovery', '#access_token=UNIT&refresh_token=UNIT&type=invite']) assert.equal(parseEmailCallback(new URL(`http://localhost:5173/login${suffix}`)).kind, 'invalid')
})

for (const code of ['otp_expired', 'access_denied', 'invalid_token']) test(`expired/reused callback ${code} cannot use an existing ordinary session`, async t => {
  const parsed = parseEmailCallback(new URL(`http://localhost:5173/login#error=access_denied&error_code=${code}&error_description=RAW_DEBUG`))
  const { controller, calls } = setup(t, parsed)
  await controller.process()
  assert.equal(controller.getSnapshot().callback, 'invalid'); assert.equal(calls.set, 0)
  await assert.rejects(controller.updatePassword('UnitPassword1'), { code: 'unauthorized' })
  assert.equal(calls.updates, 0); assert.ok(!JSON.stringify(controller.getSnapshot()).includes('RAW_DEBUG'))
})

test('confirmation verifies identity/claims and establishes a session exactly once, without granting recovery', async t => {
  const { controller, calls } = setup(t, callback('confirmation'))
  await Promise.all([controller.process(), controller.process()])
  assert.equal(controller.getSnapshot().callback, 'confirmed'); assert.equal(calls.set, 1)
  await assert.rejects(controller.updatePassword('UnitPassword1'), { code: 'unauthorized' })
  assert.equal(calls.updates, 0)
})

test('valid recovery claims authorize one real SDK update and consume the in-memory grant', async t => {
  const { controller, calls } = setup(t)
  await controller.process(); assert.equal(controller.getSnapshot().recovery, 'ready')
  await controller.updatePassword('UnitPassword1')
  assert.deepEqual(calls.updateInput, { password: 'UnitPassword1' })
  assert.equal(controller.getSnapshot().recovery, 'complete')
  await assert.rejects(controller.updatePassword('UnitPassword2'), { code: 'unauthorized' })
  await controller.process(); assert.equal(controller.getSnapshot().recovery, 'complete'); assert.equal(calls.updates, 1)
  assert.ok(!JSON.stringify(controller.getSnapshot()).includes('UNIT_ACCESS'))
})

test('confirmed update clears callback navigation, consumes recovery and preserves the SDK session', async t => {
  const { controller, auth, session, calls } = setup(t)
  let signouts = 0
  auth.signOut = async () => { signouts++; return { error: null } }
  await controller.process()
  await controller.updatePassword('UnitPassword1')
  assert.deepEqual(controller.getSnapshot(), { callback: 'none', recovery: 'complete', error: null })
  // EmailAuthProvider performs these operations when leaving /reset-password.
  controller.dismissCallback(); controller.lock()
  assert.equal(controller.getSnapshot().callback, 'none')
  assert.equal(controller.getSnapshot().recovery, 'complete')
  assert.equal((await auth.getSession()).data.session, session)
  assert.equal(signouts, 0); assert.equal(calls.reset, 0)
  await assert.rejects(controller.updatePassword('UnitPassword2'), { code: 'unauthorized' })
  assert.equal(calls.updates, 1)
  // A reload creates a new controller; an ordinary stored session cannot restore the grant.
  const reloaded = new EmailAuthController({ auth }, config)
  await reloaded.process()
  assert.equal(reloaded.getSnapshot().recovery, 'locked')
  await assert.rejects(reloaded.updatePassword('UnitPassword2'), { code: 'unauthorized' })
})

for (const failure of ['provider_error', 'network_failure', 'missing_user', 'wrong_user', 'unauthorized']) {
  test(`password update ${failure} never publishes completion`, async t => {
    const { controller, auth } = setup(t)
    await controller.process()
    const states = []
    const unsubscribe = controller.subscribe(() => states.push(controller.getSnapshot().recovery))
    t.after(unsubscribe)
    auth.updateUser = async () => {
      if (failure === 'network_failure') throw new TypeError('SYNTHETIC_NETWORK_ERROR')
      if (failure === 'provider_error') return { data: { user: validUser }, error: { code: 'weak_password' } }
      if (failure === 'unauthorized') return { data: { user: null }, error: { status: 401 } }
      return { data: { user: failure === 'wrong_user' ? { id: 'different-user' } : null }, error: null }
    }
    await assert.rejects(controller.updatePassword('UnitPassword1'))
    assert.ok(!states.includes('complete'))
    assert.equal(controller.getSnapshot().recovery, failure === 'unauthorized' ? 'locked' : 'ready')
  })
}

test('authorization expiry before submission prevents an SDK update and any success state', async t => {
  t.mock.timers.enable({ apis: ['Date', 'setTimeout'], now: 1_000_000 })
  const { controller, calls } = setup(t)
  await controller.process()
  t.mock.timers.tick(15 * 60_000 + 1)
  await assert.rejects(controller.updatePassword('UnitPassword1'), { code: 'unauthorized' })
  assert.equal(controller.getSnapshot().recovery, 'locked')
  assert.equal(calls.updates, 0); assert.equal(calls.reset, 0)
})

for (const reason of ['signout', 'account_change', 'expiry', 'navigation']) {
  for (const outcome of ['success', 'provider_error', 'network_failure']) {
    test(`revoked recovery (${reason}) ignores late ${outcome} without retrying or declaring an outcome`, async t => {
      t.mock.timers.enable({ apis: ['Date', 'setTimeout'], now: 1_000_000 })
      const { controller, auth, session, calls } = setup(t)
      await controller.process()
      let settle, reject
      auth.updateUser = async () => { calls.updates++; return new Promise((resolve, fail) => { settle = resolve; reject = fail }) }
      const pending = controller.updatePassword('UnitPassword1')
      for (let n = 0; n < 20 && !settle; n++) await Promise.resolve()
      assert.equal(typeof settle, 'function')
      assert.equal(controller.getSnapshot().recovery, 'updating')
      if (reason === 'signout') controller.observeSession(null, 'SIGNED_OUT')
      if (reason === 'account_change') controller.observeSession({ ...session, user: { ...session.user, id: 'different-test-account' } }, 'SIGNED_IN')
      if (reason === 'expiry') t.mock.timers.tick(15 * 60_000 + 1)
      if (reason === 'navigation') { controller.dismissCallback(); controller.lock() }
      const revoked = controller.getSnapshot()
      assert.equal(revoked.recovery, 'locked')
      if (outcome === 'network_failure') reject(new Error('SYNTHETIC_TRANSPORT_ERROR'))
      else settle({ data: { user: validUser }, error: outcome === 'provider_error' ? { status: 401 } : null })
      // A resolved call is not the success signal: only controller state is.
      await pending
      assert.equal(controller.getSnapshot(), revoked)
      assert.equal(calls.updates, 1); assert.equal(calls.reset, 0)
      await assert.rejects(controller.updatePassword('UnitPassword2'), { code: 'unauthorized' })
      assert.equal(calls.updates, 1)
    })
  }
}

test('late recovery completion checks the expiry deadline even if the timer has not run', async t => {
  t.mock.timers.enable({ apis: ['Date'], now: 1_000_000 })
  const { controller, auth, calls } = setup(t)
  await controller.process()
  let settle
  auth.updateUser = async () => { calls.updates++; return new Promise(resolve => { settle = resolve }) }
  const pending = controller.updatePassword('UnitPassword1')
  for (let n = 0; n < 20 && !settle; n++) await Promise.resolve()
  assert.equal(typeof settle, 'function')
  t.mock.timers.setTime(1_000_000 + 15 * 60_000 + 1)
  settle({ data: { user: validUser }, error: null })
  await pending
  assert.equal(controller.getSnapshot().recovery, 'locked')
  assert.equal(calls.updates, 1)
})

test('direct reset navigation and ordinary sign-in never grant recovery', async t => {
  const { controller, session, calls } = setup(t, { kind: 'none' })
  controller.observeSession(session, 'SIGNED_IN'); await controller.process()
  await assert.rejects(controller.updatePassword('UnitPassword1'), { code: 'unauthorized' }); assert.equal(calls.updates, 0)
})

for (const mode of ['password', 'expired', 'stale_recovery', 'future_recovery', 'missing_session_id', 'invalid_signature', 'unconfirmed', 'wrong_subject']) {
  test(`recovery rejects ${mode} before persisting credentials or updating`, async t => {
    const { controller, auth, claims, calls } = setup(t)
    if (mode === 'password') claims.amr = [{ method: 'password', timestamp: Math.floor(Date.now() / 1000) }]
    if (mode === 'expired') claims.exp = 1
    if (mode === 'stale_recovery') claims.amr[0].timestamp -= 3600
    if (mode === 'future_recovery') claims.amr[0].timestamp += 3600
    if (mode === 'missing_session_id') delete claims.session_id
    if (mode === 'wrong_subject') claims.sub = 'other'
    if (mode === 'invalid_signature') auth.getClaims = async () => ({ data: null, error: { message: 'RAW_DEBUG' } })
    if (mode === 'unconfirmed') auth.getUser = async () => ({ data: { user: { ...validUser, email_confirmed_at: null } }, error: null })
    await controller.process(); assert.equal(controller.getSnapshot().callback, 'invalid'); assert.equal(calls.set, 0)
    await assert.rejects(controller.updatePassword('UnitPassword1'), { code: 'unauthorized' }); assert.equal(calls.updates, 0)
  })
}

test('new/revoked sessions are rechecked immediately before update', async t => {
  const { controller, claims, calls } = setup(t)
  await controller.process(); claims.session_id = 'changed-session'
  await assert.rejects(controller.updatePassword('UnitPassword1'), { code: 'unauthorized' }); assert.equal(calls.updates, 0)
})

test('logout invalidates authorization and stale callback completion', async t => {
  let resolve
  const { controller, calls } = setup(t, callback('recovery'), { getUser: () => new Promise(done => { resolve = done }) })
  const pending = controller.process()
  controller.observeSession(null, 'SIGNED_OUT')
  resolve({ data: { user: validUser }, error: null })
  await pending
  await assert.rejects(controller.updatePassword('UnitPassword1'), { code: 'unauthorized' }); assert.equal(calls.updates, 0)
})

test('recovery authorization expires even if a session remains signed in', async t => {
  t.mock.timers.enable({ apis: ['Date', 'setTimeout'], now: 1_000_000 })
  const { controller, calls } = setup(t)
  await controller.process(); t.mock.timers.tick(15 * 60_000 + 1)
  assert.equal(controller.getSnapshot().recovery, 'locked')
  await assert.rejects(controller.updatePassword('UnitPassword1'), { code: 'unauthorized' }); assert.equal(calls.updates, 0)
})

test('accepted reset request is neutral, uses configured redirect, and duplicate requests share an outcome', async t => {
  let resolve
  const { controller, calls } = setup(t, { kind: 'none' }, { resetPasswordForEmail: async (email, options) => { calls.reset++; calls.resetOptions = options; return new Promise(done => { resolve = done }) } })
  const first = controller.requestReset('unit@example.com'), second = controller.requestReset('unit@example.com')
  assert.equal(first, second); assert.equal(calls.reset, 1)
  assert.deepEqual(calls.resetOptions, { redirectTo: 'http://localhost:5173/reset-password' })
  resolve({ data: {}, error: null }); await first
})

test('network/provider errors are safe and never automatically retried', async t => {
  const { controller, calls } = setup(t, { kind: 'none' }, { resetPasswordForEmail: async () => { calls.reset++; throw new Error('RAW_DEBUG') } })
  await assert.rejects(controller.requestReset('unit@example.com'), { message: 'unavailable' }); assert.equal(calls.reset, 1)
})

test('password-policy errors keep an unexpired grant available for an explicit edit/retry', async t => {
  const { controller, auth, calls } = setup(t)
  await controller.process()
  auth.updateUser = async () => ({ data: {}, error: { code: 'weak_password', message: 'RAW_DEBUG' } })
  await assert.rejects(controller.updatePassword('UnitPassword1'), { code: 'weak_password' })
  assert.equal(controller.getSnapshot().recovery, 'ready'); assert.equal(calls.updates, 0)
})

test('duplicate password submissions never call updateUser twice or report premature success', async t => {
  let resolve
  const { controller, auth, calls } = setup(t)
  await controller.process()
  auth.updateUser = async () => { calls.updates++; return new Promise(done => { resolve = done }) }
  const first = controller.updatePassword('UnitPassword1')
  await assert.rejects(controller.updatePassword('UnitPassword1'), { code: 'unavailable' })
  // Allow the first operation to finish its identity/claims verification.
  for (let n = 0; n < 10 && !resolve; n++) await Promise.resolve()
  assert.equal(controller.getSnapshot().recovery, 'updating'); assert.equal(calls.updates, 1)
  resolve({ data: { user: validUser }, error: null }); await first
  assert.equal(controller.getSnapshot().recovery, 'complete')
})

test('provider session-establishment failures do not become confirmation/recovery success', async t => {
  const { controller } = setup(t, callback('confirmation'), { setSession: async () => ({ data: { session: null }, error: { message: 'RAW_DEBUG' } }) })
  await controller.process(); assert.equal(controller.getSnapshot().callback, 'invalid')
  assert.ok(!JSON.stringify(controller.getSnapshot()).includes('RAW_DEBUG'))
})

test('rate limits map to safe manual retry guidance without revealing account existence', async t => {
  const { controller } = setup(t, { kind: 'none' }, { resetPasswordForEmail: async () => ({ error: { status: 429, message: 'RAW_DEBUG' } }) })
  await assert.rejects(controller.requestReset('unit@example.com'), { code: 'rate_limited', message: 'rate_limited' })
})

test('regression: Supabase implicit email recovery may have OTP claims and must not bypass recovery proof', async t => {
  const { controller, claims, calls } = setup(t)
  // Supabase Auth verifyGet issues the OTP method for implicit email links.
  claims.amr = [{ method: 'otp', timestamp: Math.floor(Date.now() / 1000) }]
  await controller.process()
  assert.equal(controller.getSnapshot().callback, 'invalid')
  assert.equal(calls.set, 0)
  await assert.rejects(controller.updatePassword('UnitPassword1'), { code: 'unauthorized' })
  assert.equal(calls.updates, 0)
})

test('regression: PKCE recovery exchanges the captured code once and retains verified recovery proof', async t => {
  const { controller, auth, session, calls } = setup(t, { kind: 'pkce', code: 'UNIT_CODE' })
  let exchanges = 0
  auth.exchangeCodeForSession = async code => { assert.equal(code, 'UNIT_CODE'); exchanges++; return { data: { session, redirectType: 'recovery' }, error: null } }
  await Promise.all([controller.process(), controller.process()])
  assert.equal(controller.getSnapshot().recovery, 'ready')
  assert.equal(exchanges, 1); assert.equal(calls.set, 0)
  assert.ok(!JSON.stringify(controller.getSnapshot()).includes('UNIT_CODE'))
})

test('PKCE parser preserves code/flow correlation and rejects mixed, duplicated or error callbacks', () => {
  assert.deepEqual(parseEmailCallback(new URL('http://localhost:5173/reset-password?code=UNIT_CODE&sb_flow_id=unit-flow')), { kind: 'pkce', code: 'UNIT_CODE', flowId: 'unit-flow' })
  for (const suffix of ['?code=A&code=B', '?code=UNIT&error=access_denied', '?code=UNIT#access_token=UNIT&refresh_token=UNIT&type=recovery', '?code=UNIT&sb_flow_id=a&sb_flow_id=b', '?code=UNIT&sb_flow_id=invalid%2Fflow', '?token_hash=UNIT&type=recovery']) assert.equal(parseEmailCallback(new URL(`http://localhost:5173/reset-password${suffix}`)).kind, 'invalid')
})

test('scrubbed PKCE flow id is passed explicitly to the SDK', async t => {
  const { controller, auth, session } = setup(t, { kind: 'pkce', code: 'UNIT_CODE', flowId: 'unit-flow' })
  auth.exchangeCodeForSession = async (code, options) => { assert.equal(code, 'UNIT_CODE'); assert.deepEqual(options, { flowId: 'unit-flow' }); return { data: { session }, error: null } }
  await controller.process(); assert.equal(controller.getSnapshot().recovery, 'ready')
})

for (const code of ['flow_state_expired', 'flow_state_not_found', 'bad_code_verifier', 'pkce_code_verifier_not_found']) {
  test(`PKCE ${code} fails closed despite an existing authenticated session`, async t => {
    const { controller, auth, calls } = setup(t, { kind: 'pkce', code: 'UNIT_CODE' })
    auth.exchangeCodeForSession = async () => ({ data: { session: null }, error: { code, message: 'RAW_DEBUG' } })
    await controller.process(); assert.equal(controller.getSnapshot().callback, 'invalid')
    await assert.rejects(controller.updatePassword('UnitPassword1'), { code: 'unauthorized' }); assert.equal(calls.updates, 0)
    assert.ok(!JSON.stringify(controller.getSnapshot()).includes('RAW_DEBUG'))
  })
}

test('PKCE confirmation and a forged recovery event cannot grant password reset from ordinary claims', async t => {
  const { controller, auth, session, claims, calls } = setup(t, { kind: 'pkce', code: 'UNIT_CODE' })
  claims.amr = [{ method: 'password', timestamp: Math.floor(Date.now() / 1000) }]
  auth.exchangeCodeForSession = async () => { controller.observeSession(session, 'PASSWORD_RECOVERY'); return { data: { session }, error: null } }
  await controller.process(); assert.equal(controller.getSnapshot().callback, 'confirmed')
  await assert.rejects(controller.updatePassword('UnitPassword1'), { code: 'unauthorized' }); assert.equal(calls.updates, 0)
})

test('installed SDK mock HTTP: reset creates PKCE proof, code exchange emits recovery and passes the gate', async t => {
  // All HTTP is intercepted here. No request reaches a real Supabase project.
  const storage = new Map()
  let challenge, exchanged = 0, eventSeen = false
  const payload = { sub: validUser.id, aud: 'authenticated', role: 'authenticated', iss: `${config.url}/auth/v1`, iat: Math.floor(Date.now() / 1000), exp: Math.floor(Date.now() / 1000) + 3600, session_id: 'unit-session', amr: [{ method: 'recovery', timestamp: Math.floor(Date.now() / 1000) }] }
  const encode = value => Buffer.from(JSON.stringify(value)).toString('base64url')
  const token = `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode(payload)}.${Buffer.alloc(32).toString('base64url')}`
  const json = body => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  const client = createClient(config.url, config.publishableKey, {
    auth: { flowType: 'pkce', detectSessionInUrl: false, autoRefreshToken: false, persistSession: true, storage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => { storage.set(key, value) }, removeItem: key => { storage.delete(key) } } },
    global: { fetch: async (input, init) => {
      const url = new URL(String(input))
      if (url.pathname === '/auth/v1/recover') {
        const body = JSON.parse(init.body); challenge = body.code_challenge
        assert.equal(body.code_challenge_method, 's256'); assert.ok(challenge)
        assert.equal(url.searchParams.get('redirect_to'), `${config.appUrl}/reset-password`); return json({})
      }
      if (url.pathname === '/auth/v1/token') {
        const body = JSON.parse(init.body); exchanged++
        assert.equal(url.searchParams.get('grant_type'), 'pkce'); assert.equal(body.auth_code, 'UNIT_CODE')
        assert.equal(createHash('sha256').update(body.code_verifier).digest('base64url'), challenge)
        return json({ access_token: token, refresh_token: 'UNIT_REFRESH', token_type: 'bearer', expires_in: 3600, user: validUser })
      }
      if (url.pathname === '/auth/v1/user') return json(validUser)
      throw new Error('Unexpected mock HTTP path')
    } },
  })
  const listener = client.auth.onAuthStateChange(event => { if (event === 'PASSWORD_RECOVERY') eventSeen = true })
  const controller = new EmailAuthController(client, config, { kind: 'pkce', code: 'UNIT_CODE' })
  t.after(() => { controller.lock(); listener.data.subscription.unsubscribe(); client.auth.stopAutoRefresh() })
  await controller.requestReset('unit@example.com')
  await Promise.all([controller.process(), controller.process()])
  assert.equal(exchanged, 1); assert.equal(eventSeen, true)
  assert.equal(controller.getSnapshot().recovery, 'ready')
})
