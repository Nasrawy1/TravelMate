import type { ResultPrice as Price, ResultsContext } from '../../types/results'
import { priceDisplay } from '../../utils/results'

export default function ResultPrice({ price, context }: { price: Pick<Price, 'amount_usd' | 'kind'>; context: ResultsContext }) {
  const display = priceDisplay(price, context)
  return <span className={`res-price res-price-${display.style}`}><span className="res-price-tag">{display.label}</span><strong>{display.amount}</strong></span>
}
