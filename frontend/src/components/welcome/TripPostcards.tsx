import PriceBadge from './PriceBadge'

export default function TripPostcards() {
  return (
    <div className="welcome-postcards">
      <svg viewBox="0 0 620 620" aria-hidden="true" className="welcome-seascape">
        <circle cx="310" cy="310" r="300" fill="#EFD9C2" />
        <circle cx="310" cy="250" r="120" fill="#E9A15A" />
        <path d="M10 360c80-30 160-30 240 0s160 30 240 0 80-20 120-10v260H10z" fill="#2C5C8A" />
        <path d="M10 420c80-25 160-25 240 0s160 25 240 0 80-15 120-8" stroke="#F6EBDD" strokeWidth="5" fill="none" />
      </svg>
      <figure className="welcome-trip-card" aria-labelledby="sample-trip-caption">
        <figcaption id="sample-trip-caption" className="welcome-sample-label">Sample trip · Example only</figcaption>
        <div className="welcome-trip-heading"><span>Rome</span><span className="welcome-nights">5 NIGHTS</span></div>
        <span className="welcome-trip-details">From Istanbul · 10–15 Nov · 2 adults</span>
        <div className="welcome-cost-row welcome-cost-row-first"><span>Flights <PriceBadge kind="sample" /></span><strong>$412</strong></div>
        <div className="welcome-cost-row"><span>Hotel <PriceBadge kind="unavailable" /></span><strong className="welcome-missing-price">—</strong></div>
        <div className="welcome-cost-row"><span>Activities <PriceBadge kind="estimate" /></span><strong>~$180</strong></div>
        <span className="welcome-budget-note">Budget uncertain · hotel price missing</span>
      </figure>
      <div className="welcome-day-card">
        <span className="welcome-day-label">DAY 2 · 11 NOV</span>
        <span className="welcome-day-title">Colosseum, Forum &amp; gelato</span>
        <span className="welcome-day-details">3 activities · ~$65 estimated</span>
      </div>
    </div>
  )
}
