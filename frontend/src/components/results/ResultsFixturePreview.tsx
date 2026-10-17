import { RESULTS_FIXTURES, getResultsFixture } from '../../fixtures/resultsFixtures'
import type { ResultsData } from '../../types/results'

export default function ResultsFixturePreview({ selected, onPreview }: { selected: string; onPreview: (data: ResultsData | null) => void }) {
  return <details className="res-fixture-tools">
    <summary>Development only · Results fixture preview</summary>
    <label htmlFor="results-fixture">MOCK result scenario</label>
    <select id="results-fixture" value={selected} onChange={event => onPreview(getResultsFixture(event.target.value))}>
      <option value="">No result · empty state</option>
      {RESULTS_FIXTURES.map(name => <option key={name} value={name}>{name} · MOCK</option>)}
    </select>
    <p>Repository v0.4 structural fixtures only. Selecting a case does not generate a trip, verify provider coverage or call a service.</p>
  </details>
}
