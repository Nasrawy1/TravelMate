import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { GenerationController, watchGenerationIdentity } from '../src/services/generation.ts'
import { handoffGeneratedTrip, TripResultHandoff } from '../src/services/tripResultHandoff.ts'

const read = file => JSON.parse(readFileSync(new URL(`../../docs/fixtures/${file}`, import.meta.url), 'utf8'))
const request = read('request.json')
const response = read('within-budget.json')
const context = { data_mode: 'api', contract_version: '0.4', live_evidence: false }
const authenticated = id => ({ status: 'authenticated', user: { id, displayName: null } })
const anonymous = { status: 'anonymous', user: null }

// Synchronous verified-session source, like AuthSessionController; no SDK or HTTP.
function sessionSource() {
  let state = authenticated('mock-a')
  const listeners = new Set()
  return {
    getSnapshot: () => state,
    subscribe: listener => { listeners.add(listener); return () => { listeners.delete(listener) } },
    publish: next => { state = next; listeners.forEach(listener => listener()) },
  }
}

function setup() {
  const source = sessionSource()
  const controller = new GenerationController(() => null)
  const store = new TripResultHandoff()
  const calls = []
  let requestOwner = null, navigations = 0
  const service = { context, generate: (input, { signal }) => new Promise(resolve => {
    // Deliberately ignore abort to reproduce a server response arriving late.
    calls.push({ input, signal, resolve })
  }) }
  const stop = watchGenerationIdentity(source, () => {
    requestOwner = null
    controller.cancel()
  })
  return {
    source, controller, calls, store,
    start() { requestOwner = source.getSnapshot().user?.id ?? null; return controller.start(request, service) },
    handoff(state = controller.getSnapshot()) {
      const owner = source.getSnapshot().user?.id ?? null
      store.setOwner(owner)
      return handoffGeneratedTrip(state, requestOwner, owner, (id, result) => store.retain(id, result), () => { navigations++ })
    },
    navigations: () => navigations,
    dispose() { stop(); controller.cancel() },
  }
}

const failure = { ok: false, error: { code: 'PROVIDER_UNAVAILABLE', title: 'Unavailable', message: 'Try later.', fields: {}, canRetry: true } }
for (const [name, transitions] of [
  ['signout', [anonymous]],
  ['A to B', [authenticated('mock-b')]],
  ['A to B to A in one synchronous batch', [authenticated('mock-b'), authenticated('mock-a')]],
  ['signout then return to A', [anonymous, authenticated('mock-a')]],
]) for (const late of ['success', 'error']) test(`${name}: late ${late} cannot publish, navigate or retry automatically`, async () => {
  const h = setup()
  try {
    const inputBefore = structuredClone(request)
    const pending = h.start()
    assert.equal(h.controller.getSnapshot().status, 'pending')
    const states = []
    const unsubscribe = h.controller.subscribe(() => states.push(h.controller.getSnapshot().status))
    transitions.forEach(h.source.publish)
    assert.equal(h.calls[0].signal.aborted, true)
    assert.equal(h.controller.getSnapshot().status, 'idle')
    h.calls[0].resolve(late === 'success' ? { ok: true, status: 200, response } : failure)
    assert.equal(await pending, false)
    await Promise.resolve()
    assert.ok(states.every(status => status === 'idle'))
    assert.equal(h.handoff(), false)
    assert.equal(h.navigations(), 0)
    assert.equal(h.calls.length, 1)
    assert.deepEqual(request, inputBefore)
    assert.deepEqual(h.calls[0].input, inputBefore)
    assert.equal(h.store.read('mock-a'), null)
    unsubscribe()
  } finally { h.dispose() }
})

for (const late of ['success', 'error']) test(`new deliberate attempt survives old late ${late} and still blocks duplicates`, async () => {
  const h = setup()
  try {
    const old = h.start()
    h.source.publish(authenticated('mock-b'))
    h.source.publish(authenticated('mock-a'))
    assert.equal(h.calls.length, 1) // Returning never resubmits.
    const next = h.start() // Deliberate action after identity verification.
    assert.equal(await h.start(), false)
    assert.equal(h.calls.length, 2)
    h.calls[0].resolve(late === 'success' ? { ok: true, status: 200, response: read('over-budget.json') } : failure)
    await old
    assert.equal(h.controller.getSnapshot().status, 'pending')
    assert.equal(h.calls[1].signal.aborted, false)
    const nextResponse = structuredClone(response)
    h.calls[1].resolve({ ok: true, status: 200, response: nextResponse })
    assert.equal(await next, true)
    assert.equal(h.controller.getSnapshot().response, nextResponse)
    assert.equal(h.handoff(), true)
    assert.equal(h.navigations(), 1)
    assert.deepEqual(h.store.read('mock-a'), nextResponse)
  } finally { h.dispose() }
})

test('identity invalidation also rejects a completed success awaiting its navigation effect', async () => {
  const h = setup()
  try {
    const pending = h.start()
    h.calls[0].resolve({ ok: true, status: 200, response })
    await pending
    const capturedSuccess = h.controller.getSnapshot()
    h.source.publish(authenticated('mock-b'))
    h.source.publish(authenticated('mock-a'))
    assert.equal(h.handoff(capturedSuccess), false)
    assert.equal(h.navigations(), 0)
  } finally { h.dispose() }
})

test('same-account re-verification does not invalidate a pending operation', async () => {
  const h = setup()
  try {
    const pending = h.start()
    h.source.publish({ status: 'checking', user: null })
    h.source.publish(authenticated('mock-a'))
    assert.equal(h.calls[0].signal.aborted, false)
    h.calls[0].resolve({ ok: true, status: 200, response })
    await pending
    assert.equal(h.handoff(), true)
  } finally { h.dispose() }
})

test('expiry or unavailable verification permanently invalidates the local operation', async () => {
  for (const status of ['expired', 'unavailable', 'not_configured']) {
    const h = setup()
    try {
      const pending = h.start()
      h.source.publish({ status: 'checking', user: null })
      h.source.publish({ status, user: null })
      h.source.publish(authenticated('mock-a'))
      h.calls[0].resolve({ ok: true, status: 200, response })
      await pending
      assert.equal(h.controller.getSnapshot().status, 'idle')
      assert.equal(h.handoff(), false)
    } finally { h.dispose() }
  }
})

test('identity watcher cleanup removes its subscription', () => {
  const source = sessionSource()
  let invalidations = 0
  const stop = watchGenerationIdentity(source, () => { invalidations++ })
  stop()
  source.publish(anonymous)
  assert.equal(invalidations, 0)
})
