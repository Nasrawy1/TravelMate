import schema from '../../../docs/contracts/api-v0.4.schema.json' with { type: 'json' }
import type { TripResult } from '../types/results'
import type { TripGenerateRequest } from '../types/trip'

type Shape = { type?: string; enum?: unknown[]; anyOf?: Shape[]; properties?: Record<string, Shape>; required?: string[]; additionalProperties?: boolean; items?: Shape; uniqueItems?: boolean; minimum?: number; maximum?: number; exclusiveMinimum?: number; minLength?: number; maxLength?: number; pattern?: string; format?: string }
export function calendarDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value
}
/** Evaluates the keywords used by the adopted schema, without coercion or mutation.
 * Not a general-purpose JSON Schema engine. Schema keyword coverage is regression-tested. */
function matches(value: unknown, shape: Shape): boolean {
  if (shape.anyOf) return shape.anyOf.some(s => matches(value, s))
  if (shape.enum && !shape.enum.includes(value)) return false
  switch (shape.type) {
    case 'null': return value === null
    case 'object': {
      if (!value || typeof value !== 'object' || Array.isArray(value)) return false
      const object = value as Record<string, unknown>
      return (shape.required ?? []).every(k => Object.hasOwn(object, k))
        && Object.entries(object).every(([k, v]) => shape.properties?.[k] ? matches(v, shape.properties[k]) : shape.additionalProperties !== false)
    }
    case 'array': return Array.isArray(value) && value.every(v => !shape.items || matches(v, shape.items))
      && (!shape.uniqueItems || new Set(value.map(v => JSON.stringify(v))).size === value.length)
    case 'integer': case 'number': return typeof value === 'number' && Number.isFinite(value)
      && (shape.type !== 'integer' || Number.isInteger(value))
      && (shape.minimum === undefined || value >= shape.minimum) && (shape.maximum === undefined || value <= shape.maximum)
      && (shape.exclusiveMinimum === undefined || value > shape.exclusiveMinimum)
    case 'string': {
      if (typeof value !== 'string') return false
      const length = [...value].length
      if (shape.minLength !== undefined && length < shape.minLength || shape.maxLength !== undefined && length > shape.maxLength) return false
      if (shape.pattern && !new RegExp(shape.pattern, 'u').test(value)) return false
      if (shape.format === 'date') return calendarDate(value)
      if (shape.format === 'date-time') return /^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?Z$/.test(value) && calendarDate(value.slice(0, 10))
      return true
    }
    default: return shape.enum !== undefined
  }
}
export function validGenerationRequest(value: unknown, today = new Date().toISOString().slice(0, 10)): value is TripGenerateRequest {
  if (!matches(value, schema.$defs.request)) return false
  const r = value as TripGenerateRequest
  const nights = (Date.parse(r.return_date) - Date.parse(r.start_date)) / 86400000
  return r.departure_city === r.departure_city.trim() && r.destination_city === r.destination_city.trim()
    && r.departure_city.toLowerCase() !== r.destination_city.toLowerCase() && r.start_date > today && nights >= 1 && nights <= 7
}
/** Mirrors the public request schema's Decimal(str(value)).quantize(0.01):
 * half-even, positive after rounding, at most 28 coefficient digits.
 * Decimal digits/BigInt avoid binary multiplication errors and support exponents. */
function normalizedRequestBudget(value: number): number | null {
  if (!Number.isFinite(value) || value <= 0) return null
  const [mantissa, exponent = '0'] = String(value).toLowerCase().split('e')
  const [whole, fraction = ''] = mantissa.split('.')
  const coefficient = BigInt(whole + fraction)
  const shift = Number(exponent) - fraction.length + 2
  let cents: bigint
  if (shift >= 0) cents = coefficient * 10n ** BigInt(shift)
  else {
    const divisor = 10n ** BigInt(-shift)
    cents = coefficient / divisor
    const twiceRemainder = (coefficient % divisor) * 2n
    if (twiceRemainder > divisor || twiceRemainder === divisor && cents % 2n !== 0n) cents += 1n
  }
  if (cents === 0n || cents.toString().length > 28) return null
  return Number(`${cents}e-2`)
}
/** Validates public structure and referential semantics. Backend owns arithmetic,
 * cheapest-offer selection, city mapping and provider provenance; never recompute those here. */
export function validateGenerationResponse(value: unknown, request: TripGenerateRequest): TripResult | null {
  if (!matches(value, schema.$defs.response)) return null
  const r = value as TripResult
  const { trip, budget } = r
  if (trip.departure_city !== request.departure_city.trim() || trip.destination_city !== request.destination_city.trim()
    || trip.start_date !== request.start_date || trip.return_date !== request.return_date || trip.adults !== request.adults || budget.budget_usd !== normalizedRequestBudget(request.budget_usd)) return null
  const nights = (Date.parse(trip.return_date) - Date.parse(trip.start_date)) / 86400000
  if (nights !== trip.nights || r.itinerary.length !== nights + 1) return null
  const activities = new Map<string, typeof r.itinerary[number]['activities'][number]['cost']>()
  for (const [index, day] of r.itinerary.entries()) {
    if (day.date !== new Date(Date.parse(trip.start_date) + index * 86400000).toISOString().slice(0, 10)) return null
    if (day.activities.length ? day.empty_day_reason !== null : ![0, nights].includes(index) || !day.empty_day_reason?.trim()) return null
    for (const [i, activity] of day.activities.entries()) {
      const cost = activity.cost
      if (activity.order !== i + 1 || (cost.kind === 'unknown' ? cost.amount_usd !== null || cost.coverage !== null : cost.kind !== 'estimate' || cost.amount_usd === null || cost.coverage !== 'all_travelers')) return null
      activities.set(`${day.date}/${activity.order}`, cost)
    }
  }
  const offers = [...r.travel_options.flights.offers, ...r.travel_options.hotels.offers]
  if (new Set(offers.map(o => o.id)).size !== offers.length || r.live_integration_status !== (offers.length ? 'price_received' : 'no_price')) return null
  for (const group of Object.values(r.travel_options)) if (group.status !== (group.offers.length ? 'live' : 'unavailable')) return null
  for (const o of offers) {
    if (o.price.kind !== 'provider' || o.price.amount_usd === null || o.price.coverage !== 'entire_trip_all_travelers') return null
    const t = o.taxes
    if (t.status === 'included' ? t.additional_amount_usd !== 0 : t.status === 'unknown' ? t.additional_amount_usd !== null : t.additional_amount_usd === null || t.additional_amount_usd <= 0) return null
  }
  if (r.travel_options.flights.offers.some(o => o.adults !== trip.adults)
    || r.travel_options.hotels.offers.some(o => o.occupancy_adults !== trip.adults || o.check_in !== trip.start_date || o.check_out !== trip.return_date)) return null
  const selected = {
    flights: r.travel_options.flights.offers.find(o => o.id === budget.selected_flight_offer_id),
    accommodation: r.travel_options.hotels.offers.find(o => o.id === budget.selected_hotel_offer_id),
  }
  if (r.travel_options.flights.offers.length ? !selected.flights : budget.selected_flight_offer_id !== null) return null
  if (r.travel_options.hotels.offers.length ? !selected.accommodation : budget.selected_hotel_offer_id !== null) return null
  const items = budget.cost_items
  if (new Set(items.map(i => i.id)).size !== items.length) return null
  for (const category of ['flights', 'accommodation', 'food', 'local_transport']) if (items.filter(i => i.category === category).length !== 1) return null
  const refs = new Set<string>()
  for (const i of items) {
    if ((i.amount_usd === null) !== (i.kind === 'unknown')) return null
    if (i.category === 'activities') {
      const key = `${i.activity_ref?.date}/${i.activity_ref?.order}`
      const cost = activities.get(key)
      if (!cost || refs.has(key) || cost.kind !== i.kind || cost.amount_usd !== i.amount_usd) return null
      refs.add(key)
    } else if (i.activity_ref !== null) return null
    if (i.category === 'flights' || i.category === 'accommodation') {
      const offer = selected[i.category]
      if (i.source_offer_id !== (offer?.id ?? null) || i.amount_usd !== (offer?.price.amount_usd ?? null) || i.kind !== (offer ? 'provider' : 'unknown')) return null
    } else if (i.category === 'taxes_fees') {
      if (!Object.values(selected).some(o => o && o.id === i.source_offer_id)) return null
    } else if (i.source_offer_id !== null || i.kind === 'provider') return null
  }
  if (refs.size !== activities.size) return null
  for (const offer of Object.values(selected)) {
    if (!offer) continue
    const taxes = items.filter(i => i.category === 'taxes_fees' && i.source_offer_id === offer.id)
    if (taxes.length !== (offer.taxes.status === 'included' ? 0 : 1)) return null
    if (taxes.some(i => i.amount_usd !== offer.taxes.additional_amount_usd || i.kind !== (offer.taxes.status === 'unknown' ? 'unknown' : 'provider'))) return null
  }
  const missing = new Set(items.filter(i => i.kind === 'unknown').map(i => i.category))
  if (budget.missing_categories.length !== missing.size || budget.missing_categories.some(c => !missing.has(c))
    || (budget.projected_total_usd === null) !== (missing.size > 0)
    || budget.status === 'within_budget' && missing.size > 0 || budget.status === 'uncertain' && missing.size === 0) return null
  return r
}
