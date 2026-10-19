import { EmailAuthController, parseEmailCallback } from './emailAuth'
import type { EmailCallback } from './emailAuth'
import { authConfig, getSupabaseClient } from './supabase'

let captured: EmailCallback = { kind: 'none' }
let controller: EmailAuthController | undefined

/** Called once before BrowserRouter mounts. No client/network on the demo path. */
export function captureEmailCallback() {
  const url = new URL(window.location.href)
  const callback = parseEmailCallback(url)
  if (callback.kind === 'none') return
  const online = ['/', '/login', '/signup', '/auth/callback', '/reset-password'].includes(url.pathname)
  captured = online ? callback : { kind: 'none' }
  // Credentials/code/flowId are retained in captured memory and passed explicitly
  // to the SDK later. Scrubbing does not discard them or enable SDK auto-detection.
  window.history.replaceState(window.history.state, '', url.pathname)
}

export function getEmailAuthController() {
  if (!controller) {
    controller = new EmailAuthController(getSupabaseClient(), authConfig, captured)
    captured = { kind: 'none' }
  }
  return controller
}
