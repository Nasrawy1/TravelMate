// Test-only configured client sentinel: direct offline/recovery routes must not initialize it.
import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { mkdir, unlink, writeFile } from 'node:fs/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { build } from 'vite'

const root = fileURLToPath(new URL('../', import.meta.url))
const cache = new URL('../node_modules/.cache/', import.meta.url)
await mkdir(cache, { recursive: true })
const compiled = new URL(`travelmate-auth-routes-${process.pid}.mjs`, cache)
const output = await build({ root, configFile: false, logLevel: 'silent', esbuild: { jsx: 'automatic' },
  define: { 'import.meta.env.DEV': 'false' },
  plugins: [{ name: 'test-only-auth-client-sentinel', enforce: 'pre',
    resolveId(source) { if (source.endsWith('/supabase')) return '\0auth-client-sentinel' },
    load(id) { if (id === '\0auth-client-sentinel') return `export const authConfig = {url:'https://unit.supabase.co',publishableKey:'sb_publishable_UNIT_TEST_ONLY',appUrl:'http://localhost:5173'}; export function getSupabaseClient(){throw new Error('AUTH_CLIENT_INITIALIZED')}` },
  }], build: { ssr: 'src/App.tsx', write: false, minify: false },
})
await writeFile(compiled, output.output.find(item => item.type === 'chunk' && item.isEntry).code)
after(() => unlink(compiled))
const { default: App } = await import(pathToFileURL(fileURLToPath(compiled)).href)
const render = path => renderToStaticMarkup(createElement(MemoryRouter, { initialEntries: [path] }, createElement(App)))

test('configured direct Offline Demo renders without creating the Auth client', () => {
  for (const trip of ['rome', 'paris', 'barcelona']) {
    const html = render(`/offline-demo?trip=${trip}`)
    assert.match(html, /DEMO TRIP · SAMPLE DATA/)
    assert.match(html, /Demo price/)
    assert.ok(!/>Live</.test(html))
  }
})
test('unknown routes do not initialize online Auth', () => {
  assert.match(render('/unknown'), /Page not found/)
})

test('the temporary JWT probe route does not exist in production or initialize Auth', () => {
  assert.match(render('/dev/auth-probe'), /Page not found/)
})
test('online routes use the shared Auth boundary (sentinel verifies isolation test)', () => {
  for (const route of ['/', '/login', '/signup', '/trip-planner', '/results', '/forgot-password', '/reset-password', '/auth/callback']) assert.throws(() => render(route), /AUTH_CLIENT_INITIALIZED/, route)
})
