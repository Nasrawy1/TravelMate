// Run with Node >=22.12: node --experimental-strip-types --test tests/tripPlanner.test.mjs
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { after } from 'node:test'
import { mkdir, writeFile, unlink } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { build } from 'vite'
const cache = new URL('../node_modules/.cache/', import.meta.url)
await mkdir(cache, { recursive: true })
const compiled = new URL(`trip-planner-tests-${process.pid}.mjs`, cache)
const output = await build({ root: fileURLToPath(new URL('../', import.meta.url)), envDir: false, configFile: false, logLevel: 'silent', build: { ssr: 'src/utils/tripPlanner.ts', write: false, minify: false } })
await writeFile(compiled, output.output.find(i => i.type === 'chunk' && i.isEntry).code)
after(() => unlink(compiled))
const { prepareTripRequest, utcToday, validateTripForm } = await import(compiled.href)

const today = '2026-10-16'
const valid = {
  departure_city: 'Istanbul', destination_city: 'Rome',
  start_date: '2026-11-10', return_date: '2026-11-12', adults: 2, budget_usd: '1500',
}

test('prepares exactly the six schema fields, converts budget and excludes UI metadata', () => {
  const schema = JSON.parse(readFileSync(new URL('../../docs/contracts/api-v0.4.schema.json', import.meta.url), 'utf8')).$defs.request
  const request = prepareTripRequest({ ...valid, submitted: true, user_id: 'must-not-leak', nights: 2 }, today)
  assert.deepEqual(Object.keys(request).sort(), [...schema.required].sort())
  assert.equal(schema.additionalProperties, false)
  assert.deepEqual(request, { ...valid, budget_usd: 1500 })
  assert.deepEqual(JSON.parse(JSON.stringify(request)), request)
  assert.equal(Number.isInteger(request.adults), true)
  assert.equal(typeof request.budget_usd, 'number')
})

test('validation clock uses UTC rather than the device calendar date', () => {
  assert.equal(utcToday(new Date('2026-10-17T01:30:00+03:00')), today)
  assert.equal(prepareTripRequest({ ...valid, start_date: today }, today), null)
  assert.ok(prepareTripRequest({ ...valid, start_date: '2026-10-17', return_date: '2026-10-18' }, today))
})

for (const [name, patch, field] of [
  ['missing departure', { departure_city: '' }, 'departure_city'],
  ['missing destination', { destination_city: '' }, 'destination_city'],
  ['same cities', { destination_city: 'Istanbul' }, 'destination_city'],
  ['unsupported city', { departure_city: 'Atlantis' }, 'departure_city'],
  ['missing start', { start_date: '' }, 'start_date'],
  ['missing return', { return_date: '' }, 'return_date'],
  ['today', { start_date: today }, 'start_date'],
  ['past return', { return_date: '2026-10-15' }, 'return_date'],
  ['February rollover', { start_date: '2027-02-30' }, 'start_date'],
  ['non-leap February', { return_date: '2027-02-29' }, 'return_date'],
  ['invalid month', { start_date: '2026-13-01' }, 'start_date'],
  ['noncanonical date', { start_date: '2026-1-01' }, 'start_date'],
  ['zero nights', { return_date: valid.start_date }, 'return_date'],
  ['negative nights', { return_date: '2026-11-09' }, 'return_date'],
  ['eight nights', { return_date: '2026-11-18' }, 'return_date'],
  ['zero adults', { adults: 0 }, 'adults'],
  ['five adults', { adults: 5 }, 'adults'],
  ['fractional adults', { adults: 1.5 }, 'adults'],
  ['string adults', { adults: '2' }, 'adults'],
  ['boolean adults', { adults: true }, 'adults'],
  ['nonfinite adults', { adults: Infinity }, 'adults'],
  ['missing budget', { budget_usd: '' }, 'budget_usd'],
  ['blank budget', { budget_usd: ' ' }, 'budget_usd'],
  ['zero budget', { budget_usd: '0' }, 'budget_usd'],
  ['negative budget', { budget_usd: '-1' }, 'budget_usd'],
  ['NaN budget', { budget_usd: 'NaN' }, 'budget_usd'],
  ['infinite budget', { budget_usd: 'Infinity' }, 'budget_usd'],
  ['overflow budget', { budget_usd: '1e309' }, 'budget_usd'],
]) {
  test(`rejects ${name} with an associated field error and no request`, () => {
    const values = { ...valid, ...patch }
    assert.ok(validateTripForm(values, today).errors[field])
    assert.equal(prepareTripRequest(values, today), null)
  })
}

test('accepts 1 and 7 nights, adult limits, fractional USD and leap day', () => {
  for (const patch of [
    { return_date: '2026-11-11', adults: 1 },
    { return_date: '2026-11-17', adults: 4 },
    { budget_usd: '0.50' },
    { start_date: '2028-02-28', return_date: '2028-02-29' },
  ]) assert.ok(prepareTripRequest({ ...valid, ...patch }, today))
  assert.equal(validateTripForm({ ...valid, start_date: '2027-03-27', return_date: '2027-03-29' }, today).nights, 2)
})

test('empty date counter is unknown, not zero nights', () => {
  assert.equal(validateTripForm({ ...valid, start_date: '' }, today).nights, null)
})

test('canonicalizes adapter aliases and case/whitespace variants, rejects identical mapped cities', () => {
  const request = prepareTripRequest({ ...valid, departure_city: '  ISTANBUL  ', destination_city: ' ROMA ' }, today)
  assert.equal(request.departure_city, 'Istanbul'); assert.equal(request.destination_city, 'Rome')
  assert.equal(prepareTripRequest({ ...valid, departure_city: 'Rome', destination_city: ' ROMA ' }, today), null)
})
for (const value of [' ', '\t\n', 'x'.repeat(201)]) test(`rejects blank/overlength city ${JSON.stringify(value.slice(0, 5))}`, () => {
  assert.equal(prepareTripRequest({ ...valid, departure_city: value }, today), null)
})
