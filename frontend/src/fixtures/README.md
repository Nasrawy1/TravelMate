# Development fixture adapters

The implemented FE-02 Results UI and generation inspector use these development-only adapters. Original shared JSON and manifest metadata remain in `../../../docs/fixtures/`; these adapters do not copy prototype prices or provide real API responses.

- `resultsFixtures.ts` loads all six success scenarios: within budget, over budget, partial prices, no prices, unknown taxes, and known minimum over budget. It preserves the manifest and selected case metadata for the Results preview at `/results`. Rendering always carries visible MOCK/sample labels, including provider-shaped prices. Direct navigation without a selected result shows an empty state.
- `generationMocks.ts` loads the five repository error fixtures with original bodies, HTTP statuses, headers, request IDs and manifest/case metadata. Missing unsupported-location/date, provider-unavailable and internal-error examples are separately marked `development_example`. Its pending preview does not report verified provider progress or produce a successful trip.

Structural fixtures retain `data_mode=structural_mock`, `live_evidence=false`, and their fixed validation-date context. They never prove current provider coverage, availability or live prices. Fixture type assertions rely on repository fixture validation; they are not a full runtime schema/semantic validator for untrusted HTTP responses.

Both adapters are reached through DEV-gated preview components. Their controls and fixture imports are excluded from production assets, as checked by the Results tests. They never silently replace failed online responses or bypass authentication.

Supabase Auth and the reusable FastAPI transport are implemented separately from these fixture adapters. Diyar reported real JWT probe testing against backend PR #23 commit `e4fe192`, with ES256 signing: Account A and Account B each received HTTP 200 with matching identity; a missing JWT received HTTP 401 UNAUTHORIZED. See the [frontend verification record](../../README.md#be-02-auth-and-jwt-verification). This evidence does not turn fixture prices into live data or connect fixtures to the backend.

The real generation-to-Results flow and full runtime generation-response validation remain pending. The final FE-03 offline demo is separate future work: 2–3 curated, read-only journeys with visible DEMO/MOCK labels and no hosted sign-in or backend/provider calls.
