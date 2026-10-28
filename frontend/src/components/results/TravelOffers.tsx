import type { FlightOffer, HotelOffer, OfferTaxes, ResultsData } from '../../types/results'
import { formatDate, formatMoney, formatTimestamp, providerLabel, selectedFirst } from '../../utils/results'
import ResultPrice from './ResultPrice'

function Taxes({ taxes }: { taxes: OfferTaxes }) {
  return <p className={`res-taxes res-taxes-${taxes.status}`}>{taxes.status === 'included' ? 'Taxes and fees included'
    : taxes.status === 'unknown' ? 'Taxes and fees unknown'
      : `+ ${formatMoney(taxes.additional_amount_usd)} taxes and fees (added in the budget)`}</p>
}

function OfferCard({ offer, kind, selected, context }: { offer: FlightOffer | HotelOffer; kind: 'flight' | 'hotel'; selected: boolean; context: ResultsData['context'] }) {
  const flight = 'airline' in offer ? offer : null
  const hotel = 'name' in offer ? offer : null
  const title = flight ? flight.airline : hotel!.name
  return <article className={`res-offer ${selected ? 'res-selected' : ''}`} id={`offer-${offer.id}`} data-offer-id={offer.id} data-selected={selected} aria-label={`${kind === 'flight' ? 'Flight' : 'Hotel'} offer ${title}${selected ? ', selected' : ''}`}>
    <div className="res-offer-heading"><h4>{title}</h4>{selected && <span className="res-selected-badge">Selected</span>}</div>
    {flight && <div className="res-offer-lines"><p>{flight.departure_airport_code} → {flight.arrival_airport_code} · round trip</p>
      <p>Out <time dateTime={flight.outbound_departure_at}>{formatTimestamp(flight.outbound_departure_at)}</time></p>
      <p>Return <time dateTime={flight.return_departure_at}>{formatTimestamp(flight.return_departure_at)}</time></p></div>}
    {hotel && <div className="res-offer-lines"><p>{hotel.area ?? 'Area not provided'}</p><p>Check-in <time dateTime={hotel.check_in}>{formatDate(hotel.check_in)}</time> · Check-out <time dateTime={hotel.check_out}>{formatDate(hotel.check_out)}</time></p>
      <p>{hotel.occupancy_adults} adult{hotel.occupancy_adults === 1 ? '' : 's'} · {hotel.room_qty === null ? 'rooms not provided' : `${hotel.room_qty} room${hotel.room_qty === 1 ? '' : 's'}`}</p></div>}
    <div className="res-offer-price"><span>{flight ? `Total for ${flight.adults} adults` : `Total stay, ${hotel!.occupancy_adults} adults`}</span><ResultPrice price={offer.price} context={context} /></div>
    <Taxes taxes={offer.taxes} />
    <p className="res-source">{context.data_mode === 'offline_demo' ? `Sample data · ${offer.source} · sample timestamp ` : <>Source: {offer.source}{context.data_mode === 'structural_mock' ? ' (sample)' : ''} · retrieved </>}<time dateTime={offer.retrieved_at}>{formatTimestamp(offer.retrieved_at)}</time></p>
  </article>
}

export default function TravelOffers({ response, context }: ResultsData) {
  return <section className="res-section" aria-labelledby="res-offers-heading">
    <h2 id="res-offers-heading">Flight and hotel</h2>
    <div className="res-offer-columns">
      {(['flights', 'hotels'] as const).map(category => {
        const options = response.travel_options[category]
        const selectedId = category === 'flights' ? response.budget.selected_flight_offer_id : response.budget.selected_hotel_offer_id
        const kind = category === 'flights' ? 'flight' : 'hotel'
        return <section key={category} className="res-section" aria-labelledby={`res-${category}-heading`}>
          <div className="res-category-heading"><h3 id={`res-${category}-heading`}>{category === 'flights' ? 'Round-trip flights' : 'Hotel'}</h3><span className="res-category-tag">{options.status === 'unavailable' ? 'Unavailable' : providerLabel(context)}</span></div>
          {options.status === 'unavailable' ? <div className="res-unavailable res-card"><p>No {context.data_mode !== 'validated_api' ? 'sample ' : ''}{kind} offer is available for these dates and travellers.</p><p className="res-small">Counted as missing in the budget, never as $0.00.</p></div>
            : selectedFirst<FlightOffer | HotelOffer>(options.offers, selectedId).map(offer => <OfferCard key={offer.id} offer={offer} kind={kind} selected={selectedId !== null && offer.id === selectedId} context={context} />)}
        </section>
      })}
    </div>
  </section>
}
