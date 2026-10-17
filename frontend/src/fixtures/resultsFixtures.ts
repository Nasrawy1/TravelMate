// Imported only by the DEV-gated preview. Never a production or generation fallback.
import manifestJson from '../../../docs/fixtures/manifest.json' with { type: 'json' }
import within from '../../../docs/fixtures/within-budget.json' with { type: 'json' }
import over from '../../../docs/fixtures/over-budget.json' with { type: 'json' }
import partial from '../../../docs/fixtures/partial-prices.json' with { type: 'json' }
import noPrices from '../../../docs/fixtures/no-prices.json' with { type: 'json' }
import minimum from '../../../docs/fixtures/known-minimum-over-budget.json' with { type: 'json' }
import taxes from '../../../docs/fixtures/unknown-taxes.json' with { type: 'json' }
import type { ResultsData, ResultsFixtureManifest, TripResult } from '../types/results'

export const RESULTS_FIXTURES = ['within-budget', 'over-budget', 'partial-prices', 'no-prices', 'unknown-taxes', 'known-minimum-over-budget'] as const
const responses: Record<string, unknown> = { 'within-budget': within, 'over-budget': over, 'partial-prices': partial, 'no-prices': noPrices, 'unknown-taxes': taxes, 'known-minimum-over-budget': minimum }

export function getResultsFixture(name: string): ResultsData | null {
  if (!Object.hasOwn(responses, name)) return null
  if (manifestJson.contract_version !== '0.4' || manifestJson.data_mode !== 'structural_mock' || manifestJson.live_evidence !== false) throw new Error('Invalid fixture provenance')
  // These local JSON files are verified by the repository's schema/semantic fixture validator.
  // This assertion is NOT an HTTP response validator and must never be used as one.
  const manifest = manifestJson as ResultsFixtureManifest
  const fixtureCase = manifest.cases.find(item => item.file === `${name}.json` && item.schema === 'response' && item.http_status === 200)
  if (!fixtureCase) throw new Error('Missing fixture manifest case')
  return { response: responses[name] as TripResult, context: { data_mode: manifest.data_mode, live_evidence: manifest.live_evidence, manifest, fixtureCase } }
}
