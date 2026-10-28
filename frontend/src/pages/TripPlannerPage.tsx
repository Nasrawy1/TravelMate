import CityCombobox from '../components/trip/CityCombobox'
import { lazy, Suspense, useContext, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { useTripResult } from '../components/results/TripResultProvider'
import { Link, useNavigate } from 'react-router-dom'
import RivieraLogo from '../components/welcome/RivieraLogo'
import AuthNavigationLink from '../components/auth/AuthNavigationLink'
import type { TripResult } from '../types/results'
import { handoffGeneratedTrip } from '../services/tripResultHandoff'
import { GenerationController, watchGenerationIdentity } from '../services/generation'
import { validateGenerationResponse } from '../services/generationValidation'
import { realGenerationService } from '../services/api'
import GenerationView from '../components/generation/GenerationView'
import { AuthSessionContext, useAuthSessionState } from '../components/auth/AuthSessionProvider'
import { prepareTripRequest, utcToday, validateTripForm } from '../utils/tripPlanner'
import type { TripField, TripFormErrors, TripFormValues } from '../utils/tripPlanner'
import '../styles/trip-planner.css'

// Vite removes this entire import path and repository fixtures from production.
const GenerationDevTools = import.meta.env.DEV ? lazy(() => import('../components/generation/GenerationDevTools')) : null

const INITIAL_VALUES: TripFormValues = {
  departure_city: '', destination_city: '', start_date: '', return_date: '', adults: 2, budget_usd: '',
}

function Field({ name, label, error, children }: { name: TripField; label: string; error?: string; children: ReactNode }) {
  return <div className="tp-field">
    <label htmlFor={`tp-${name}`}>{label}</label>
    {children}
    {error && <span id={`tp-${name}-error`} className="tp-error">{error}</span>}
  </div>
}

export default function TripPlannerPage() {
  const [values, setValues] = useState<TripFormValues>(INITIAL_VALUES)
  const [submitted, setSubmitted] = useState(false)
  const [controller] = useState(() => new GenerationController<TripResult>(validateGenerationResponse))
  const generation = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot)
  const session = useAuthSessionState()
  const sessionSource = useContext(AuthSessionContext)
  const navigate = useNavigate()
  const { retain } = useTripResult()
  const requestOwner = useRef<string | null>(null)
  const handedOff = useRef<TripResult | null>(null)
  useLayoutEffect(() => {
    if (!sessionSource) return
    return watchGenerationIdentity(sessionSource, () => {
      requestOwner.current = null
      handedOff.current = null
      // cancel invalidates the unique local operation token before aborting. Late
      // success/error cannot revive it, even after returning to the same account.
      controller.cancel()
    })
  }, [sessionSource, controller])
  useEffect(() => {
    if (generation.status !== 'success' || handedOff.current === generation.response) return
    if (handoffGeneratedTrip(generation, requestOwner.current, session.status === 'authenticated' ? session.user?.id ?? null : null, retain, navigate)) {
      handedOff.current = generation.response
    } else controller.cancel()
  }, [generation, session.status, session.user?.id, retain, navigate, controller])
  const [clock, setClock] = useState(Date.now())
  const retryAt = controller.getRetryAt()
  const remaining = Math.max(0, Math.ceil((retryAt - clock) / 1000))
  const realActive = generation.status !== 'idle'
  useEffect(() => () => controller.cancel(), [controller])
  useEffect(() => {
    setClock(Date.now())
    if (!retryAt || retryAt <= Date.now()) return
    const timer = setInterval(() => { const now = Date.now(); setClock(now); if (now >= retryAt) clearInterval(timer) }, 250)
    return () => clearInterval(timer)
  }, [retryAt])
  const [previewActive, setPreviewActive] = useState(false)
  const [serviceErrors, setServiceErrors] = useState<TripFormErrors>({})
  const fields = useRef<Partial<Record<TripField, HTMLElement | null>>>({})
  const editFocus = useRef<TripField | null>(null)
  useLayoutEffect(() => {
    if (!previewActive && !realActive && editFocus.current) {
      fields.current[editFocus.current]?.focus()
      editFocus.current = null
    }
  }, [previewActive, realActive, serviceErrors])
  const { errors, nights } = validateTripForm(values)
  const valid = Object.keys(errors).length === 0
  const shownErrors = { ...serviceErrors, ...(submitted ? errors : {}) }
  const nightsOk = nights !== null && nights >= 1 && nights <= 7
  const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
  const summary = valid
    ? `${values.departure_city} → ${values.destination_city} · ${nights} night${nights === 1 ? '' : 's'} · ${values.adults} adult${values.adults === 1 ? '' : 's'} · ${money.format(Number(values.budget_usd))}`
    : 'Fill in every field to continue.'

  function update<K extends TripField>(name: K, value: TripFormValues[K]) {
    setValues(previous => ({ ...previous, [name]: value }))
    setServiceErrors(previous => { const next = { ...previous }; delete next[name]; return next })
  }

  function fieldProps(name: TripField, helperId: string) {
    return {
      id: `tp-${name}`, name, required: true,
      'aria-invalid': Boolean(shownErrors[name]),
      'aria-describedby': `${helperId}${shownErrors[name] ? ` tp-${name}-error` : ''}`,
      ref: (element: HTMLInputElement | HTMLSelectElement | null) => { fields.current[name] = element },
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (controller.getSnapshot().status === 'pending' || controller.getRetryAt() > Date.now()) return
    setSubmitted(true)
    setServiceErrors({})
    // Revalidate at submit time, including the UTC date if midnight passed while editing.
    const result = prepareTripRequest(values)
    if (result && !previewActive && session.status !== 'checking') {
      requestOwner.current = session.status === 'authenticated' ? session.user?.id ?? null : null
      void controller.start(result, realGenerationService)
    }
    if (!result) {
      const firstError = Object.keys(validateTripForm(values).errors)[0] as TripField
      fields.current[firstError]?.focus()
    }
  }

  function editReal(fieldsToEdit: TripFormErrors = {}) {
    editFocus.current = (Object.keys(fieldsToEdit)[0] ?? 'departure_city') as TripField
    controller.cancel()
    setServiceErrors(fieldsToEdit)
  }
  function retryReal() {
    const snapshot = controller.getSnapshot()
    if (snapshot.status === 'error' && snapshot.error.canRetry) {
      requestOwner.current = session.status === 'authenticated' ? session.user?.id ?? null : null
      void controller.start(snapshot.request, realGenerationService)
    }
  }

  function editAfterPreview(errors: TripFormErrors) {
    editFocus.current = (Object.keys(errors)[0] ?? 'departure_city') as TripField
    setPreviewActive(false)
    setServiceErrors(errors)
  }

  return <div className="trip-planner">
    <a className="skip-link" href="#trip-details">Skip to trip details</a>
    <header className="tp-header">
      <div className="tp-container tp-header-inner">
        <RivieraLogo />
        <nav aria-label="Main navigation" className="tp-nav">
          <Link to="/trip-planner" aria-current="page">Plan a trip</Link>
          <AuthNavigationLink />
        </nav>
      </div>
    </header>
    <main className="tp-container tp-main" id="trip-details" tabIndex={-1}>
      <div className="tp-intro" hidden={previewActive || realActive}>
        <h1>Where to <em>next?</em></h1>
        <p>Tell us the basics. Start with your route, dates and whole-trip budget.</p>
      </div>
      <div className="tp-mock-notice"><span>Choose your destination, dates, and budget to plan your trip.</span></div>
      <div className="tp-columns" hidden={previewActive || realActive}>
        <form className="tp-form" aria-label="Trip details" noValidate onSubmit={submit}>
          {submitted && !valid && <div role="alert" className="tp-error-banner">Please fix the highlighted fields.</div>}
          {Object.keys(serviceErrors).length > 0 && <div role="alert" className="tp-error-banner">Please check the highlighted fields. Your inputs are unchanged.</div>}
          <fieldset>
            <legend>Route</legend>
            <div className="tp-row tp-route">
              <Field name="departure_city" label="From" error={shownErrors.departure_city}>
                <CityCombobox {...fieldProps('departure_city', 'tp-cities-help')} value={values.departure_city} onValueChange={value => update('departure_city', value)} />
              </Field>
              <button type="button" className="tp-swap" aria-label="Swap cities" onClick={() => {
                setValues(previous => ({ ...previous, departure_city: previous.destination_city, destination_city: previous.departure_city }))
                            setServiceErrors({})
              }}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 8h14l-4-4M20 16H6l4 4" /></svg>
              </button>
              <Field name="destination_city" label="To" error={shownErrors.destination_city}>
                <CityCombobox {...fieldProps('destination_city', 'tp-cities-help')} value={values.destination_city} onValueChange={value => update('destination_city', value)} />
              </Field>
            </div>
            <p id="tp-cities-help" className="tp-help">Search by city name or supported alias. Country codes identify the mapped country. Supported cities do not guarantee available offers.</p>
          </fieldset>
          <fieldset>
            <legend>Dates</legend>
            <div className="tp-row tp-dates">
              <Field name="start_date" label="Start date" error={shownErrors.start_date}>
                <input {...fieldProps('start_date', 'tp-dates-help')} type="date" value={values.start_date} onChange={event => update('start_date', event.target.value)} />
              </Field>
              <Field name="return_date" label="Return date" error={shownErrors.return_date}>
                <input {...fieldProps('return_date', 'tp-dates-help')} type="date" value={values.return_date} onChange={event => update('return_date', event.target.value)} />
              </Field>
              <div className="tp-stay"><span className="tp-label" id="tp-stay-label">Stay</span>
                <output aria-labelledby="tp-stay-label" className={`tp-nights ${nights === null ? '' : nightsOk ? 'tp-nights-ok' : 'tp-nights-error'}`}>
                  {nights === null ? '— nights' : `${nights} night${nights === 1 ? '' : 's'}`}
                </output>
              </div>
            </div>
            <p id="tp-dates-help" className="tp-help">1 to 7 nights. Both dates must be after today in UTC ({utcToday()}). The return date is the day you fly home.</p>
          </fieldset>
          <div className="tp-row tp-travellers-budget">
            <fieldset>
              <legend>Travellers</legend>
              <span id="tp-adults-label" className="tp-label">Adults</span>
              <div className="tp-stepper" role="group" aria-labelledby="tp-adults-label" aria-describedby={`tp-adults-help${shownErrors.adults ? ' tp-adults-error' : ''}`} aria-invalid={Boolean(shownErrors.adults)} tabIndex={-1} ref={element => { fields.current.adults = element }}>
                <button type="button" aria-label="Fewer adults" disabled={values.adults <= 1} onClick={() => update('adults', Math.max(1, values.adults - 1))}>−</button>
                <output aria-label="Adult count">{values.adults}</output>
                <button type="button" aria-label="More adults" disabled={values.adults >= 4} onClick={() => update('adults', Math.min(4, values.adults + 1))}>+</button>
              </div>
              {shownErrors.adults && <span className="tp-error" id="tp-adults-error">{shownErrors.adults}</span>}
              <p id="tp-adults-help" className="tp-help">1–4 adults. Children aren't supported yet.</p>
            </fieldset>
            <fieldset>
              <legend>Budget</legend>
              <Field name="budget_usd" label="Total for everyone (USD)" error={shownErrors.budget_usd}>
                <div className="tp-money"><span aria-hidden="true">$</span>
                  <input {...fieldProps('budget_usd', 'tp-budget-help')} type="number" inputMode="decimal" step="any" placeholder="1500" value={values.budget_usd} onChange={event => update('budget_usd', event.target.value)} />
                </div>
              </Field>
              <p id="tp-budget-help" className="tp-help">Flights, hotel, activities and food, for the whole trip and all adults.</p>
            </fieldset>
          </div>
          <div className="tp-submit-row">
            <p className="tp-summary" aria-live="polite">{summary}</p>
            <button className="tp-submit" type="submit" disabled={generation.status === 'pending' || remaining > 0 || session.status === 'checking'}>{session.status === 'checking' ? 'Checking session…' : remaining > 0 ? `Try again in ${remaining} s` : 'Generate Trip'} <span aria-hidden="true">→</span></button>
          </div>
        </form>
        <aside className="tp-aside">
          <section aria-labelledby="tp-know-heading">
            <h2 id="tp-know-heading">Good to know</h2>
            <ul>
              <li>Generation requires sign-in. Failures keep your inputs for editing or a deliberate retry; generation is never retried automatically.</li>
              <li>Results show <b>Retrieved prices</b>, <b>Estimates</b> and <b>Unavailable</b> costs. Retrieved prices reflect their source and retrieval time; availability and final prices can change.</li>
              <li>A missing price will never be counted as $0.00.</li>
              <li>TravelMate plans trips. It doesn't book or take payments.</li>
            </ul>
          </section>
        </aside>
      </div>
      {generation.status !== 'idle' && <GenerationView state={generation} remaining={remaining} onRetry={retryReal} onEdit={editReal} />}
      {!realActive && GenerationDevTools && <Suspense fallback={<p role="status">Loading development preview controls…</p>}>
        <GenerationDevTools request={prepareTripRequest(values)} onActiveChange={setPreviewActive} onEdit={editAfterPreview} />
      </Suspense>}
    </main>
  </div>
}
