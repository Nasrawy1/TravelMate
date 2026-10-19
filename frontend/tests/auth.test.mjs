// SDK responses here are unit doubles, never real accounts or live Auth evidence.
import assert from 'node:assert/strict'
import test from 'node:test'
import { readAuthConfig } from '../src/services/authConfig.ts'
import { createAuthActions, AuthError } from '../src/services/authActions.ts'
import { AuthSessionController, safeDisplayName } from '../src/services/authSession.ts'

const config = { url: 'https://unit.supabase.co', publishableKey: 'sb_publishable_UNIT_TEST_ONLY', appUrl: 'http://localhost:5173' }
const env = { VITE_SUPABASE_URL: config.url, VITE_SUPABASE_PUBLISHABLE_KEY: config.publishableKey, VITE_APP_URL: config.appUrl }
const user = { id: 'unit-user', email: 'unit@example.com', email_confirmed_at: '2026-10-17T00:00:00Z' }
const session = () => ({ access_token: 'UNIT_TOKEN_DO_NOT_RENDER', user, expires_at: Math.floor(Date.now() / 1000) + 3600 })
const tick = () => new Promise(resolve => setTimeout(resolve, 5))
function client(overrides = {}) {
  let callback
  const calls = { stop: 0, start: 0, unsubscribe: 0, verified: [] }
  const sdk = { auth: {
    getSession: async () => ({ data: { session: null }, error: null }),
    getUser: async token => { calls.verified.push(token); return { data: { user }, error: null } },
    signOut: async options => { calls.signOut = options; callback?.('SIGNED_OUT', null); return { error: null } },
    onAuthStateChange: fn => { callback = fn; return { data: { subscription: { unsubscribe: () => { calls.unsubscribe++ } } } } },
    startAutoRefresh: () => { calls.start++ }, stopAutoRefresh: () => { calls.stop++ }, ...overrides,
  } }
  return { sdk, calls, emit: (event, value) => callback(event, value) }
}

test('public configuration accepts configured origins and rejects placeholders/elevated keys', () => {
  assert.deepEqual(readAuthConfig(env), config)
  assert.equal(readAuthConfig({}), null)
  for (const key of ['', '<supabase-publishable-key>', 'sb_secret_UNIT', 'eyJlegacy-role-key']) assert.equal(readAuthConfig({ ...env, VITE_SUPABASE_PUBLISHABLE_KEY: key }), null)
  for (const appUrl of ['javascript:alert(1)', 'https://user:password@example.com', 'http://example.com', 'http://localhost:5173/?token=unsafe']) assert.equal(readAuthConfig({ ...env, VITE_APP_URL: appUrl }), null)
})

test('display names accept plain international names and reject emails, markup and excessive metadata', () => {
  for (const name of ['Diyar', 'علي', 'José O’Neill', 'Anne-Marie']) assert.equal(safeDisplayName(name), name)
  assert.equal(safeDisplayName('  Diyar   Test  '), 'Diyar Test')
  for (const value of [undefined, null, {}, 5, '', ' ', 'unit@example.com', '<script>debug</script>', 'x'.repeat(49), 'Name\u202Etext']) assert.equal(safeDisplayName(value), null)
})

test('identity presentation uses verified metadata, excludes email and never trusts stored metadata', async () => {
  const current = session()
  current.user = { ...user, user_metadata: { display_name: 'Stored name' } }
  const { sdk } = client({ getSession: async () => ({ data: { session: current }, error: null }), getUser: async () => ({ data: { user: { ...user, user_metadata: { display_name: 'Verified name' } } }, error: null }) })
  const controller = new AuthSessionController(sdk), stop = controller.start()
  await tick()
  assert.deepEqual(controller.getSnapshot().user, { id: user.id, displayName: 'Verified name' })
  assert.ok(!JSON.stringify(controller.getSnapshot()).includes(user.email)); stop()
})

test('missing configuration never invokes an SDK method', async () => {
  const actions = createAuthActions(null, null)
  await assert.rejects(actions.signIn({ email: 'unit@example.com', password: 'unit' }), { code: 'not_configured' })
  await assert.rejects(actions.signUp({ name: 'Unit', email: 'unit@example.com', password: 'unit' }), { code: 'not_configured' })
  const controller = new AuthSessionController(null)
  const stop = controller.start()
  assert.deepEqual(controller.getSnapshot(), { status: 'not_configured', user: null }); stop()
})

test('signup sends display metadata and reports confirmation required without claiming a session', async () => {
  let sent
  const { sdk } = client({ signUp: async input => { sent = input; return { data: { user, session: null }, error: null } } })
  const outcome = await createAuthActions(sdk, config).signUp({ name: 'Unit', email: 'unit@example.com', password: 'UnitPassword1' })
  assert.equal(outcome, 'confirmation_required')
  assert.deepEqual(sent, { email: 'unit@example.com', password: 'UnitPassword1', options: { data: { display_name: 'Unit' }, emailRedirectTo: 'http://localhost:5173/login' } })
})

test('login passes credentials only to the SDK and requires a real returned session', async () => {
  const credentials = { email: 'unit@example.com', password: 'UnitPassword1' }
  const { sdk } = client({ signInWithPassword: async input => { assert.deepEqual(input, credentials); return { data: { session: session() }, error: null } } })
  await createAuthActions(sdk, config).signIn(credentials)
  sdk.auth.signInWithPassword = async () => ({ data: { session: null }, error: null })
  await assert.rejects(createAuthActions(sdk, config).signIn(credentials), { code: 'unavailable' })
})

test('signup does not convert an absent user into confirmation success or a returned session into verified identity', async () => {
  const { sdk } = client({ signUp: async () => ({ data: { user: null, session: null }, error: null }) })
  const actions = createAuthActions(sdk, config)
  const details = { name: 'Unit', email: 'unit@example.com', password: 'UnitPassword1' }
  await assert.rejects(actions.signUp(details), { code: 'unavailable' })
  sdk.auth.signUp = async () => ({ data: { user, session: session() }, error: null })
  assert.equal(await actions.signUp(details), 'session_received')
  // Only the separately verified session controller may publish authenticated UI.
})

for (const [code, status, expected] of [['invalid_credentials', 400, 'invalid_credentials'], ['email_not_confirmed', 400, 'email_not_confirmed'], ['weak_password', 422, 'weak_password'], ['unknown', 429, 'rate_limited'], ['user_already_exists', 400, 'unavailable']]) {
  test(`safe SDK error mapping: ${code}`, async () => {
    const { sdk } = client({ signInWithPassword: async () => ({ data: {}, error: { code, status, message: 'SECRET_RAW_MESSAGE' } }) })
    await assert.rejects(createAuthActions(sdk, config).signIn({ email: '', password: '' }), error => error instanceof AuthError && error.code === expected && !String(error).includes('SECRET_RAW_MESSAGE'))
  })
}

test('transport exceptions never expose credentials or raw provider messages', async () => {
  const { sdk } = client({ signUp: async () => { throw new Error('SECRET_RAW_MESSAGE') } })
  await assert.rejects(createAuthActions(sdk, config).signUp({ name: '', email: '', password: '' }), { message: 'unavailable' })
})

test('stored sessions remain checking until verified by getUser; snapshots never contain tokens', async () => {
  let resolve
  const { sdk, calls } = client({ getSession: async () => ({ data: { session: session() }, error: null }), getUser: () => new Promise(done => { resolve = done }) })
  const controller = new AuthSessionController(sdk), stop = controller.start()
  await tick()
  assert.equal(controller.getSnapshot().status, 'checking')
  resolve({ data: { user }, error: null }); await tick()
  assert.deepEqual(controller.getSnapshot(), { status: 'authenticated', user: { id: user.id, displayName: null } })
  assert.ok(!JSON.stringify(controller.getSnapshot()).includes('UNIT_TOKEN'))
  stop(); assert.equal(calls.unsubscribe, 1); assert.equal(calls.stop, 1)
})

test('refresh events reverify outside the SDK callback; signout clears identity', async () => {
  const { sdk, calls, emit } = client()
  const controller = new AuthSessionController(sdk), stop = controller.start()
  await tick(); assert.equal(controller.getSnapshot().status, 'anonymous')
  emit('TOKEN_REFRESHED', session())
  assert.equal(controller.getSnapshot().status, 'checking'); assert.equal(calls.verified.length, 0)
  await tick(); assert.equal(controller.getSnapshot().status, 'authenticated')
  assert.equal(await controller.signOut(), true)
  assert.deepEqual(calls.signOut, { scope: 'local' })
  assert.equal(controller.getSnapshot().status, 'anonymous'); stop()
})

test('expired, unconfirmed, mismatched and revoked identities never authenticate', async () => {
  for (const scenario of ['expired', 'unconfirmed', 'mismatched', 'revoked']) {
    const current = session()
    if (scenario === 'expired') current.expires_at = 1
    const { sdk } = client({ getSession: async () => ({ data: { session: current }, error: null }), getUser: async () => ({ data: { user: { ...user, id: scenario === 'mismatched' ? 'other' : user.id, email_confirmed_at: scenario === 'unconfirmed' ? null : user.email_confirmed_at } }, error: scenario === 'revoked' ? { status: 401 } : null }) })
    const controller = new AuthSessionController(sdk), stop = controller.start()
    await tick(); assert.notEqual(controller.getSnapshot().status, 'authenticated'); assert.equal(controller.getSnapshot().user, null); stop()
  }
})

test('cleanup rejects stale verification and supports StrictMode remount', async () => {
  let resolve
  const { sdk } = client({ getSession: async () => ({ data: { session: session() }, error: null }), getUser: () => new Promise(done => { resolve = done }) })
  const controller = new AuthSessionController(sdk)
  const stop = controller.start(); await tick(); stop()
  resolve({ data: { user }, error: null }); await tick()
  assert.notEqual(controller.getSnapshot().status, 'authenticated')
  sdk.auth.getSession = async () => ({ data: { session: null }, error: null })
  const stopAgain = controller.start(); await tick()
  assert.equal(controller.getSnapshot().status, 'anonymous'); stopAgain()
})

test('a later signout cannot be overwritten by an earlier getUser response', async () => {
  let resolve
  const { sdk, emit } = client({ getUser: () => new Promise(done => { resolve = done }) })
  const controller = new AuthSessionController(sdk), stop = controller.start(); await tick()
  emit('SIGNED_IN', session()); await tick()
  emit('SIGNED_OUT', null)
  resolve({ data: { user }, error: null }); await tick()
  assert.equal(controller.getSnapshot().status, 'anonymous'); stop()
})

test('a verified identity is removed when its session expires without a refresh', async t => {
  t.mock.timers.enable({ apis: ['Date', 'setTimeout'], now: 1_000_000 })
  const current = session()
  current.expires_at = (Date.now() + 1000) / 1000
  const { sdk } = client({ getSession: async () => ({ data: { session: current }, error: null }) })
  const controller = new AuthSessionController(sdk), stop = controller.start()
  await controller.refresh(); assert.equal(controller.getSnapshot().status, 'authenticated')
  t.mock.timers.tick(1001)
  assert.deepEqual(controller.getSnapshot(), { status: 'expired', user: null }); stop()
})

test('logout errors never claim signout succeeded or retain a verified UI identity', async () => {
  const { sdk } = client({ getSession: async () => ({ data: { session: session() }, error: null }), signOut: async () => ({ error: { message: 'SECRET_RAW_MESSAGE' } }) })
  const controller = new AuthSessionController(sdk), stop = controller.start()
  await tick(); assert.equal(controller.getSnapshot().status, 'authenticated')
  assert.equal(await controller.signOut(), false)
  assert.deepEqual(controller.getSnapshot(), { status: 'unavailable', user: null }); stop()
})
