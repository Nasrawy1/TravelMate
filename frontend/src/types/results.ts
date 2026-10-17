import type { TripGenerateRequest } from './trip'

/** API v0.4 candidate view types. Runtime schema/semantic validation is required for future HTTP data. */
export type PriceKind = 'provider' | 'estimate' | 'unknown'
export type ExpenseCategory = 'flights' | 'accommodation' | 'taxes_fees' | 'activities' | 'food' | 'local_transport'
export interface ResultPrice {
  amount_usd: number | null
  kind: PriceKind
  coverage: 'entire_trip_all_travelers' | 'all_travelers' | null
}
export interface OfferTaxes {
  status: 'included' | 'additional_known' | 'unknown'
  additional_amount_usd: number | null
}
interface OfferBase { id: string; source: string; retrieved_at: string; price: ResultPrice; taxes: OfferTaxes }
export interface FlightOffer extends OfferBase {
  airline: string
  departure_airport_code: string
  arrival_airport_code: string
  outbound_departure_at: string
  return_departure_at: string
  adults: number
}
export interface HotelOffer extends OfferBase {
  name: string
  area: string | null
  check_in: string
  check_out: string
  occupancy_adults: number
  room_qty: number | null
}
export interface ItineraryDay {
  date: string
  empty_day_reason: string | null
  activities: { order: number; name: string; area: string; description: string; cost: ResultPrice }[]
}
export interface CostItem {
  id: string
  category: ExpenseCategory
  label: string
  amount_usd: number | null
  kind: PriceKind
  coverage: 'entire_trip_all_travelers'
  basis: string
  source_offer_id: string | null
  activity_ref: { date: string; order: number } | null
}
export interface ResultBudget {
  budget_usd: number
  selected_flight_offer_id: string | null
  selected_hotel_offer_id: string | null
  cost_items: CostItem[]
  provider_subtotal_usd: number
  estimated_subtotal_usd: number
  projected_total_usd: number | null
  status: 'within_budget' | 'over_budget' | 'uncertain'
  missing_categories: ExpenseCategory[]
  notes: string[]
}
export interface TripResult {
  generation_status: 'complete'
  live_integration_status: 'price_received' | 'no_price'
  trip: Omit<TripGenerateRequest, 'budget_usd'> & { nights: number }
  itinerary: ItineraryDay[]
  travel_options: {
    flights: { status: 'live' | 'unavailable'; offers: FlightOffer[] }
    hotels: { status: 'live' | 'unavailable'; offers: HotelOffer[] }
  }
  budget: ResultBudget
  warnings: { code: string; message: string }[]
}
export interface ResultsFixtureCase {
  file: string
  schema: string
  http_status: number | null
  request?: TripGenerateRequest
  headers?: Record<string, string>
}
export interface ResultsFixtureManifest {
  contract_version: '0.4'
  data_mode: 'structural_mock'
  live_evidence: false
  validation_today_utc: string
  cases: ResultsFixtureCase[]
}
export type ResultsContext = {
  data_mode: 'structural_mock'
  live_evidence: false
  manifest: ResultsFixtureManifest
  fixtureCase: ResultsFixtureCase
} | {
  data_mode: 'validated_api'
  live_evidence: boolean
}
export interface ResultsData { response: TripResult; context: ResultsContext }
