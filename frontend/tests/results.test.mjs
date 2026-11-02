// Uses the existing Vite compiler to test real TSX output without adding dependencies.
// node --experimental-strip-types --test tests/*.test.mjs
import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { mkdir, readFile, unlink, writeFile } from 'node:fs/promises'
import { pathToFileURL, fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { build } from 'vite'
import { RESULTS_FIXTURES, getResultsFixture } from '../src/fixtures/resultsFixtures.ts'
import { budgetDisplay, formatMoney, formatTimestamp, priceDisplay, providerLabel, selectedFirst, warningTitle } from '../src/utils/results.ts'

const root = fileURLToPath(new URL('../', import.meta.url))
const cache = new URL('../node_modules/.cache/', import.meta.url)
await mkdir(cache, { recursive: true })
const compiledPath = new URL(`travelmate-results-tests-${process.pid}.mjs`, cache)
const output = await build({ root, configFile: false, logLevel: 'silent',
  esbuild: { jsx: 'automatic' },
  build: { ssr: 'src/components/results/TripResults.tsx', write: false, minify: false },
})
const chunk = output.output.find(item => item.type === 'chunk' && item.isEntry)
await writeFile(compiledPath, chunk.code)
after(async () => { await unlink(compiledPath) })
const { default: TripResults } = await import(pathToFileURL(fileURLToPath(compiledPath)).href)
const render = data => renderToStaticMarkup(createElement(MemoryRouter, null, createElement(TripResults, data)))
const readFixture = async name => JSON.parse(await readFile(new URL(`../../docs/fixtures/${name}`, import.meta.url), 'utf8'))
const manifest = await readFixture('manifest.json')

for (const name of RESULTS_FIXTURES) {
  test(`${name}: renders actual repository data, selections, budget status and amounts without mutation`, async () => {
    const data = getResultsFixture(name)
    const original = await readFixture(`${name}.json`)
    assert.deepEqual(data.response, original)
    assert.deepEqual(data.context.manifest, manifest)
    assert.deepEqual(data.context.fixtureCase, manifest.cases.find(item => item.file === `${name}.json`))
    assert.equal(data.context.data_mode, 'structural_mock')
    assert.equal(data.context.live_evidence, false)
    const before = JSON.stringify(data)
    const html = render(data)
    assert.equal(JSON.stringify(data), before)
    assert.ok(html.includes('MOCK TRIP'))
    assert.ok(!/>Live(?: price)?</.test(html))
    assert.ok(html.includes(budgetDisplay(original.budget).status))
    for (const key of ['budget_usd', 'provider_subtotal_usd', 'estimated_subtotal_usd']) assert.ok(html.includes(formatMoney(original.budget[key])))
    assert.ok(html.includes(original.budget.projected_total_usd === null ? 'Not calculable' : formatMoney(original.budget.projected_total_usd)))
    for (const [category, selectedKey] of [['flights', 'selected_flight_offer_id'], ['hotels', 'selected_hotel_offer_id']]) {
      const offers = original.travel_options[category].offers
      for (const offer of offers) {
        assert.ok(html.includes(`data-offer-id="${offer.id}" data-selected="${offer.id === original.budget[selectedKey]}"`))
        assert.ok(html.includes(offer.source))
        assert.ok(html.includes(offer.retrieved_at))
      }
    }
    for (const item of original.budget.cost_items) {
      const row = html.match(new RegExp(`<li[^>]*data-expense-id="${item.id}"[^>]*>([\\s\\S]*?)</li>`))?.[1]
      assert.ok(row, item.id)
      assert.ok(row.includes(priceDisplay(item, data.context, item.category === 'activities').amount), item.id)
      if (item.kind === 'unknown' || item.amount_usd === null) assert.ok(!row.includes('$0.00'))
      if (item.kind === 'provider') assert.ok(row.includes('Sample price'))
    }
    for (const day of original.itinerary) assert.ok(html.includes(day.date))
  })
}

test('selection is ID-only, keeps backend-selected expensive alternatives first and never mutates source', () => {
  const data = structuredClone(getResultsFixture('within-budget'))
  const source = data.response.travel_options.flights.offers[0]
  const expensive = { ...source, id: 'unit-selected-expensive', price: { ...source.price, amount_usd: 9000 } }
  const cheap = { ...source, id: 'unit-cheapest', price: { ...source.price, amount_usd: 1 } }
  data.response.travel_options.flights.offers = [cheap, expensive]
  data.response.budget.selected_flight_offer_id = expensive.id
  const html = render(data)
  assert.ok(html.includes('data-offer-id="unit-selected-expensive" data-selected="true"'))
  assert.ok(html.includes('data-offer-id="unit-cheapest" data-selected="false"'))
  assert.ok(html.indexOf('data-offer-id="unit-selected-expensive"') < html.indexOf('data-offer-id="unit-cheapest"'))
  assert.deepEqual(data.response.travel_options.flights.offers.map(offer => offer.id), [cheap.id, expensive.id])
  assert.deepEqual(selectedFirst([cheap, expensive], null), [cheap, expensive])
  assert.deepEqual(selectedFirst([cheap, expensive], 'absent-id'), [cheap, expensive])
})

test('budget rendering never corrects supplied totals or re-derives status', () => {
  const data = structuredClone(getResultsFixture('within-budget'))
  // Intentionally contradictory unit input proves this is a renderer, not a budget calculator.
  data.response.budget.projected_total_usd = 12.34
  data.response.budget.provider_subtotal_usd = 56.78
  data.response.budget.estimated_subtotal_usd = 90.12
  data.response.budget.status = 'over_budget'
  const html = render(data)
  for (const value of ['$12.34', '$56.78', '$90.12', 'Over budget']) assert.ok(html.includes(value))
  assert.ok(!html.includes('$1,140.00'))
})

test('known minimum over budget remains over budget with a non-calculable projected total', () => {
  const data = getResultsFixture('known-minimum-over-budget')
  const html = render(data)
  assert.ok(html.includes('Over budget'))
  assert.ok(html.includes('Not calculable'))
  assert.ok(html.includes('before missing costs are added'))
  assert.ok(!html.includes('Uncertain'))
})

test('unknown taxes and unavailable prices remain distinct from explicit free activities', () => {
  const taxHtml = render(getResultsFixture('unknown-taxes'))
  assert.ok(taxHtml.includes('Taxes and fees unknown'))
  assert.ok(taxHtml.includes('Hotel tax is unknown.'))
  const noPriceHtml = render(getResultsFixture('no-prices'))
  assert.equal((noPriceHtml.match(/class="res-unavailable res-card"/g) ?? []).length, 2)
  assert.ok(noPriceHtml.includes('No sample flight or hotel prices available'))
  assert.ok(noPriceHtml.includes('Estimate'))
  assert.ok(noPriceHtml.includes('$0.00')) // These zeroes belong to explicitly free activities/subtotals.
  const context = getResultsFixture('within-budget').context
  assert.deepEqual(priceDisplay({ kind: 'estimate', amount_usd: 0 }, context), { label: 'Estimate', amount: '$0.00', style: 'estimate' })
  for (const value of [null, NaN, Infinity]) assert.equal(priceDisplay({ kind: 'provider', amount_usd: value }, context).amount, 'Unknown')
  assert.equal(priceDisplay({ kind: 'unknown', amount_usd: 0 }, context).amount, 'Unknown')
})

test('nullable rooms/area, empty-day reason and unknown activities have honest accessible output', () => {
  const data = structuredClone(getResultsFixture('within-budget'))
  data.response.travel_options.hotels.offers[0].room_qty = null
  data.response.itinerary[0].activities = []
  data.response.itinerary[0].empty_day_reason = 'Arrival travel day.'
  data.response.itinerary[1].activities[0].cost = { amount_usd: null, kind: 'unknown', coverage: null }
  data.response.warnings = [{ code: 'NEW_WARNING', message: 'Safe warning <b>as plain text</b>.' }]
  const html = render(data)
  for (const text of ['rooms not provided', 'Area not provided', 'Arrival travel day.', 'Unknown', 'Note.', '&lt;b&gt;as plain text&lt;/b&gt;']) assert.ok(html.includes(text))
})

test('fixture price provenance always defeats provider-shaped metadata; unverified API data is not Live', () => {
  const context = getResultsFixture('within-budget').context
  assert.equal(providerLabel({ ...context, live_evidence: true }), 'Sample price')
  assert.equal(providerLabel({ data_mode: 'validated_api', live_evidence: false }), 'Retrieved price')
  assert.equal(providerLabel({ data_mode: 'validated_api', live_evidence: true }), 'Retrieved price')
  assert.equal(getResultsFixture('not-a-case'), null)
  assert.equal(getResultsFixture('__proto__'), null)
  assert.equal(warningTitle('NEW_CODE'), 'Note.')
})

test('timestamps stay in UTC independently of the local device timezone', () => {
  assert.equal(formatTimestamp('2026-10-15T23:30:00Z'), '15 Oct 2026, 23:30 UTC')
})

test('current production assets exclude Results/generation fixtures and development controls', async () => {
  const production = await build({ root, logLevel: 'silent', build: { write: false } })
  const assets = production.output.map(item => item.type === 'chunk' ? item.code : String(item.source)).join('\n')
  // FE-03 intentionally ships local demo samples (including their fixed dates),
  // while the development fixture adapters and JWT probe must remain excluded.
  for (const marker of ['demo-rome-flight', 'demo-paris-flight', 'demo-bcn-flight', 'Demo data notice']) assert.ok(assets.includes(marker), marker)
  for (const marker of ['fixture-provider', 'fixture-flight-1', 'within-budget.json', 'unknown-taxes.json', 'Results fixture preview', 'Inspect MOCK state', 'generation-preview-scenario', 'MOCK result scenario', 'Run JWT probe', '/api/v1/auth/probe', 'dev/auth-probe']) assert.ok(!assets.includes(marker), marker)
})

test('direct production Results navigation renders an honest empty state without fixtures', async () => {
  const emptyPath = new URL(`travelmate-results-empty-tests-${process.pid}.mjs`, cache)
  try {
    const compiled = await build({ root, configFile: false, logLevel: 'silent', esbuild: { jsx: 'automatic' },
      build: { ssr: 'src/pages/ResultsPage.tsx', write: false, minify: false } })
    await writeFile(emptyPath, compiled.output.find(item => item.type === 'chunk' && item.isEntry).code)
    const { default: ResultsPage } = await import(emptyPath.href)
    const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(ResultsPage)))
    assert.ok(html.includes('No trip result yet'))
    assert.ok(html.includes('No generated trip is retained in this session.'))
    assert.ok(!html.includes('Trip generation and authentication are not connected.'))
    assert.ok(!html.includes('MOCK result scenario'))
    assert.ok(!html.includes('fixture-provider'))
  } finally { await unlink(emptyPath).catch(error => { if (error.code !== 'ENOENT') throw error }) }
})

for (const name of RESULTS_FIXTURES) test(`API rendering ${name} preserves sources, timestamps and backend budget values`, () => {
  const { response } = getResultsFixture(name)
  const before = structuredClone(response)
  const html = render({ response, context: { data_mode: 'validated_api', live_evidence: false } })
  assert.ok(html.includes(budgetDisplay(response.budget).status))
  assert.ok(html.includes(budgetDisplay(response.budget).total))
  for (const offer of [...response.travel_options.flights.offers, ...response.travel_options.hotels.offers]) {
    assert.ok(html.includes(offer.source)); assert.ok(html.includes(offer.retrieved_at))
  }
  assert.ok(!/>Live</.test(html)); assert.ok(!html.includes('Sample price'))
  if (response.budget.missing_categories.length) assert.ok(html.includes('Not calculable'))
  assert.deepEqual(response, before)
})

test('zero activity estimates, other zero costs and unknowns remain distinct', () => {
  const context = { data_mode: 'validated_api', live_evidence: false }
  assert.equal(priceDisplay({ amount_usd: 0, kind: 'estimate' }, context, true).amount, 'Estimated free')
  assert.equal(priceDisplay({ amount_usd: 0, kind: 'estimate' }, context).amount, '$0.00')
  assert.equal(priceDisplay({ amount_usd: 0, kind: 'provider' }, context, true).amount, '$0.00')
  assert.equal(priceDisplay({ amount_usd: 40, kind: 'estimate' }, context, true).amount, '~$40.00')
  for (const amount of [null, NaN, Infinity]) assert.equal(priceDisplay({ amount_usd: amount, kind: 'estimate' }, context, true).amount, 'Unknown')
  const data = getResultsFixture('no-prices')
  const html = render({ response: data.response, context })
  assert.ok(html.includes('Estimated free'))
  for (const item of data.response.budget.cost_items.filter(i => i.kind === 'unknown')) {
    const row = html.match(new RegExp(`<li[^>]*data-expense-id="${item.id}"[^>]*>([\\s\\S]*?)</li>`))?.[1]
    assert.ok(row.includes('<strong>Unknown</strong>'))
    assert.ok(!row.includes('res-price-tag'))
    assert.ok(!row.includes('$0.00')); assert.ok(!row.includes('Estimated free'))
  }
})
test('missing travel keeps backend zero subtotal and adds separate explanation', () => {
  const data = getResultsFixture('no-prices'), before = structuredClone(data.response)
  const html = render({ response: data.response, context: { data_mode: 'validated_api', live_evidence: false } })
  assert.ok(html.includes('<dt>Retrieved travel prices</dt><dd>$0.00</dd>'))
  assert.ok(html.includes('No priced travel offers are available.'))
  assert.ok(html.includes('missing travel costs are not free.'))
  assert.ok(html.includes('Not calculable'))
  assert.ok(!html.includes('<strong aria-hidden="true">—</strong>'))
  assert.ok(html.includes('Counted as missing in the budget, never as $0.00.'))
  assert.deepEqual(data.response, before)
  assert.ok(!render(getResultsFixture('within-budget')).includes('No priced travel offers are available.'))
})
test('updated decoration and retrieved provenance preserve backend source and timestamps', () => {
  const data = getResultsFixture('within-budget')
  const html = render({ response: data.response, context: { data_mode: 'validated_api', live_evidence: false } })
  assert.ok(html.includes('width="300" height="170"'))
  assert.ok(html.includes('Retrieved price')); assert.ok(!/>Live</.test(html))
  for (const offer of [...data.response.travel_options.flights.offers, ...data.response.travel_options.hotels.offers]) {
    assert.ok(html.includes(offer.source)); assert.ok(html.includes(offer.retrieved_at))
  }
})
