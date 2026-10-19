import { useContext, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import PasswordRecoveryLayout from '../../components/auth/PasswordRecoveryLayout'
import { AuthSessionContext, useAuthSession } from '../../components/auth/AuthSessionProvider'
import { api } from '../../services/api'
import { ApiError } from '../../services/apiClient'
import type { ApiResponse } from '../../services/apiClient'

/** Return only the comparison, never the response body or either user identifier. */
export function probeIdentityMatches(response: ApiResponse, expectedId: string): boolean | null {
  if (response.status !== 200 || typeof response.body !== 'object' || response.body === null || Array.isArray(response.body)) return null
  const body = response.body as Record<string, unknown>
  if (body.status !== 'ok' || typeof body.user_id !== 'string' || !body.user_id || !expectedId) return null
  return body.user_id === expectedId
}

export default function AuthProbePage() {
  const auth = useAuthSession()
  const sessionController = useContext(AuthSessionContext)
  const request = useRef<AbortController | null>(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{ status: number | null; matches: boolean | null } | null>(null)

  useEffect(() => {
    // Account changes and navigation invalidate any previous comparison or pending request.
    request.current?.abort(); request.current = null
    setResult(null); setLoading(false)
    return () => { request.current?.abort(); request.current = null }
  }, [auth.status, auth.user?.id])

  async function runProbe() {
    if (request.current || auth.status !== 'authenticated' || !auth.user) return
    const expectedId = auth.user.id
    const operation = new AbortController()
    request.current = operation
    setLoading(true); setResult(null)
    const stillCurrent = () => {
      const current = sessionController?.getSnapshot()
      return request.current === operation && !operation.signal.aborted
        && current?.status === 'authenticated' && current.user?.id === expectedId
    }
    try {
      const response = await api.request('/api/v1/auth/probe', { signal: operation.signal })
      if (stillCurrent()) setResult({ status: response.status, matches: probeIdentityMatches(response, expectedId) })
    } catch (error) {
      if (stillCurrent()) setResult({ status: error instanceof ApiError ? error.status ?? null : null, matches: null })
    } finally {
      if (request.current === operation) { request.current = null; setLoading(false) }
    }
  }

  return <PasswordRecoveryLayout title="JWT probe" description="Temporary development tool. Runs one protected API request only when you choose.">
    {auth.status !== 'authenticated' && <p role="status">{auth.status === 'checking' ? 'Checking your sign-in…' : 'Sign in before running this test.'}</p>}
    <p>Requires your local VITE_API_BASE_URL configuration. No tokens or user IDs are displayed.</p>
    <button type="button" className="login-submit" disabled={loading || auth.status !== 'authenticated'} aria-busy={loading} onClick={() => { void runProbe() }}>
      {loading ? 'Checking JWT probe…' : 'Run JWT probe'}
    </button>
    <div role="status" aria-atomic="true" className="recovery-acknowledgement">
      <p>HTTP status: <strong>{result ? result.status ?? 'No response' : 'Not checked'}</strong></p>
      <p>Identity matches: <strong>{result?.matches === true ? 'Yes' : result?.matches === false ? 'No' : 'Not verified'}</strong></p>
    </div>
    <Link to={auth.status === 'authenticated' ? '/' : '/login'}>{auth.status === 'authenticated' ? 'Return home' : 'Go to sign in'}</Link>
  </PasswordRecoveryLayout>
}
