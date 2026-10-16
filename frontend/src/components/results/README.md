# Results presentation boundary

`TripResults` accepts `ResultsData`: a v0.4 candidate `TripResult` plus explicit provenance. It composes `TravelOffers`, `DailyItinerary` and `BudgetExpenses`; `ResultPrice` consistently distinguishes provider/sample, estimate, unknown and explicit zero amounts. It uses the scoped Riviera tokens supplied by the Results page. The route supplies the permanent MOCK banner whenever fixture data is shown.

The development-only `ResultsFixturePreview` loads `src/fixtures/resultsFixtures.ts`. That adapter imports the original six response JSON files and manifest from `docs/fixtures/`, retaining the manifest and matching case object without modifying them. These files are checked with `docs/contracts/validate_fixtures.py`; TypeScript assertions in the development adapter are not runtime validation for HTTP responses. There is no automatic default fixture or production fallback.

Selected IDs, totals, status, missing categories, notes and warnings belong to the backend. Presentation only orders selected offers first and formats amounts/dates; it never chooses a cheapest offer, sums costs, calculates an overage or changes status. Machine-like fixture expense labels get readable names; custom backend labels are preserved. Timestamp displays explicitly use UTC. No fixture amount is labeled Live, even when payload fields say `kind=provider` or `status=live`.

Before real integration: approve v0.4, supply full schema/semantic response validation at the generation boundary, pass the validated response to this route, and construct trusted API provenance. Do not pass unchecked `fetch().json()` values or router state directly to these components. No authenticated route guard, transport, persistence or offline-demo implementation is included here.

Run from `frontend/`:

```sh
npm run typecheck
npm run build
node --experimental-strip-types --test tests/*.test.mjs
```

Results tests compile the actual TSX using existing Vite dependencies, render it with React's server renderer, and check all six cases plus production asset isolation. Temporary test modules go in ignored `node_modules/.cache/` and are removed after testing. No new package is needed.
