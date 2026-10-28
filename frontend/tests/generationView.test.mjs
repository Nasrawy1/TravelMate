import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { mkdir, readFile, writeFile, unlink } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { build } from 'vite'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
const cache = new URL('../node_modules/.cache/', import.meta.url)
await mkdir(cache, { recursive: true })
const compiled = new URL(`generation-view-${process.pid}.mjs`, cache)
const output = await build({ root: fileURLToPath(new URL('../', import.meta.url)), envDir: false, configFile: false, logLevel: 'silent', esbuild: { jsx: 'automatic' }, build: { ssr: 'src/components/generation/GenerationView.tsx', write: false, minify: false } })
await writeFile(compiled, output.output.find(i => i.type === 'chunk' && i.isEntry).code)
after(() => unlink(compiled))
const { default: View } = await import(compiled.href)
const request = JSON.parse(await readFile(new URL('../../docs/fixtures/request.json', import.meta.url), 'utf8'))
const base = { request, context: { contract_version: '0.4', data_mode: 'api', live_evidence: false } }
const render = (state, remaining = 0) => renderToStaticMarkup(createElement(MemoryRouter, null, createElement(View, { state: { ...base, ...state }, remaining, onEdit() {}, onRetry() {} })))
test('real loading has accessible status, unverified stages and honest cancellation', () => {
  const html = render({ status: 'pending' })
  assert.match(html, /Building your trip/); assert.match(html, /role="status"/)
  assert.match(html, /aria-busy="true"/); assert.match(html, /Unverified/)
  assert.match(html, /Stop waiting and edit trip/); assert.match(html, /does not guarantee server cancellation/)
  assert.doesNotMatch(html, /MOCK pending/)
})
test('401 offers sign-in while cooldown renders a disabled deliberate retry', () => {
  const error = { code: 'UNAUTHORIZED', httpStatus: 401, title: 'Please sign in again', message: 'Sign in required', fields: {}, canRetry: false, signIn: true }
  const html = render({ status: 'error', error })
  assert.match(html, /href="\/login"/); assert.doesNotMatch(html, /Try again/)
  const limited = render({ status: 'error', error: { ...error, code: 'RATE_LIMITED', httpStatus: 429, canRetry: true, signIn: false, retryAt: 60000 } }, 60)
  assert.match(limited, /disabled=""/); assert.match(limited, /Try again in 60 s/)
  assert.match(limited, /never starts a retry automatically/)
})
test('success acknowledges validation without stale integration copy or fallback trips', () => {
  const html = render({ status: 'success', response: { generation_status: 'complete' } })
  assert.match(html, /Trip response validated/); assert.match(html, /validated for Results/); assert.doesNotMatch(html, /not connected yet|not connected in this increment/)
  assert.doesNotMatch(html, /href="\/results"|Demo price|MOCK/)
})


test('pending stop-waiting action follows stages and retains its accessible cancellation explanation', () => {
  const html = render({ status: 'pending' })
  assert.equal((html.match(/Stop waiting and edit trip/g) ?? []).length, 1)
  assert.ok(html.indexOf('Stop waiting and edit trip') > html.indexOf('</ol>'))
  assert.match(html, /aria-describedby="gen-operation-notice"/)
  assert.match(html, /Stopping locally does not guarantee server cancellation/)
  assert.match(html, /aria-label="Pending trip actions"/)
  assert.doesNotMatch(html, /gen-top-actions/)
})
test('validation failure has a single edit action and no retry', () => {
  const html = render({ status: 'error', error: { code: 'VALIDATION_ERROR', httpStatus: 422, title: 'Check your trip', message: 'Review your cities.', fields: { destination_city: 'Choose a different city.' }, canRetry: false } })
  assert.equal((html.match(/>Edit trip<\/button>/g) ?? []).length, 1)
  assert.doesNotMatch(html, /Try again|Stop waiting/)
  assert.match(html, /role="alert"/); assert.match(html, /aria-label="Trip recovery actions"/)
})
test('session expiry offers navigation and edit once without suggesting retry', () => {
  const html = render({ status: 'error', error: { code: 'SESSION_EXPIRED', title: 'Please sign in again', message: 'Session expired.', fields: {}, canRetry: false, signIn: true } })
  assert.match(html, /href="\/login"/)
  assert.equal((html.match(/>Edit trip<\/button>/g) ?? []).length, 1)
  assert.doesNotMatch(html, /Try again/)
})
test('retry becomes enabled after cooldown only as an explicit action', () => {
  const error = { code: 'RATE_LIMITED', title: 'Please wait', message: 'Retry manually later.', fields: {}, canRetry: true, retryAt: 60000 }
  const waiting = render({ status: 'error', error }, 30)
  assert.match(waiting, /disabled=""[^>]*>Try again in 30 s/)
  const ready = render({ status: 'error', error }, 0)
  assert.match(ready, />Try again<\/button>/)
  assert.doesNotMatch(ready, /disabled=""/)
  assert.match(ready, /never starts a retry automatically/)
})
