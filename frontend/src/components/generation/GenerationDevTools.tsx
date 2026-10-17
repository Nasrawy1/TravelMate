import { useEffect, useLayoutEffect, useState, useSyncExternalStore } from 'react'
import { createGenerationMock, GENERATION_PREVIEWS } from '../../fixtures/generationMocks'
import { GenerationController } from '../../services/generation'
import type { TripGenerateRequest } from '../../types/trip'
import type { TripFormErrors } from '../../utils/tripPlanner'
import GenerationView from './GenerationView'

export default function GenerationDevTools({ request, onActiveChange, onEdit }: {
  request: TripGenerateRequest | null
  onActiveChange: (active: boolean) => void
  onEdit: (fields: TripFormErrors) => void
}) {
  // No success fixture or permissive response validator: a preview cannot create a trip.
  const [controller] = useState(() => new GenerationController<{ generation_status: 'complete' }>(() => null))
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot)
  const [scenario, setScenario] = useState<string>('pending')
  const [clock, setClock] = useState(Date.now())
  const active = state.status !== 'idle'
  const retryAt = controller.getRetryAt() || undefined
  const remaining = Math.max(0, Math.ceil(((retryAt ?? 0) - clock) / 1000))
  useLayoutEffect(() => { onActiveChange(active) }, [active, onActiveChange])
  useEffect(() => () => controller.cancel(), [controller])
  useEffect(() => {
    setClock(Date.now())
    if (retryAt === undefined) return
    const timer = setInterval(() => { const now = Date.now(); setClock(now); if (now >= retryAt) clearInterval(timer) }, 250)
    return () => clearInterval(timer)
  }, [retryAt])

  function start() {
    const input = state.status === 'idle' ? request : state.request
    if (input) void controller.start(input, createGenerationMock(scenario))
  }
  function edit(fields: TripFormErrors = {}) {
    controller.cancel()
    onEdit(fields)
  }

  return <div className="gen-development">
    <details className="gen-tools" open={active || undefined}>
      <summary>Development only · MOCK generation previews</summary>
      <p>No authentication, backend calls or successful trips. Check valid trip details above before opening a preview.</p>
      <label htmlFor="generation-preview-scenario">MOCK scenario</label>
      <select id="generation-preview-scenario" value={scenario} disabled={active} onChange={event => setScenario(event.target.value)}>
        {GENERATION_PREVIEWS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      {!active && <button type="button" className="gen-secondary" disabled={!request || remaining > 0} onClick={start}>{remaining > 0 ? `Inspect MOCK state in ${remaining} s` : 'Inspect MOCK state'}</button>}
      {active && <p className="gen-small"><strong>MOCK · {state.context.data_mode === 'structural_mock' ? 'Repository error fixture' : 'Frontend-only development example'}</strong> · live_evidence=false</p>}
      {active && state.context.fixture && <p className="gen-small">Source: docs/fixtures/{state.context.fixture.file}. Original manifest, HTTP status, headers and response are retained. Dates use the manifest’s fixed test clock, not verified travel availability.</p>}
    </details>
    {state.status !== 'idle' && <GenerationView state={state} remaining={remaining} onRetry={start} onEdit={edit} />}
  </div>
}
