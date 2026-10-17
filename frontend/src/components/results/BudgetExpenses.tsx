import type { ResultsData } from '../../types/results'
import { budgetDisplay, CATEGORY_LABELS, CATEGORY_ORDER, expenseLabel } from '../../utils/results'
import ResultPrice from './ResultPrice'

export default function BudgetExpenses({ response, context }: ResultsData) {
  const { budget } = response
  const display = budgetDisplay(budget)
  const rows = [['Your budget', display.budget], [context.data_mode === 'structural_mock' ? 'Sample travel prices' : context.live_evidence ? 'Live travel prices' : 'Unverified travel prices', display.provider], ['Estimates', display.estimated], ['Projected total', display.total]]
  return <aside className="res-costs" aria-label="Budget and expenses">
    <section className="res-budget res-card" aria-labelledby="res-budget-heading">
      <div className="res-section-heading"><h2 id="res-budget-heading">Budget check</h2><span className={`res-budget-status res-status-${budget.status}`}>{display.status}</span></div>
      <p>{display.reason}</p>
      <dl>{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      {budget.missing_categories.length > 0 && <div className="res-missing"><strong>Missing:</strong>{budget.missing_categories.map(category => <span key={category}>{CATEGORY_LABELS[category]}</span>)}</div>}
      {budget.notes.map((note, index) => <p className="res-small" key={index}>{note}</p>)}
      <p className="res-small">An estimate, not a booking price. Totals and status are supplied by TravelMate; the browser does not calculate them.{context.data_mode === 'structural_mock' ? ' These are synthetic test values.' : ''}</p>
    </section>
    <section className="res-expenses res-card" aria-labelledby="res-expenses-heading">
      <h2 id="res-expenses-heading">Itemized expenses</h2>
      {CATEGORY_ORDER.map(category => {
        const items = budget.cost_items.filter(item => item.category === category)
        return items.length > 0 && <section className="res-expense-group" key={category} aria-labelledby={`res-expense-${category}`}>
          <h3 id={`res-expense-${category}`}>{CATEGORY_LABELS[category]}</h3>
          <ul>{items.map(item => <li key={item.id} data-expense-id={item.id}>
            <div className="res-expense-row"><h4>{expenseLabel(item, response)}</h4><ResultPrice price={item} context={context} /></div>
            <p className="res-small">{item.basis}</p>
          </li>)}</ul>
        </section>
      })}
    </section>
  </aside>
}
