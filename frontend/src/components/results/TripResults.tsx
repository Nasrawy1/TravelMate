import { Link } from 'react-router-dom'
import type { ResultsData } from '../../types/results'
import { formatDate, formatMoney, warningTitle } from '../../utils/results'
import BudgetExpenses from './BudgetExpenses'
import DailyItinerary from './DailyItinerary'
import TravelOffers from './TravelOffers'

/** Presentation only: callers must supply validated v0.4 data AND its provenance context. */
export default function TripResults({ response, context }: ResultsData) {
  const { trip, budget } = response
  return <>
    <section className="res-trip-summary" aria-label="Trip summary">
      <svg className="res-decoration" width="320" height="200" viewBox="0 0 320 200" aria-hidden="true"><circle cx="200" cy="90" r="70" fill="var(--res-sun)" /><path d="M0 120c50-18 100-18 150 0s100 18 150 0 20-6 20-6v86H0z" fill="var(--res-sea)" /></svg>
      <div><p className="res-eyebrow">{context.data_mode === 'offline_demo' ? 'DEMO TRIP · SAMPLE DATA' : context.data_mode === 'structural_mock' ? 'MOCK TRIP · TEST DATA' : 'YOUR TRIP'}</p>
        <h1>{trip.departure_city} → <em>{trip.destination_city}</em></h1>
        <p><time dateTime={trip.start_date}>{formatDate(trip.start_date)}</time> – <time dateTime={trip.return_date}>{formatDate(trip.return_date)}</time> · {trip.nights} night{trip.nights === 1 ? '' : 's'} · {trip.adults} adult{trip.adults === 1 ? '' : 's'} · Budget {formatMoney(budget.budget_usd)}</p>
      </div>
      <Link to={context.data_mode === 'offline_demo' ? '/signup' : '/trip-planner'}>{context.data_mode === 'offline_demo' ? 'Plan your own trip' : 'Plan a trip'}</Link>
    </section>
    {response.live_integration_status === 'no_price' && <div className="res-warning" role="status"><strong>No {context.data_mode !== 'validated_api' ? 'sample' : 'verified'} flight or hotel prices available</strong><p>The itinerary is present, but the budget has missing travel costs. Generation is not connected in this preview.</p></div>}
    {response.warnings.length > 0 && <section className="res-warnings" aria-label="Warnings" role="status">{response.warnings.map((warning, index) => <p className="res-warning" key={`${warning.code}-${index}`}><strong>{warningTitle(warning.code)}</strong> {warning.message}</p>)}</section>}
    <div className="res-columns"><BudgetExpenses response={response} context={context} /><div className="res-main-column"><TravelOffers response={response} context={context} /><DailyItinerary response={response} context={context} /></div></div>
  </>
}
