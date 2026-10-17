import type { TripGenerateRequest } from '../types/trip'

// Testing choices only. This list does not establish live provider coverage.
export const MOCK_CITIES = ['Istanbul', 'Rome', 'Paris', 'London', 'Barcelona', 'Dubai'] as const

export interface TripFormValues {
  departure_city: string
  destination_city: string
  start_date: string
  return_date: string
  adults: number
  budget_usd: string
}

export type TripField = keyof TripFormValues
export type TripFormErrors = Partial<Record<TripField, string>>

const DAY_MS = 86_400_000

export function utcToday(now = new Date()): string {
  return now.toISOString().slice(0, 10)
}

// Round-trip the calendar date: Date.parse alone normalizes dates such as Feb 30.
function calendarTime(value: string): number | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null
  const time = Date.parse(`${value}T00:00:00Z`)
  return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value ? time : null
}

export function validateTripForm(values: TripFormValues, today = utcToday()) {
  const errors: TripFormErrors = {}
  if (!values.departure_city) errors.departure_city = 'Choose where you leave from.'
  else if (!MOCK_CITIES.some(city => city === values.departure_city)) errors.departure_city = 'Choose a MOCK testing city from the list.'
  if (!values.destination_city) errors.destination_city = 'Choose your destination.'
  else if (!MOCK_CITIES.some(city => city === values.destination_city)) errors.destination_city = 'Choose a MOCK testing city from the list.'
  else if (values.destination_city === values.departure_city) errors.destination_city = 'Pick a different city from your departure.'

  const start = calendarTime(values.start_date)
  const end = calendarTime(values.return_date)
  const nights = start !== null && end !== null ? (end - start) / DAY_MS : null
  if (!values.start_date) errors.start_date = 'Choose a start date.'
  else if (start === null) errors.start_date = 'Enter a valid calendar date.'
  else if (values.start_date <= today) errors.start_date = 'Start date must be in the future (after today in UTC).'
  if (!values.return_date) errors.return_date = 'Choose a return date.'
  else if (end === null) errors.return_date = 'Enter a valid calendar date.'
  else if (values.return_date <= today) errors.return_date = 'Return date must be in the future (after today in UTC).'
  else if (nights !== null && nights < 1) errors.return_date = 'Return date must be after the start date.'
  else if (nights !== null && nights > 7) errors.return_date = 'Trips can be up to 7 nights.'

  if (!Number.isInteger(values.adults) || values.adults < 1 || values.adults > 4) errors.adults = 'Choose between 1 and 4 adults (a whole number).'
  const budget = Number(values.budget_usd)
  if (!values.budget_usd.trim()) errors.budget_usd = 'Enter your total budget.'
  else if (!Number.isFinite(budget)) errors.budget_usd = 'Enter a finite budget in USD.'
  else if (budget <= 0) errors.budget_usd = 'Budget must be more than $0.00.'
  return { errors, nights }
}

export function prepareTripRequest(values: TripFormValues, today = utcToday()): TripGenerateRequest | null {
  if (Object.keys(validateTripForm(values, today).errors).length) return null
  // Explicitly whitelist the candidate contract fields; never spread form/UI state.
  return {
    departure_city: values.departure_city,
    destination_city: values.destination_city,
    start_date: values.start_date,
    return_date: values.return_date,
    adults: values.adults,
    budget_usd: Number(values.budget_usd),
  }
}
