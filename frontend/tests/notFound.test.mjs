import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { mkdir, writeFile, unlink } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { build } from 'vite'
const root = fileURLToPath(new URL('../', import.meta.url))
const cache = new URL('../node_modules/.cache/', import.meta.url)
await mkdir(cache, { recursive: true })
const compiled = new URL(`not-found-${process.pid}.mjs`, cache)
const output = await build({ root, envDir: false, configFile: false, logLevel: 'silent', esbuild: { jsx: 'automatic' },
  plugins: [{ name: 'not-found-test-entry', resolveId(id) { if (id.endsWith('not-found-test-entry')) return 'not-found-test-entry' },
    load(id) { if (id === 'not-found-test-entry') return "export { default as NotFoundPage } from '/src/pages/NotFoundPage.tsx'; export { AuthSessionContext } from '/src/components/auth/AuthSessionProvider.tsx';" },
  }], build: { ssr: 'not-found-test-entry', write: false, minify: false },
})
await writeFile(compiled, output.output.find(c => c.type === 'chunk' && c.isEntry).code)
after(() => unlink(compiled))
const { NotFoundPage, AuthSessionContext } = await import(compiled.href)
for (const status of ['authenticated', 'anonymous', 'checking', 'expired']) test(`404 navigation stays truthful for ${status} users without reading Auth`, () => {
  let reads = 0
  const state = { status, user: status === 'authenticated' ? { id: 'unit-test-user', displayName: 'Test' } : null }
  const controller = { getSnapshot() { reads++; return state }, subscribe() { throw new Error('404_MUST_NOT_SUBSCRIBE') } }
  const html = renderToStaticMarkup(createElement(MemoryRouter, null,
    createElement(AuthSessionContext.Provider, { value: controller }, createElement(NotFoundPage))))
  assert.equal(reads, 0)
  assert.match(html, /Error 404/)
  assert.match(html, /href="\/"[^>]*>Go to home/)
  assert.match(html, /href="\/trip-planner"/)
  assert.doesNotMatch(html, /Sign in|href="\/login"|Frontend placeholder|Page designs pending approval/)
  assert.equal((html.match(/<h1\b/g) ?? []).length, 1)
  assert.equal((html.match(/<header\b/g) ?? []).length, 1)
  assert.match(html, /href="#not-found"/)
  assert.match(html, /<main[^>]+id="not-found"[^>]+tabindex="-1"/)
})
