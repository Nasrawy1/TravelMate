# Service boundary

## Implemented FE-02 generation lifecycle (v0.4 candidate)

`generation.ts` defines an injectable `GenerationService`, a single-flight `GenerationController`, safe error handling and idle/pending/success/error states. It contains no HTTP client or Auth initialization. **Check trip details** only prepares a local request; it does not generate a trip.

In `npm run dev`, prepare valid trip details, expand **Development only · MOCK generation previews**, select a scenario and choose **Inspect MOCK state**. Loading does not imply provider progress. The generation inspector uses repository error fixtures with their original manifest, HTTP status, headers, request IDs, `data_mode=structural_mock` and `live_evidence=false`. Missing 400/503/500 cases are separately labeled frontend-only examples. This inspector does not load successful trip fixtures or simulate successful generation.

The controller blocks duplicate submissions synchronously, aborts/ignores cancelled or stale operations, uses a 70-second transport allowance, honors both Retry-After seconds and HTTP dates, and never retries automatically. Cancel/Edit preserves current in-memory form values; navigating away/reloading does not persist them. Sign in does not simulate a session.

Server debug/error messages are never echoed; recognized codes/field names map to safe local copy. Malformed responses retain status-based Sign in (401) or Edit trip (400/422) guidance instead of offering retries. Malformed bodies cannot supply field errors or request references; only a safe, accessible `X-Request-ID` header can supply a reference. Valid envelopes require a matching body/header reference. Rate-limit cooldowns still apply to malformed 429 responses.

## Implemented fixture-driven Results UI

`/results` has reusable summary, itinerary, offer and expense components. Its development-only fixture selector renders all six repository success scenarios through `../fixtures/resultsFixtures.ts`, preserving manifest context and showing permanent MOCK/sample labeling. It displays backend-selected offers and supplied budget values without replacing totals or turning missing prices into zero. Direct navigation without a result shows an empty state.

The Results selector and generation inspector are separate development tools. Selecting a result fixture does not authenticate a user or complete a generation operation. Their controls and fixture adapters/imports are excluded from production assets by DEV gates and verified by the Results tests. They are neither production failure fallbacks nor the final FE-03 offline demo.

## Pending real integration

Supabase Authentication, bearer-token handling, the FastAPI HTTP adapter, a full runtime schema and semantic response validator, and the real generation-to-Results handoff/navigation are **not connected**. Existing Auth service boundaries do not create real sessions. The generation validator is mandatory for success; the generation development preview rejects every success response. Fixture type assertions are not HTTP response validation.

Diyar's frontend adapter/validation work must be coordinated with Adel's backend/Auth implementation and team approval of candidate v0.4. The backend must expose matching `X-Request-ID` and `Retry-After` headers through CORS.

- Use the agreed FastAPI `/api/v1` contract and snake_case wire fields; confirm v0.4 adoption before real integration.
- Keep future public backend configuration in `VITE_API_BASE_URL`. Add bearer tokens only through real Auth integration; keep provider credentials server-side.
- Preserve backend budget decisions and null/unknown amounts; never calculate replacement totals or select offers in the browser.
- Retain bounded timeouts, duplicate-submit protection, safe errors and explicit loading states when HTTP requests are introduced. Never automatically retry AI generation.
- Final FE-03 offline demo must use local fixtures without hosted sign-in or backend/provider calls; online services must not initialize on entering demo.

Run all frontend tests from `frontend/` with:

```sh
node --experimental-strip-types --test tests/*.test.mjs
```
