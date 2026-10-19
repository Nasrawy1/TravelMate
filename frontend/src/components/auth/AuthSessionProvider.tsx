import { createContext, useContext, useEffect, useState, useSyncExternalStore } from 'react'
import { Outlet } from 'react-router-dom'
import { AuthSessionController } from '../../services/authSession'
import type { AuthSessionState } from '../../services/authSession'
import { getSupabaseClient } from '../../services/supabase'

export const AuthSessionContext = createContext<AuthSessionController | null>(null)
const unchecked: AuthSessionState = { status: 'checking', user: null }
const uncheckedSnapshot = () => unchecked
const noSubscription = () => () => {}

// Mounted only by online routes. Direct demo/recovery routes never create a client.
export default function AuthSessionProvider() {
  const [controller] = useState(() => new AuthSessionController(getSupabaseClient()))
  useEffect(() => controller.start(), [controller])
  return <AuthSessionContext.Provider value={controller}><Outlet /></AuthSessionContext.Provider>
}

export function useAuthSession() {
  const controller = useContext(AuthSessionContext)
  if (!controller) throw new Error('Auth route boundary is required')
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot)
  return { ...state, refresh: controller.refresh, signOut: controller.signOut }
}

// Standalone navigation renderers without an online boundary must remain undecided.
// This hook never creates a client (including when rendering an offline entry).
export function useAuthSessionState() {
  const controller = useContext(AuthSessionContext)
  return useSyncExternalStore(controller?.subscribe ?? noSubscription, controller?.getSnapshot ?? uncheckedSnapshot, controller?.getSnapshot ?? uncheckedSnapshot)
}
