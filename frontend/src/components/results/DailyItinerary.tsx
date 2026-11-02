import type { ResultsData } from '../../types/results'
import { formatDate } from '../../utils/results'
import ResultPrice from './ResultPrice'

export default function DailyItinerary({ response, context }: ResultsData) {
  return <section className="res-section" aria-labelledby="res-itinerary-heading">
    <div className="res-section-heading"><h2 id="res-itinerary-heading">Day by day</h2><p className="res-small">Activity costs cover all {response.trip.adults} travellers. Estimates are not verified prices.</p></div>
    {response.itinerary.map((day, index) => <article className="res-day res-card" key={day.date} aria-labelledby={`res-day-${index}`}>
      <div className="res-day-heading"><span>Day {index + 1}</span><h3 id={`res-day-${index}`}><time dateTime={day.date}>{formatDate(day.date, true)}</time></h3></div>
      {day.activities.length === 0 ? <p className="res-empty-day">{day.empty_day_reason ?? 'No activities were provided for this day.'}</p>
        : <ol className="res-activities">{day.activities.map(activity => <li key={activity.order} value={activity.order}>
          <span className="res-activity-number" aria-hidden="true">{activity.order}</span>
          <div className="res-activity-copy"><h4>{activity.name} <span>· {activity.area}</span></h4><p>{activity.description}</p></div>
          <ResultPrice activity price={activity.cost} context={context} />
        </li>)}</ol>}
    </article>)}
  </section>
}
