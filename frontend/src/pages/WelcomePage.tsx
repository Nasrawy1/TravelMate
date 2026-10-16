import { Link } from 'react-router-dom'
import PriceBadge from '../components/welcome/PriceBadge'
import RivieraLogo from '../components/welcome/RivieraLogo'
import TripPostcards from '../components/welcome/TripPostcards'
import '../styles/welcome.css'

const steps = [
  { title: 'Tell us your trip', description: 'Two cities, your dates (1–7 nights), 1–4 adults and one total budget in USD.' },
  { title: 'We find prices and plan', description: 'Available live flight or hotel prices, then AI builds your day-by-day itinerary around them.' },
  { title: 'See if it fits', description: 'Within budget, over budget, or uncertain, with every cost and where it came from.' },
]

export default function WelcomePage() {
  return (
    <div className="welcome">
      <a className="skip-link" href="#welcome-content">Skip to content</a>
      <header className="welcome-header welcome-container">
        <RivieraLogo />
        <nav aria-label="Main" className="welcome-nav">
          <a href="#how">How it works</a>
          <a href="#demo">Demo trips</a>
          <Link to="/login">Sign in</Link>
          <Link to="/signup" className="welcome-button welcome-button-primary welcome-nav-cta">Get started</Link>
        </nav>
      </header>
      <main id="welcome-content" className="welcome-main" tabIndex={-1}>
        <section className="welcome-hero welcome-container" aria-labelledby="welcome-title">
          <div className="welcome-hero-copy">
            <span className="welcome-eyebrow">AI trip planner · one budget</span>
            <h1 id="welcome-title">Sun, sea and a plan that <em>fits.</em></h1>
            <p className="welcome-intro">Pick your cities, dates and budget. Get a day-by-day itinerary with real flight or hotel prices, and a straight answer on whether it all fits.</p>
            <div className="welcome-actions">
              <Link to="/signup" className="welcome-button welcome-button-primary">Plan my trip</Link>
              <a href="#demo" className="welcome-button welcome-button-secondary">See a demo</a>
            </div>
            <p className="welcome-account">Already have an account? <Link to="/login">Sign in</Link></p>
          </div>
          <TripPostcards />
        </section>
        <section id="how" className="welcome-how welcome-container" aria-labelledby="how-title">
          <h2 id="how-title">How it works</h2>
          <ol className="welcome-step-grid">
            {steps.map((step, index) => (
              <li className="welcome-step" key={step.title}>
                <span className={`welcome-step-number welcome-step-number-${index + 1}`}>{index + 1}</span>
                <h3>{step.title}</h3>
                <p>{step.description}</p>
              </li>
            ))}
          </ol>
        </section>
        <section className="welcome-pricing welcome-container" aria-labelledby="pricing-title">
          <div className="welcome-pricing-panel">
            <div className="welcome-pricing-copy">
              <h2 id="pricing-title">Every price says where it came from.</h2>
              <p>No made-up numbers. If a price is missing, we show it, and your budget status says so.</p>
            </div>
            <div className="welcome-price-grid">
              <div className="welcome-price-explanation"><span className="welcome-badge welcome-badge-live">Live</span><p>Verified provider-sourced data, with name and time. Sample prices are never live.</p></div>
              <div className="welcome-price-explanation"><PriceBadge kind="estimate" /><p>A reasonable guess, never shown as live.</p></div>
              <div className="welcome-price-explanation"><PriceBadge kind="unavailable" /><p>No price found. Never counted as $0.</p></div>
              <div className="welcome-price-explanation">
                <div className="welcome-budget-labels"><span className="welcome-badge welcome-badge-within">Within</span><span className="welcome-badge welcome-badge-over">Over</span><span className="welcome-badge welcome-badge-uncertain">Uncertain</span></div>
                <p>Your budget status, from the numbers.</p>
              </div>
            </div>
          </div>
        </section>
        <section id="demo" className="welcome-demo" aria-labelledby="demo-title">
          <svg viewBox="0 0 1440 60" preserveAspectRatio="none" aria-hidden="true" className="welcome-demo-wave"><path d="M0 0h1440v20c-120 30-240 30-360 0s-240-30-360 0-240 30-360 0S120-10 0 20z" fill="#F6EBDD" /></svg>
          <div className="welcome-demo-content welcome-container">
            <div className="welcome-demo-heading">
              <span className="welcome-demo-badge">DEMO</span>
              <h2 id="demo-title">Try it without an account</h2>
              <p>Ready-made sample trips will work offline, use no live prices, and save nothing. Demo trips are being prepared; these cards open the demo placeholder.</p>
            </div>
            <div className="welcome-demo-grid">
              {[1, 2, 3].map((number) => (
                <Link to="/offline-demo" className="welcome-demo-card" key={number} aria-label={`Demo trip ${number} — open demo placeholder`}>
                  <span className="welcome-demo-card-label">DEMO TRIP {number}</span>
                  <span className="welcome-demo-card-title">[City A → City B]</span>
                  <span className="welcome-demo-card-details">[Nights] · [Adults] · [Budget]</span>
                  <span className="welcome-demo-card-link">Open demo <span aria-hidden="true">→</span></span>
                </Link>
              ))}
            </div>
          </div>
        </section>
      </main>
      <footer className="welcome-footer">
        <div className="welcome-container welcome-footer-content">
          <span>TravelMate · Graduation project</span>
          <span>We plan trips. We never book or take payments.</span>
        </div>
      </footer>
    </div>
  )
}
