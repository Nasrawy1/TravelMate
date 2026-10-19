import { lazy, Suspense, useState } from 'react'
import { Link } from 'react-router-dom'
import RivieraLogo from '../components/welcome/RivieraLogo'
import AuthNavigationLink from '../components/auth/AuthNavigationLink'
import TripResults from '../components/results/TripResults'
import type { ResultsData } from '../types/results'
import '../styles/trip-planner.css'
import '../styles/results.css'

const ResultsFixturePreview = import.meta.env.DEV ? lazy(() => import('../components/results/ResultsFixturePreview')) : null

export default function ResultsPage() {
  const [data, setData] = useState<ResultsData | null>(null)
  return <div className="trip-planner trip-results">
    <a className="skip-link" href="#results-content">Skip to results</a>
    {data?.context.data_mode === 'structural_mock' && <div className="res-mock-banner" role="note" aria-label="Mock data notice"><strong>MOCK</strong><span>Sample prices, not live. Test data only; nothing is sent or saved.</span></div>}
    <header className="tp-header"><div className="tp-container tp-header-inner"><RivieraLogo /><nav className="tp-nav" aria-label="Main navigation"><Link to="/trip-planner">Plan a trip</Link><AuthNavigationLink /></nav></div></header>
    <main className="tp-container res-page-main" id="results-content" tabIndex={-1}>
      {ResultsFixturePreview && <Suspense fallback={<p role="status">Loading development fixture controls…</p>}><ResultsFixturePreview selected={data?.context.data_mode === 'structural_mock' ? data.context.fixtureCase.file.replace(/\.json$/, '') : ''} onPreview={setData} /></Suspense>}
      {data ? <>
        {data.context.data_mode === 'structural_mock' && <p className="res-provenance" role="status">MOCK source: docs/fixtures/{data.context.fixtureCase.file} · contract {data.context.manifest.contract_version} · data_mode={data.context.manifest.data_mode} · live_evidence=false · test date {data.context.manifest.validation_today_utc} UTC · HTTP {data.context.fixtureCase.http_status}</p>}
        <TripResults {...data} />
      </> : <section className="res-empty res-card" aria-labelledby="res-empty-heading"><h1 id="res-empty-heading">No trip result yet</h1><p>No generated itinerary has been loaded. Real trip generation is not yet connected to FastAPI.</p><Link className="res-action" to="/trip-planner">Open Trip Planner</Link></section>}
    </main>
  </div>
}
