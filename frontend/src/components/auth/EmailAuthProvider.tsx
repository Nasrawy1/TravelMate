import { createContext, useContext, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { EmailAuthController } from '../../services/emailAuth'
import { getEmailAuthController } from '../../services/emailAuthRuntime'
import { getSupabaseClient } from '../../services/supabase'
import PasswordRecoveryLayout from './PasswordRecoveryLayout'

export const EmailAuthContext = createContext<EmailAuthController | null>(null)

export default function EmailAuthProvider() {
  const [controller] = useState(getEmailAuthController)
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot)
  const { pathname } = useLocation()
  const previous = useRef(pathname)
  const cleanup = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => {
    if (previous.current !== pathname) {
      controller.dismissCallback()
      if (previous.current === '/reset-password') controller.lock()
      previous.current = pathname
    }
  }, [pathname, controller])
  useEffect(() => {
    clearTimeout(cleanup.current)
    const client = getSupabaseClient()
    client?.auth.startAutoRefresh()
    const subscription = client?.auth.onAuthStateChange((event, session) => controller.observeSession(session, event))
    void controller.process()
    return () => {
      subscription?.data.subscription.unsubscribe()
      client?.auth.stopAutoRefresh()
      // Preserve StrictMode's immediate remount, but revoke on a real departure.
      cleanup.current = setTimeout(controller.lock, 0)
    }
  }, [controller])
  const callbackPage = pathname !== '/reset-password' && (state.callback !== 'none' || pathname === '/auth/callback')
  return <EmailAuthContext.Provider value={controller}>{callbackPage ? <PasswordRecoveryLayout
    onBackToLogin={controller.dismissCallback}
    title={state.callback === 'pending' ? 'Checking your email link' : state.callback === 'confirmed' ? 'Your email is confirmed' : state.callback === 'recovery' ? 'Recovery link verified' : 'This link could not be verified'}
    description="Secure access to your TravelMate account.">
    {state.callback === 'pending' ? <p role="status">Verifying your link with Supabase…</p> : <>
      <p role={state.callback === 'invalid' ? 'alert' : 'status'}>{state.error ?? (state.callback === 'confirmed' ? 'Your email and session were verified. You can continue to your trip.' : state.callback === 'recovery' ? 'Choose a new password to continue.' : 'Open a fresh confirmation or recovery email to continue.')}</p>
      <Link className="login-submit auth-planner-action" to={state.callback === 'recovery' ? '/reset-password' : state.callback === 'confirmed' ? '/trip-planner' : '/login'} onClick={controller.dismissCallback}>{state.callback === 'recovery' ? 'Choose a new password' : state.callback === 'confirmed' ? 'Open Trip Planner' : 'Return to sign in'}</Link>
      {state.callback === 'invalid' && <Link to="/forgot-password" onClick={controller.dismissCallback}>Request a new recovery link</Link>}
    </>}
  </PasswordRecoveryLayout> : <Outlet />}</EmailAuthContext.Provider>
}

export function useEmailAuth() {
  const controller = useContext(EmailAuthContext)
  if (!controller) throw new Error('Email Auth boundary is required')
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot)
  return { ...state, requestReset: controller.requestReset, updatePassword: controller.updatePassword }
}
