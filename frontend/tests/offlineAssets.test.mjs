import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { build } from 'vite'

// Inspect real production output without reading local environment configuration
// or writing generated files. SDK source strings are not asset requests; emitted
// HTML/CSS URLs and chunk metadata define the runtime asset dependency closure.
const root = fileURLToPath(new URL('../', import.meta.url))
const production = await build({ root, envDir: false, logLevel: 'silent', build: { write: false } })
const output = production.output
const names = new Set(output.map(item => item.fileName))
const text = item => item.type === 'chunk' ? item.code : String(item.source)
const css = output.filter(item => item.fileName.endsWith('.css')).map(text).join('\n')
const html = output.filter(item => item.fileName.endsWith('.html')).map(text).join('\n')
const js = output.filter(item => item.type === 'chunk').map(text).join('\n')

function assertLocalAsset(url) {
  if (url.startsWith('#') || url.startsWith('data:')) return
  assert.ok(!/^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(url), 'External asset reference')
  const path = url.replace(/^\.?\//, '').split(/[?#]/)[0]
  assert.ok(names.has(path), `Missing bundled asset: ${path}`)
}

test('production CSS has no remote font imports or external resource URLs', () => {
  assert.ok(css.length > 0)
  assert.ok(!/@import\b/i.test(css))
  assert.ok(!/fonts\.(googleapis|gstatic)\.com/i.test(css))
  assert.equal((css.match(/@font-face/g) ?? []).length, 6)
  for (const face of css.matchAll(/@font-face\s*{([^}]*)}/gi)) assert.match(face[1], /url\(/)
  for (const match of css.matchAll(/url\(\s*['"]?([^)'"\s]+)['"]?\s*\)/gi)) assertLocalAsset(match[1])
})

test('production document scripts/styles and all emitted chunk dependencies are local and present', () => {
  assert.ok(html.includes('type="module"'))
  for (const match of html.matchAll(/(?:src|href)=["']([^"']+)["']/gi)) assertLocalAsset(match[1])
  for (const chunk of output.filter(item => item.type === 'chunk')) {
    for (const dependency of [...chunk.imports, ...chunk.dynamicImports, ...(chunk.referencedFiles ?? [])]) assert.ok(names.has(dependency), dependency)
  }
})

test('all three demo journeys ship in production, while online fixture tools and JWT probe do not', () => {
  for (const marker of ['demo-rome-flight', 'demo-paris-flight', 'demo-bcn-flight', 'offline_demo', 'Demo data notice']) assert.ok(js.includes(marker), marker)
  for (const marker of ['Results fixture preview', 'generation-preview-scenario', 'fixture-flight-1', 'Run JWT probe', '/api/v1/auth/probe']) assert.ok(!js.includes(marker), marker)
})

test('demo fonts use bundled Riviera faces with system fallbacks and no remote images', async () => {
  const demoCss = await readFile(new URL('../src/styles/offline-demo.css', import.meta.url), 'utf8')
  assert.match(demoCss, /--tm-font-display: 'Fraunces', Georgia, 'Times New Roman', serif/)
  assert.match(demoCss, /font-family: 'Figtree', system-ui/)
  for (const font of ['fraunces-latin-600-normal', 'fraunces-latin-600-italic', 'fraunces-latin-800-normal', 'figtree-latin-400-normal', 'figtree-latin-500-normal', 'figtree-latin-700-normal']) assert.ok([...names].some(name => name.includes(font) && name.endsWith('.woff2')), font)
  const logo = await readFile(new URL('../src/components/welcome/RivieraLogo.tsx', import.meta.url), 'utf8')
  const results = await readFile(new URL('../src/components/results/TripResults.tsx', import.meta.url), 'utf8')
  for (const illustration of [logo, results]) {
    assert.match(illustration, /<svg\b/)
    assert.ok(!/<(?:img|image)\b/.test(illustration))
  }
})

for (const font of ['fraunces-latin-600-normal', 'fraunces-latin-600-italic', 'fraunces-latin-800-normal', 'figtree-latin-400-normal', 'figtree-latin-500-normal', 'figtree-latin-700-normal']) test(`${font}: production preserves the exact local WOFF2 bytes`, async () => {
  const source = await readFile(new URL(`../src/assets/fonts/${font}.woff2`, import.meta.url))
  assert.equal(source.toString('ascii', 0, 4), 'wOF2')
  assert.equal(source.readUInt32BE(8), source.length)
  assert.ok(source.length > 10000)
  const emitted = output.find(item => item.type === 'asset' && item.fileName.includes(font) && item.fileName.endsWith('.woff2'))
  assert.ok(emitted)
  assert.deepEqual(Buffer.from(emitted.source), source)
})
test('both local font families include complete OFL license texts', async () => {
  for (const family of ['Figtree', 'Fraunces']) {
    const license = await readFile(new URL(`../src/assets/fonts/${family}-OFL.txt`, import.meta.url), 'utf8')
    assert.match(license, /SIL OPEN FONT LICENSE Version 1\.1/)
    assert.match(license, /PERMISSION & CONDITIONS/)
    assert.match(license, /DISCLAIMER/)
  }
})
