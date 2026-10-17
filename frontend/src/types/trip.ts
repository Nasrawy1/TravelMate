/** Six-field request from the v0.4 candidate. No auth or UI metadata belongs here. */
export interface TripGenerateRequest {
  departure_city: string
  destination_city: string
  start_date: string
  return_date: string
  adults: number
  budget_usd: number
}
