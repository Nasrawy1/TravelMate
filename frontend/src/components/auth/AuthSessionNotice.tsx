import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuthSession } from './AuthSessionProvider'

export default function AuthSessionNotice({ headingId }: { headingId: string }) {
  const auth = useAuthSession()
  const [leaving, setLeaving] = useState(false)
  const [failed, setFailed] = useState(false)
  async function logout() {
    if (leaving) return
    setLeaving(true); setFailed(false)
    try { setFailed(!await auth.signOut()) } finally { setLeaving(false) }
  }
  return <>
    {auth.status === 'authenticated' && <div className="auth-signed-in">
      <span className="auth-signed-in-icon" aria-hidden="true"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12l4 4L19 6" /></svg></span>
      <div className="login-card-heading"><h2 id={headingId}>You're signed in</h2><p>{auth.user?.displayName ? `Welcome back, ${auth.user.displayName}.` : 'Welcome back.'} Your next trip starts here.</p></div>
      <Link className="login-submit auth-planner-action" to="/trip-planner">Open Trip Planner <span aria-hidden="true">→</span></Link>
    </div>}
    <div className="auth-session-notice" role="status">
      {auth.status === 'checking' && 'Checking your session…'}
      {auth.status === 'not_configured' && 'Authentication is unavailable until local Supabase configuration is supplied.'}
      {auth.status === 'expired' && 'Your session has expired. Please sign in again.'}
      {auth.status === 'unavailable' && <>We could not verify your session. <button type="button" onClick={() => { void auth.refresh() }}>Check again</button></>}
    </div>
    {(auth.status === 'authenticated' || auth.status === 'unavailable') && <button type="button" className="auth-signout" disabled={leaving} onClick={() => { void logout() }}>{leaving ? 'Signing out…' : 'Sign out on this browser'}</button>}
    {failed && <p role="alert">Unable to finish signing out. Please try again.</p>}
  </>
}
