import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import { OFFLINE_DEMO_IDS, getOfflineDemoTrip } from '../src/data/offlineDemo/index.ts'
import { formatMoney } from '../src/utils/results.ts'

const expected = {
  rome: ['Istanbul', 'Rome', 3, 2, 1200, 1184, 'within_budget'],
  paris: ['London', 'Paris', 2, 1, 600, 670, 'over_budget'],
  barcelona: ['Dubai', 'Barcelona', 4, 3, 2500, null, 'uncertain'],
}

test('exactly the three approved-for-this-increment proposed journeys are exposed', () => {
  assert.deepEqual(OFFLINE_DEMO_IDS, ['rome', 'paris', 'barcelona'])
})

for (const id of OFFLINE_DEMO_IDS) {
  test(`${id}: complete local response and DEMO provenance preserved`, async () => {
    const data = getOfflineDemoTrip(id)
    const json = JSON.parse(await readFile(new URL(`../src/data/offlineDemo/${id}.json`, import.meta.url), 'utf8'))
    assert.deepEqual(data, json)
    assert.equal(data.provenance.label, 'DEMO')
    assert.equal(data.provenance.data_mode, 'offline_demo')
    assert.equal(data.provenance.live_evidence, false)
    assert.match(data.provenance.notice, /not live/)
    const r = data.response
    assert.deepEqual([r.trip.departure_city, r.trip.destination_city, r.trip.nights, r.trip.adults,
      r.budget.budget_usd, r.budget.projected_total_usd, r.budget.status], expected[id])
    assert.equal(r.itinerary.length, r.trip.nights + 1)
    assert.deepEqual(Object.keys(data.request).sort(), ['adults', 'budget_usd', 'departure_city', 'destination_city', 'return_date', 'start_date'])
    for (const day of r.itinerary) {
      for (const activity of day.activities) {
        for (const key of ['name', 'area', 'description']) assert.ok(activity[key].trim())
      }
    }
  })

  test(`${id}: selected IDs, ledger links and sample sources are not changed by loading`, () => {
    const { response: r } = getOfflineDemoTrip(id)
    for (const [category, key, ledger] of [['flights', 'selected_flight_offer_id', 'flights'], ['hotels', 'selected_hotel_offer_id', 'accommodation']]) {
      const selected = r.budget[key]
      const offers = r.travel_options[category].offers
      const item = r.budget.cost_items.find(item => item.category === ledger)
      assert.equal(item.source_offer_id, selected)
      if (selected === null) {
        assert.deepEqual(offers, [])
        assert.equal(item.amount_usd, null)
      } else {
        assert.equal(item.amount_usd, offers.find(offer => offer.id === selected).price.amount_usd)
      }
      for (const offer of offers) assert.equal(offer.source, 'demo-sample')
    }
  })
}

test('Barcelona keeps missing hotel, unknown flight taxes and unknown total distinct from zero', () => {
  const r = getOfflineDemoTrip('barcelona').response
  assert.equal(r.travel_options.hotels.status, 'unavailable')
  assert.equal(r.budget.selected_hotel_offer_id, null)
  assert.equal(r.travel_options.flights.offers[0].taxes.status, 'unknown')
  assert.equal(r.travel_options.flights.offers[0].taxes.additional_amount_usd, null)
  assert.equal(r.budget.projected_total_usd, null)
  assert.deepEqual(r.budget.missing_categories, ['accommodation', 'taxes_fees'])
  assert.equal(r.warnings.length, 3)
  for (const item of r.budget.cost_items.filter(item => item.kind === 'unknown')) {
    assert.equal(item.amount_usd, null)
    assert.equal(formatMoney(item.amount_usd), 'Unknown')
  }
})

test('explicit free activities and included taxes remain genuine zero values', () => {
  for (const id of OFFLINE_DEMO_IDS) {
    const r = getOfflineDemoTrip(id).response
    const free = r.itinerary.flatMap(day => day.activities).filter(a => a.cost.amount_usd === 0)
    assert.ok(free.length > 0)
    for (const activity of free) {
      assert.equal(activity.cost.kind, 'estimate')
      assert.equal(formatMoney(activity.cost.amount_usd), '$0.00')
    }
    for (const group of Object.values(r.travel_options)) {
      for (const offer of group.offers.filter(o => o.taxes.status === 'included')) assert.equal(offer.taxes.additional_amount_usd, 0)
    }
  }
})

test('each selection returns an independent copy including nested provenance and ledger', () => {
  const changed = getOfflineDemoTrip('rome')
  changed.response.budget.cost_items[0].amount_usd = 1
  changed.provenance.live_evidence = true
  changed.response.itinerary.pop()
  const next = getOfflineDemoTrip('rome')
  assert.equal(next.provenance.live_evidence, false)
  assert.equal(next.response.itinerary.length, 4)
  assert.notEqual(next.response.budget.cost_items[0].amount_usd, 1)
})

test('unknown IDs and prototype names fail closed without defaulting to a trip', () => {
  for (const id of ['', 'unknown', '__proto__', 'constructor', 'toString', 'ROME']) assert.equal(getOfflineDemoTrip(id), null)
})

test('fresh import and loading all samples require no network, configuration or session storage', () => {
  const moduleUrl = new URL('../src/data/offlineDemo/index.ts', import.meta.url).href
  const code = `
    const deny = () => { throw new Error('ONLINE_OR_STORAGE_ACCESS'); };
    globalThis.fetch = deny;
    globalThis.WebSocket = class { constructor() { deny(); } };
    for (const key of ['localStorage', 'sessionStorage', 'window', 'document'])
      Object.defineProperty(globalThis, key, { get: deny });
    const { OFFLINE_DEMO_IDS, getOfflineDemoTrip } = await import(${JSON.stringify(moduleUrl)});
    for (const id of OFFLINE_DEMO_IDS) if (!getOfflineDemoTrip(id)) throw new Error('MISSING_SAMPLE');
  `
  const run = spawnSync(process.execPath, ['--experimental-strip-types', '--input-type=module', '-e', code], { encoding: 'utf8' })
  assert.equal(run.status, 0, run.stderr)
})
