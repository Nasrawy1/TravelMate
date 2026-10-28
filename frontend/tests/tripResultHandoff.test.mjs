import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { TripResultHandoff } from '../src/services/tripResultHandoff.ts'
import { GenerationController } from '../src/services/generation.ts'
const read = file => JSON.parse(readFileSync(new URL(`../../docs/fixtures/${file}`, import.meta.url), 'utf8'))
const request = read('request.json')
const response = read('within-budget.json')
test('validated successful generation hands off the exact public response without SDK state', async () => {
  const store = new TripResultHandoff(); store.setOwner('test-account-a')
  const lifecycle = new GenerationController(() => null)
  await lifecycle.start(request, { context: { data_mode: 'api', contract_version: '0.4', live_evidence: false }, generate: async () => ({ ok: true, status: 200, response }) })
  const state = lifecycle.getSnapshot()
  assert.equal(state.status, 'success')
  assert.equal(store.retain('test-account-a', state.response), true)
  lifecycle.cancel() // Planner unmount must not clear the route-level handoff.
  assert.deepEqual(store.read('test-account-a'), response)
  assert.notEqual(store.read('test-account-a'), response)
  assert.equal(store.read('test-account-b'), null)
})
test('direct visits, reload and leaving the route scope start empty', () => {
  assert.equal(new TripResultHandoff().read('test-account-a'), null)
})
test('account changes and signout discard prior data and reject late completions', () => {
  const store = new TripResultHandoff(); store.setOwner('test-account-a')
  store.retain('test-account-a', response)
  store.setOwner('test-account-b')
  assert.equal(store.read('test-account-b'), null)
  assert.equal(store.retain('test-account-a', response), false)
  store.setOwner(null)
  assert.equal(store.retain(null, response), false)
  store.setOwner('test-account-a'); assert.equal(store.read('test-account-a'), null)
})
test('all six success scenarios keep exact totals, selected IDs, unknowns and budget statuses', () => {
  const manifest = read('manifest.json')
  const store = new TripResultHandoff(); store.setOwner('test-account-a')
  for (const c of manifest.cases.filter(c => c.schema === 'response')) {
    const r = read(c.file)
    store.retain('test-account-a', r)
    assert.deepEqual(store.read('test-account-a'), r)
  }
})

test('success navigates to Results and Back/Forward do not resubmit or lose retained data', async () => {
  const { createMemoryRouter } = await import('react-router-dom')
  const { handoffGeneratedTrip } = await import('../src/services/tripResultHandoff.ts')
  const router = createMemoryRouter([{ path: '/trip-planner' }, { path: '/results' }], { initialEntries: ['/trip-planner'] })
  const store = new TripResultHandoff(); store.setOwner('test-account-a')
  const state = { status: 'success', request, response, context: { data_mode: 'api', contract_version: '0.4', live_evidence: false } }
  let navigations = 0
  const navigate = path => { navigations++; void router.navigate(path) }
  assert.equal(handoffGeneratedTrip(state, 'test-account-a', 'test-account-a', (o, r) => store.retain(o, r), navigate), true)
  assert.equal(router.state.location.pathname, '/results')
  await router.navigate(-1)
  assert.equal(router.state.location.pathname, '/trip-planner')
  await router.navigate(1)
  assert.equal(router.state.location.pathname, '/results')
  assert.deepEqual(store.read('test-account-a'), response)
  for (const rejected of [{ ...state, status: 'error' }, { ...state, context: { ...state.context, data_mode: 'structural_mock' } }]) assert.equal(handoffGeneratedTrip(rejected, 'test-account-a', 'test-account-a', () => true, navigate), false)
  assert.equal(handoffGeneratedTrip(state, 'test-account-a', 'test-account-b', () => true, navigate), false)
  assert.equal(navigations, 1)
  router.dispose()
})
