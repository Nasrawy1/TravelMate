import { Link, useSearchParams } from 'react-router-dom'
import RivieraLogo from '../components/welcome/RivieraLogo'
import TripResults from '../components/results/TripResults'
import { getOfflineDemoTrip, OFFLINE_DEMO_IDS } from '../data/offlineDemo'
import '../styles/trip-planner.css'
import '../styles/results.css'
import '../styles/offline-demo.css'

export default function OfflineDemoPage() {
  const [params, setParams] = useSearchParams()
  const sample = getOfflineDemoTrip(params.get('trip') ?? '') ?? getOfflineDemoTrip('rome')!
  return <div className="trip-planner trip-results offline-demo">
    <a className="skip-link" href="#demo-content">Skip to demo results</a>
    <div className="demo-banner" role="note" aria-label="Demo data notice">
      <strong>DEMO</strong><span>{sample.provenance.notice}</span>
    </div>
    <header className="tp-header"><div className="tp-container tp-header-inner">
      <RivieraLogo />
      <nav className="tp-nav" aria-label="Demo navigation"><Link to="/">Exit demo</Link><Link className="demo-create-account" to="/signup">Create account</Link></nav>
    </div></header>
    <main className="tp-container res-page-main" id="demo-content" tabIndex={-1}>
      <div className="demo-trip-picker" role="group" aria-label="Choose a demo trip">
        {OFFLINE_DEMO_IDS.map(id => <button key={id} type="button" aria-pressed={sample.id === id} aria-controls="demo-results" onClick={() => setParams({ trip: id })}>
          {getOfflineDemoTrip(id)!.label}
        </button>)}
      </div>
      <p className="demo-selection-status" role="status">Showing {sample.label} · DEMO sample trip</p>
      <div id="demo-results"><TripResults response={sample.response} context={{ data_mode: 'offline_demo', live_evidence: false }} /></div>
    </main>
  </div>
}
