import { useLayoutEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import type { GenerationFailure, GenerationState } from '../../services/generation'
import '../../styles/generation.css'

const STEPS = ['Checking your trip details', 'Searching flight prices', 'Searching hotel prices', 'Building your day-by-day plan', 'Checking it against your budget']

export default function GenerationView({ state, remaining, onEdit, onRetry }: {
  state: Exclude<GenerationState<{ generation_status: 'complete' }>, { status: 'idle' }>
  remaining: number
  onEdit: (fields?: GenerationFailure['fields']) => void
  onRetry: () => void
}) {
  const heading = useRef<HTMLHeadingElement>(null)
  useLayoutEffect(() => { heading.current?.focus() }, [state.status])
  const { request } = state
  const nights = (Date.parse(`${request.return_date}T00:00:00Z`) - Date.parse(`${request.start_date}T00:00:00Z`)) / 86_400_000
  const error = state.status === 'error' ? state.error : null
  const mock = state.context.data_mode !== 'api'
  return <section className="generation-view" aria-label="Generation lifecycle">
    <div className="gen-top-actions"><button type="button" className="gen-secondary" onClick={() => onEdit(error?.fields)}>{state.status === 'pending' ? 'Cancel preview and edit trip' : 'Edit trip'}</button></div>
    <svg className={state.status === 'pending' ? 'gen-scene gen-bob' : 'gen-scene'} width="180" height="180" viewBox="0 0 180 180" aria-hidden="true">
      <defs><clipPath id="generation-scene-clip"><circle cx="90" cy="90" r="88" /></clipPath></defs>
      <g clipPath="url(#generation-scene-clip)"><circle cx="90" cy="90" r="88" fill="var(--gen-sand-deep)" /><circle cx="90" cy="72" r="38" fill="var(--gen-sun)" /><path d="M0 104c22-9 44-9 66 0s44 9 66 0 34-7 48-3v80H0z" fill="var(--gen-sea)" /><path d="M0 124c22-8 44-8 66 0s44 8 66 0 34-6 48-2" stroke="var(--gen-sand-deep)" strokeWidth="4" fill="none" /></g>
    </svg>
    <p className="gen-trip-summary">{request.departure_city} → {request.destination_city} · {nights} night{nights === 1 ? '' : 's'} · {request.adults} adult{request.adults === 1 ? '' : 's'} · {new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(request.budget_usd)}</p>
    {error ? <div className="gen-error-card" role="alert">
      <h1 ref={heading} tabIndex={-1}>{error.title}</h1>
      <p>{error.message}</p>
      <div className="gen-actions">
        {error.canRetry && <button type="button" className="gen-primary" onClick={onRetry} disabled={remaining > 0}>{remaining > 0 ? `Try again in ${remaining} s` : mock ? 'Retry MOCK preview' : 'Try again'}</button>}
        {error.signIn && <Link className="gen-primary" to="/login">Sign in</Link>}
        <button type="button" className="gen-secondary" onClick={() => onEdit(error.fields)}>Edit trip</button>
      </div>
      {error.code === 'RATE_LIMITED' && <p className="gen-small">{error.retryAt === undefined ? 'Retry-After was not provided or was invalid. Retry manually later.' : 'The waiting period never starts a retry automatically.'}</p>}
      <p className="gen-reference">{error.httpStatus ? `${error.httpStatus} ` : ''}{error.code}{error.requestId ? ` · Reference ${error.requestId}` : ' · No valid request reference available'}</p>
    </div> : <>
      <h1 ref={heading} tabIndex={-1}>{state.status === 'pending' ? 'Building your trip…' : 'Trip response validated'}</h1>
      {state.status === 'pending' ? <>
        <p role="status">{mock ? 'MOCK pending operation. No backend or providers are being contacted.' : 'Waiting for a validated response from the planning service.'}</p>
        <ol className="gen-steps" aria-label="Generation stages — visual guide only" aria-busy="true">
          {STEPS.map((label, index) => <li key={label} className={index === 0 ? 'gen-step-active' : ''}>
            <span className="gen-step-icon" aria-hidden="true">{index === 0 ? <svg className="gen-spin" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round"><path d="M12 3a9 9 0 1 0 9 9" /></svg> : index + 1}</span>
            <span>{label}</span><span className="gen-step-status">{index === 0 ? 'Pending' : 'Unverified'}</span>
          </li>)}
        </ol>
        <p className="gen-small">Visual guide only. Individual provider steps are not reported or verified. Nothing is complete until the full response is validated.</p>
      </> : <p role="status">The response passed the supplied contract validator. Results rendering is not connected in this increment.</p>}
    </>}
  </section>
}
