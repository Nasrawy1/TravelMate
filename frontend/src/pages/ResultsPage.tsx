import { lazy, Suspense, useState, useLayoutEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import RivieraLogo from '../components/welcome/RivieraLogo'
import AuthNavigationLink from '../components/auth/AuthNavigationLink'
import { useTripResult } from '../components/results/TripResultProvider'
import TripResults from '../components/results/TripResults'
import type { ResultsData } from '../types/results'
import '../styles/trip-planner.css'
import '../styles/results.css'

const ResultsFixturePreview = import.meta.env.DEV ? lazy(() => import('../components/results/ResultsFixturePreview')) : null

export default function ResultsPage() {
  const { response } = useTripResult()
  const [preview, setPreview] = useState<ResultsData | null>(null)
  const data: ResultsData | null = response ? { response, context: { data_mode: 'validated_api', live_evidence: false } } : preview
  const main = useRef<HTMLElement>(null)
  useLayoutEffect(() => { main.current?.focus() }, [response])
  return <div className="trip-planner trip-results">
    <a className="skip-link" href="#results-content">Skip to results</a>
    {data?.context.data_mode === 'structural_mock' && <div className="res-mock-banner" role="note" aria-label="Mock data notice"><strong>MOCK</strong><span>Sample prices, not live. Test data only; nothing is sent or saved.</span></div>}
    <header className="tp-header"><div className="tp-container tp-header-inner"><RivieraLogo /><nav className="tp-nav" aria-label="Main navigation"><Link to="/trip-planner">Plan a trip</Link><AuthNavigationLink /></nav></div></header>
    <main className="tp-container res-page-main" id="results-content" ref={main} tabIndex={-1}>
      {!response && ResultsFixturePreview && <Suspense fallback={<p role="status">Loading development fixture controls…</p>}><ResultsFixturePreview selected={data?.context.data_mode === 'structural_mock' ? data.context.fixtureCase.file.replace(/\.json$/, '') : ''} onPreview={setPreview} /></Suspense>}
      {response && <p className="res-provenance" role="note"><strong>Real trip results · API-generated</strong> · Prices reflect the reported retrieval time. Availability and final prices are not guaranteed. This trip is held only in memory; reloading clears it.</p>}
      {data ? <>
        {data.context.data_mode === 'structural_mock' && <p className="res-provenance" role="status">MOCK source: docs/fixtures/{data.context.fixtureCase.file} · contract {data.context.manifest.contract_version} · data_mode={data.context.manifest.data_mode} · live_evidence=false · test date {data.context.manifest.validation_today_utc} UTC · HTTP {data.context.fixtureCase.http_status}</p>}
        <TripResults {...data} />
      </> : <section className="res-empty res-card" aria-labelledby="res-empty-heading"><h1 id="res-empty-heading">No trip result yet</h1><p>No generated trip is retained in this session. Generate a trip in Trip Planner to see its results. Reloading or leaving the planning flow clears retained results.</p><Link className="res-action" to="/trip-planner">Open Trip Planner</Link></section>}
    </main>
  </div>
}
