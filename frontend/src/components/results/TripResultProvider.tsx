import { createContext, useCallback, useContext, useLayoutEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { useAuthSessionState } from '../auth/AuthSessionProvider'
import { TripResultHandoff } from '../../services/tripResultHandoff'
import type { TripResult } from '../../types/results'

export const TripResultContext = createContext<{
  response: TripResult | null
  retain: (owner: string | null, response: TripResult) => boolean
} >({ response: null, retain: () => false })

/** Shared only by Planner and Results. Leaving online planning destroys the handoff. */
export default function TripResultProvider() {
  const session = useAuthSessionState()
  const owner = session.status === 'authenticated' ? session.user?.id ?? null : null
  const [store] = useState(() => new TripResultHandoff())
  const [, render] = useState(0)
  useLayoutEffect(() => { store.setOwner(owner); render(n => n + 1) }, [owner, store])
  const retain = useCallback((requestOwner: string | null, response: TripResult) => {
    if (!owner || owner !== requestOwner) return false
    const accepted = store.retain(owner, response)
    if (accepted) render(n => n + 1)
    return accepted
  }, [owner, store])
  return <TripResultContext.Provider value={{ response: store.read(owner), retain }}><Outlet /></TripResultContext.Provider>
}
export const useTripResult = () => useContext(TripResultContext)
