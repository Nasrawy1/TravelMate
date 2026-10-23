// Actual React pages rendered with explicit test-only verified/anonymous/checking state.
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
const compiled = new URL(`travelmate-auth-navigation-${process.pid}.mjs`, cache)
const entryPath = new URL(`travelmate-auth-navigation-entry-${process.pid}.mjs`, cache)
const exports = { WelcomePage: 'pages/WelcomePage.tsx', LoginPage: 'pages/LoginPage.tsx', SignupPage: 'pages/SignupPage.tsx', TripPlannerPage: 'pages/TripPlannerPage.tsx', ResultsPage: 'pages/ResultsPage.tsx', ForgotPasswordPage: 'pages/ForgotPasswordPage.tsx', ResetPasswordPage: 'pages/ResetPasswordPage.tsx' }
const entry = Object.entries(exports).map(([name, path]) => `export { default as ${name} } from ${JSON.stringify(`${root}src/${path}`)}`).join('\n')
  + `\nexport { AuthSessionContext } from ${JSON.stringify(`${root}src/components/auth/AuthSessionProvider.tsx`)}`
  + `\nexport { EmailAuthContext } from ${JSON.stringify(`${root}src/components/auth/EmailAuthProvider.tsx`)}`
await writeFile(entryPath, entry)
after(async () => { await Promise.allSettled([unlink(entryPath), unlink(compiled)]) })
const output = await build({ root, envDir: false, configFile: false, logLevel: 'silent', esbuild: { jsx: 'automatic' },
  define: { 'import.meta.env.DEV': 'false' },
  build: { ssr: fileURLToPath(entryPath), write: false, minify: false },
})
await writeFile(compiled, output.output.find(item => item.type === 'chunk' && item.isEntry).code)
const pages = await import(compiled.href)
const render = (page, status, displayName = null) => {
  const state = { status, user: status === 'authenticated' ? { id: 'test-only-id', displayName } : null }
  const controller = { getSnapshot: () => state, subscribe: () => () => {}, refresh: async () => {}, signOut: async () => true }
  return renderToStaticMarkup(createElement(MemoryRouter, null, createElement(pages.AuthSessionContext.Provider, { value: controller }, createElement(pages[page]))))
}

const renderRecovery = state => {
  const controller = { getSnapshot: () => state, subscribe: () => () => {}, requestReset: async () => {}, updatePassword: async () => {} }
  return renderToStaticMarkup(createElement(MemoryRouter, null, createElement(pages.EmailAuthContext.Provider, { value: controller }, createElement(pages.ResetPasswordPage))))
}

test('direct Reset Password is locked and has no password inputs even for an existing login', () => {
  const html = renderRecovery({ callback: 'none', recovery: 'locked', error: null })
  assert.ok(html.includes('A verified recovery link is required'))
  assert.ok(!html.includes('<form')); assert.ok(!html.includes('name="confirm_password"'))
  assert.ok(html.includes('href="/forgot-password"'))
})

test('only verified recovery shows the password form; pending and consumed links do not', () => {
  assert.ok(renderRecovery({ callback: 'recovery', recovery: 'ready', error: null }).includes('<form'))
  const pending = renderRecovery({ callback: 'pending', recovery: 'locked', error: null })
  assert.ok(pending.includes('role="status"')); assert.ok(!pending.includes('<form'))
  const completed = renderRecovery({ callback: 'recovery', recovery: 'complete', error: null })
  assert.ok(completed.includes('Password updated successfully')); assert.ok(!completed.includes('<form'))
})

test('completed reset has its own heading and login action, never the email-request acknowledgement', () => {
  const html = renderRecovery({ callback: 'none', recovery: 'complete', error: null })
  assert.match(html, /<h1[^>]*>Password updated successfully<\/h1>/)
  assert.match(html, /href="\/login"[^>]*>Return to sign in<\/a>/)
  assert.ok(html.includes('role="status"'))
  assert.ok(html.includes('This action has not signed you out'))
  for (const text of ['Check your email', 'If an account exists', 'href="/forgot-password"', '<form', 'Choose a new password']) assert.ok(!html.includes(text))
})

test('pending, failed and expired reset states cannot render password-update success', () => {
  for (const state of [
    { callback: 'recovery', recovery: 'updating', error: null },
    { callback: 'recovery', recovery: 'ready', error: null },
    { callback: 'none', recovery: 'locked', error: 'Recovery authorization expired.' },
  ]) {
    const html = renderRecovery(state)
    assert.ok(!html.includes('Password updated successfully'))
    assert.ok(!html.includes('Your password was updated successfully'))
    assert.ok(!html.includes('Check your email'))
  }
})

test('expired recovery has an accessible safe error and a new-link action', () => {
  const html = renderRecovery({ callback: 'invalid', recovery: 'locked', error: 'Recovery authorization expired. Request a new reset link.' })
  assert.ok(html.includes('role="alert"')); assert.ok(!html.includes('<form'))
  assert.ok(html.includes('href="/forgot-password"'))
})

test('verified Welcome planning links go directly to planner and account navigation replaces signin', () => {
  const html = render('WelcomePage', 'authenticated', 'Unit')
  assert.match(html, /href="\/trip-planner"[^>]*>Plan my trip/)
  assert.match(html, /href="\/trip-planner"[^>]*>Open Trip Planner/)
  assert.match(html, /href="\/login"[^>]*>My account/)
  assert.ok(!html.includes('Already have an account?')); assert.ok(!html.includes('href="/signup"'))
})

test('anonymous Welcome retains signup entry and signin links', () => {
  const html = render('WelcomePage', 'anonymous')
  assert.match(html, /href="\/signup"[^>]*>Plan my trip/)
  assert.ok(html.includes('Already have an account?')); assert.ok(html.includes('>Sign in</a>'))
})

test('Welcome demo cards target each bundled trip and anonymous Auth pages offer the working demo', () => {
  const html = render('WelcomePage', 'anonymous')
  for (const id of ['rome', 'paris', 'barcelona']) assert.ok(html.includes(`href="/offline-demo?trip=${id}"`))
  assert.ok(html.includes('Istanbul → Rome'))
  assert.ok(!html.includes('[City A'))
  assert.ok(!html.includes('demo placeholder'))
  for (const page of ['LoginPage', 'SignupPage']) {
    const auth = render(page, 'anonymous')
    assert.match(auth, /href="\/offline-demo"[^>]*>.*?Explore a demo trip/)
    assert.ok(!auth.includes('coming soon'))
  }
})

test('session initialization exposes no planning route or form that could misdirect a restored user', () => {
  const html = render('WelcomePage', 'checking')
  assert.match(html, /<button[^>]*disabled=""[^>]*>Checking session/)
  assert.ok(!html.includes('href="/signup"')); assert.ok(!html.includes('href="/login"'))
  for (const page of ['LoginPage', 'SignupPage']) {
    const form = render(page, 'checking')
    assert.ok(form.includes('Checking your session')); assert.ok(!form.includes('<form'))
  }
})

test('verification failures offer account verification without assuming authenticated or anonymous', () => {
  const html = render('WelcomePage', 'unavailable')
  assert.match(html, /href="\/login"[^>]*>Plan my trip/)
  assert.ok(!html.includes('href="/signup"'))
})

for (const page of ['LoginPage', 'SignupPage']) {
  test(`${page} has an accessible signed-in card with planner/logout, no form heading or email`, () => {
    const html = render(page, 'authenticated', 'Unit')
    assert.match(html, /<h2 id="(?:login|signup)-title">You(?:&#x27;|')re signed in<\/h2>/)
    assert.ok(html.includes('Open Trip Planner')); assert.ok(html.includes('Sign out on this browser'))
    assert.ok(html.includes('Welcome back, Unit.')); assert.ok(!html.includes('<form'))
    assert.ok(!html.includes('>Sign in</h2>')); assert.ok(!html.includes('>Create your account</h2>'))
    assert.ok(!html.includes('type="email"')); assert.ok(!html.includes('Already have one?'))
  })
  test(`${page} keeps the anonymous form and safe generic signed-in greeting`, () => {
    assert.ok(render(page, 'anonymous').includes('<form'))
    const html = render(page, 'authenticated')
    assert.ok(html.includes('Welcome back.')); assert.ok(!html.includes('@'))
  })
}

test('Trip Planner and Results share account navigation without changing trip behavior', () => {
  for (const page of ['TripPlannerPage', 'ResultsPage']) {
    assert.match(render(page, 'authenticated'), /href="\/login"[^>]*>My account/)
    assert.match(render(page, 'anonymous'), /href="\/login"[^>]*>Sign in/)
    assert.ok(!render(page, 'checking').includes('>Sign in</a>'))
  }
})
