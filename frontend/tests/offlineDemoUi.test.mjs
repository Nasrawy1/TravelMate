import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { mkdir, readFile, unlink, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { build } from 'vite'
import { getOfflineDemoTrip, OFFLINE_DEMO_IDS } from '../src/data/offlineDemo/index.ts'
import { budgetDisplay, formatMoney, providerLabel } from '../src/utils/results.ts'

const root = fileURLToPath(new URL('../', import.meta.url))
const compiled = new URL(`../node_modules/.cache/offline-demo-ui-${process.pid}.mjs`, import.meta.url)
await mkdir(new URL('.', compiled), { recursive: true })
const output = await build({ root, envDir: false, configFile: false, logLevel: 'silent',
  esbuild: { jsx: 'automatic' }, build: { ssr: 'src/pages/OfflineDemoPage.tsx', write: false, minify: false } })
const code = output.output.find(item => item.type === 'chunk' && item.isEntry).code
await writeFile(compiled, code)
after(() => unlink(compiled))
const { default: OfflineDemoPage } = await import(compiled.href)
const render = query => renderToStaticMarkup(createElement(MemoryRouter, { initialEntries: [`/offline-demo${query}`] }, createElement(OfflineDemoPage)))

for (const id of OFFLINE_DEMO_IDS) {
  test(`${id}: demo route renders full shared Results with sample provenance and exact supplied values`, () => {
    const { response: r } = getOfflineDemoTrip(id)
    const html = render(`?trip=${id}`)
    assert.match(html, /aria-label="Demo data notice"/)
    assert.match(html, /Prices are examples, not live, and nothing is sent or saved/)
    assert.match(html, /DEMO TRIP · SAMPLE DATA/)
    assert.match(html, /Demo price/)
    assert.ok(!/>Live(?: price| travel prices)?</.test(html))
    assert.equal((html.match(/<main\b/g) ?? []).length, 1)
    assert.equal((html.match(/<h1\b/g) ?? []).length, 1)
    assert.ok(html.includes(budgetDisplay(r.budget).status))
    for (const key of ['budget_usd', 'provider_subtotal_usd', 'estimated_subtotal_usd']) assert.ok(html.includes(formatMoney(r.budget[key])))
    assert.ok(html.includes(r.budget.projected_total_usd === null ? 'Not calculable' : formatMoney(r.budget.projected_total_usd)))
    for (const group of Object.values(r.travel_options)) for (const offer of group.offers) {
      const selected = [r.budget.selected_flight_offer_id, r.budget.selected_hotel_offer_id].includes(offer.id)
      assert.ok(html.includes(`data-offer-id="${offer.id}" data-selected="${selected}"`))
      assert.ok(html.includes(offer.retrieved_at))
      assert.ok(html.includes(`Sample data · ${offer.source} · sample timestamp`))
    }
    for (const item of r.budget.cost_items) {
      const row = html.match(new RegExp(`<li[^>]*data-expense-id="${item.id}"[^>]*>([\\s\\S]*?)</li>`))?.[1]
      assert.ok(row, item.id)
      assert.ok(row.includes(item.amount_usd === null ? 'Unknown' : formatMoney(item.amount_usd)))
      if (item.amount_usd === null) assert.ok(!row.includes('$0.00'))
    }
    for (const day of r.itinerary) {
      assert.ok(html.includes(day.date))
      for (const activity of day.activities) assert.ok(html.includes(activity.name.replaceAll('&', '&amp;')))
      if (day.empty_day_reason) assert.ok(html.includes(day.empty_day_reason))
    }
    for (const warning of r.warnings) assert.ok(html.includes(warning.message))
  })

  test(`${id}: selector exposes exactly one pressed native button and explicit online exits`, () => {
    const html = render(`?trip=${id}`)
    assert.match(html, /role="group" aria-label="Choose a demo trip"/)
    assert.equal((html.match(/aria-pressed="true"/g) ?? []).length, 1)
    assert.equal((html.match(/<button\b/g) ?? []).length, 3)
    const selected = html.match(/<button[^>]*aria-pressed="true"[^>]*>(.*?)<\/button>/)?.[1]
    assert.equal(selected, getOfflineDemoTrip(id).label)
    assert.match(html, /href="\/"[^>]*>Exit demo/)
    assert.match(html, /href="\/signup"[^>]*>Create account/)
    assert.match(html, /href="\/signup"[^>]*>Plan your own trip/)
    assert.ok(!html.includes('<form'))
    assert.ok(!html.includes('site-header'))
  })
}

test('default and unknown demo IDs safely show Rome, including prototype-shaped query values', () => {
  for (const query of ['', '?trip=unknown', '?trip=__proto__', '?trip=constructor']) assert.match(render(query), /Showing Istanbul → Rome/)
})

test('demo provenance defeats an erroneously supplied live-evidence flag', () => {
  assert.equal(providerLabel({ data_mode: 'offline_demo', live_evidence: true }), 'Demo price')
})

test('Barcelona shows missing hotel/taxes, unknown total and all warning messages', () => {
  const html = render('?trip=barcelona')
  for (const text of ['Uncertain', 'Not calculable', 'No sample hotel offer', 'Taxes and fees unknown', 'Significant costs are missing.', 'Counted as missing in the budget, never as $0.00.']) assert.ok(html.includes(text), text)
  assert.match(html, /class="res-missing"/)
  assert.match(html, /class="res-price res-price-unknown"/)
})

test('demo module graph contains no online service dependencies or development fixture adapter', () => {
  for (const forbidden of ['supabase', 'getSupabaseClient', 'getEmailAuthController', 'apiClient', 'generationMocks', 'getResultsFixture']) assert.ok(!code.includes(forbidden), forbidden)
})

test('demo responsive rules retain wrapping, touch targets, focus and shared mobile column order', async () => {
  const read = name => readFile(new URL(`../src/styles/${name}.css`, import.meta.url), 'utf8')
  const demo = await read('offline-demo')
  const results = await read('results')
  const planner = await read('trip-planner')
  assert.match(demo, /position: sticky/)
  assert.match(demo, /flex-wrap: wrap/)
  assert.match(demo, /min-height: 48px/)
  assert.match(demo, /max-width: 600px/)
  assert.match(results, /max-width: 960px/)
  assert.match(results, /\.res-costs \{ grid-column: 1; grid-row: 1;/)
  assert.match(results, /minmax\(min\(100%, 280px\), 1fr\)/)
  assert.match(planner, /:focus-visible/)
})
