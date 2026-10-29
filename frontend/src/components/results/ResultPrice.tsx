import type { ResultPrice as Price, ResultsContext } from '../../types/results'
import { priceDisplay } from '../../utils/results'

export default function ResultPrice({ price, context, activity = false }: { price: Pick<Price, 'amount_usd' | 'kind'>; context: ResultsContext; activity?: boolean }) {
  const display = priceDisplay(price, context, activity)
  return <span className={`res-price res-price-${display.style}`}>{display.label && <span className="res-price-tag">{display.label}</span>}<strong>{display.amount}</strong></span>
}
