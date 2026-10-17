import type { CostItem, ExpenseCategory, ResultBudget, ResultPrice, ResultsContext, TripResult } from '../types/results'

export const CATEGORY_LABELS: Record<ExpenseCategory, string> = {
  flights: 'Flights', accommodation: 'Hotel', taxes_fees: 'Taxes and fees',
  activities: 'Activities', food: 'Food', local_transport: 'Local transport',
}
export const CATEGORY_ORDER: ExpenseCategory[] = ['flights', 'accommodation', 'taxes_fees', 'activities', 'food', 'local_transport']
export const BUDGET_LABELS = { within_budget: 'Within budget', over_budget: 'Over budget', uncertain: 'Uncertain' }
const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

export function formatMoney(value: number | null): string {
  return value === null || !Number.isFinite(value) ? 'Unknown' : money.format(value)
}
export function providerLabel(context: ResultsContext): string {
  // Fixture mode always wins, even if an invalid caller supplied live_evidence=true.
  return context.data_mode === 'structural_mock' ? 'Sample price' : context.live_evidence === true ? 'Live' : 'Unverified price'
}
export function priceDisplay(price: Pick<ResultPrice, 'amount_usd' | 'kind'>, context: ResultsContext) {
  if (price.kind === 'unknown' || price.amount_usd === null || !Number.isFinite(price.amount_usd)) return { amount: 'Unknown', label: 'Unknown', style: 'unknown' }
  if (price.kind === 'estimate') return { amount: `${price.amount_usd === 0 ? '' : '~'}${formatMoney(price.amount_usd)}`, label: 'Estimate', style: 'estimate' }
  return { amount: formatMoney(price.amount_usd), label: providerLabel(context), style: 'provider' }
}
export function selectedFirst<T extends { id: string }>(offers: readonly T[], selectedId: string | null): T[] {
  // This only orders the backend's existing choice; it never chooses an offer or changes input.
  return [...offers].sort((a, b) => Number(b.id === selectedId) - Number(a.id === selectedId))
}
export function budgetDisplay(budget: ResultBudget) {
  // Formatting only. Do not derive totals, overage amounts, missing categories or status.
  return {
    budget: formatMoney(budget.budget_usd), provider: formatMoney(budget.provider_subtotal_usd),
    estimated: `~${formatMoney(budget.estimated_subtotal_usd)}`,
    total: budget.projected_total_usd === null ? 'Not calculable' : `~${formatMoney(budget.projected_total_usd)}`,
    status: BUDGET_LABELS[budget.status],
    reason: budget.status === 'within_budget' ? 'The supplied projected total fits your budget. Prices can still change.'
      : budget.status === 'uncertain' ? 'Some costs are unknown, so we can’t say whether this trip fits your budget.'
        : budget.projected_total_usd === null ? 'The supplied known travel prices already exceed your budget, before missing costs are added.'
          : 'The supplied projected total is over your budget.',
  }
}
export function formatDate(value: string, full = false): string {
  const date = new Date(`${value}T00:00:00Z`)
  if (!Number.isFinite(date.getTime())) return 'Unknown date'
  return new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', ...(full ? { weekday: 'long' as const } : {}), day: 'numeric', month: 'long', year: 'numeric' }).format(date)
}
export function formatTimestamp(value: string): string {
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return 'Unknown retrieval time'
  return `${new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', day: 'numeric', month: 'short', year: 'numeric' }).format(date)}, ${date.toISOString().slice(11, 16)} UTC`
}
export function expenseLabel(item: CostItem, response: TripResult): string {
  // Keep meaningful backend labels; translate only the fixture's machine-like labels.
  if (item.category === 'activities' && item.activity_ref && item.label.startsWith('activity-')) {
    const dayIndex = response.itinerary.findIndex(day => day.date === item.activity_ref?.date)
    const activity = response.itinerary[dayIndex]?.activities.find(activity => activity.order === item.activity_ref?.order)
    if (activity) return `${activity.name} · Day ${dayIndex + 1}`
  }
  const labels: Record<string, string> = { flight: 'Round-trip flights', hotel: 'Hotel stay', food: 'Food', transport: 'Local transport', 'hotel-tax': 'Hotel taxes and fees' }
  return Object.hasOwn(labels, item.label) ? labels[item.label] : item.label
}
export function warningTitle(code: string): string {
  const titles: Record<string, string> = { FLIGHTS_UNAVAILABLE: 'Flights unavailable.', HOTELS_UNAVAILABLE: 'Hotels unavailable.', TRAVEL_RATE_LIMITED: 'Travel prices busy.', TRAVEL_TIMEOUT: 'Travel prices timed out.', CURRENCY_UNAVAILABLE: 'Currency not supported.', TAXES_UNKNOWN: 'Taxes unknown.', BUDGET_INCOMPLETE: 'Budget incomplete.' }
  return Object.hasOwn(titles, code) ? titles[code] : 'Note.'
}
