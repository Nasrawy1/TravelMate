// No live Auth, browser storage, tokens or backend requests are used here.
import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { mkdir, unlink, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { build } from 'vite'

const root = fileURLToPath(new URL('../', import.meta.url)).replaceAll('\\', '/')
const cache = new URL('../node_modules/.cache/', import.meta.url)
await mkdir(cache, { recursive: true })
const compiled = new URL(`travelmate-probe-tests-${process.pid}.mjs`, cache)
const entry = new URL(`travelmate-probe-test-entry-${process.pid}.mjs`, cache)
after(async () => { await Promise.allSettled([unlink(compiled), unlink(entry)]) })
await writeFile(entry, `export {default as Page, probeIdentityMatches} from ${JSON.stringify(root + 'src/pages/dev/AuthProbePage.tsx')}; export {AuthSessionContext} from ${JSON.stringify(root + 'src/components/auth/AuthSessionProvider.tsx')};`)
const output = await build({ root, envDir: false, configFile: false, logLevel: 'silent', esbuild: { jsx: 'automatic' },
  plugins: [{ name: 'no-probe-network', enforce: 'pre',
    resolveId(id) { if (id.endsWith('/services/api')) return '\0test-api' },
    load(id) { if (id === '\0test-api') return 'export const api={request(){throw new Error("NO_AUTOMATIC_PROBE_ALLOWED")}}' },
  }], build: { ssr: fileURLToPath(entry), write: false, minify: false },
})
await writeFile(compiled, output.output.find(item => item.type === 'chunk' && item.isEntry).code)
const { Page, AuthSessionContext, probeIdentityMatches } = await import(compiled.href)

test('probe comparison exposes only a boolean for a valid 200 response', () => {
  assert.equal(probeIdentityMatches({ status: 200, body: { status: 'ok', user_id: 'test-user' } }, 'test-user'), true)
  assert.equal(probeIdentityMatches({ status: 200, body: { status: 'ok', user_id: 'other-user' } }, 'test-user'), false)
})

test('missing or untrusted probe results are never claimed as verified matches', () => {
  for (const body of [null, [], {}, { user_id: 'test-user' }, { status: 'ok', user_id: null }, { status: 'ok', user_id: 123 }]) assert.equal(probeIdentityMatches({ status: 200, body }, 'test-user'), null)
  for (const status of [401, 403, 500]) assert.equal(probeIdentityMatches({ status, body: { status: 'ok', user_id: 'test-user' } }, 'test-user'), null)
  assert.equal(probeIdentityMatches({ status: 200, body: { status: 'ok', user_id: 'test-user' } }, ''), null)
})

test('probe UI requires verified sign-in and never displays session identity metadata', () => {
  for (const status of ['checking', 'anonymous', 'authenticated', 'expired', 'unavailable']) {
    const state = { status, user: status === 'authenticated' ? { id: 'PRIVATE_TEST_USER_ID', displayName: 'PRIVATE_TEST_NAME' } : null }
    const controller = { getSnapshot: () => state, subscribe: () => () => {} }
    const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(AuthSessionContext.Provider, { value: controller }, createElement(Page))))
    assert.ok(html.includes('HTTP status:')); assert.ok(html.includes('Not checked')); assert.ok(html.includes('Not verified'))
    assert.ok(!html.includes('PRIVATE_TEST_USER_ID')); assert.ok(!html.includes('PRIVATE_TEST_NAME'))
    assert.equal(/<button[^>]*disabled/.test(html), status !== 'authenticated')
  }
})
