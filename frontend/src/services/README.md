# Service boundary

## Implemented FE-04 real generation boundary (adopted public v0.4)

The implemented flow is verified Supabase Login → Trip Planner → `realGenerationService` in `api.ts` → `tripGenerationApi.ts` → shared authenticated `apiClient.ts` → `POST /api/v1/trips/generate` → response validation → in-memory Results handoff/navigation. The six snake_case fields are `departure_city`, `destination_city`, `start_date`, `return_date`, `adults` and `budget_usd`. Explicit Generate Trip submission is real and can invoke backend AI/travel services; no request runs merely from importing a service or opening the form.

`generationValidation.ts` evaluates the keywords used by the adopted repository [v0.4 schema](../../../docs/contracts/api-v0.4.schema.json), checks dates, request/response consistency, offer/ledger references, tax and unknown-cost semantics, and rejects malformed HTTP 200 responses. It is not a general-purpose JSON Schema engine; tests check its supported schema vocabulary. It does not recalculate budget arithmetic, correct totals or select offers. Public response types are in `../types/results.ts`; unknown transport JSON is never treated as a successful trip by a type assertion alone.

`generation.ts` defines injectable mock/validated service boundaries, a single-flight `GenerationController`, safe errors and idle/pending/success/error states. The controller itself contains no HTTP client or Auth initialization. `TripPlannerPage` wires the real validated service; development previews remain separate.

### Cities and request validation

`../data/supportedCities/` derives 80 canonical labels, explicit aliases and country codes from Ziyad's adapter mapping at commit `3d3c79a8912de70b6892fed7d2d6d313ce7f4c3e`. The snapshot and normalization also match E2E backend commit `7987f73`. See its [provenance/update instructions](../data/supportedCities/README.md). Adapter-defined whitespace collapse/trim and lowercase matching resolve only canonical names or explicit aliases; submitted city strings are canonical. No separate frontend allowlist, country/provider-ID request fields, arbitrary qualifiers or invented aliases are introduced.

Local substring suggestions are not live lookup or proof of available offers. The form rejects blank/over-200-character values, unsupported or identical mapped cities, invalid/non-future UTC dates, stays outside 1–7 nights, non-integer adults outside 1–4 and non-finite/non-positive budgets. Backend validation remains authoritative. Unsupported locations, supported routes with no prices and provider failures are distinct outcomes.

### Loading, errors and identity transitions

In `npm run dev`, prepare valid trip details, expand **Development only · MOCK generation previews**, select a scenario and choose **Inspect MOCK state**. Loading does not imply provider progress. The generation inspector uses repository error fixtures with their original manifest, HTTP status, headers, request IDs, `data_mode=structural_mock` and `live_evidence=false`. Missing 400/503/500 cases are separately labeled frontend-only examples. This inspector does not load successful trip fixtures or simulate successful generation.

The controller blocks duplicate submissions synchronously, aborts/ignores cancelled or stale local operations, uses a 70-second transport allowance, honors both Retry-After seconds and HTTP dates, and never retries automatically. Pending UI is accessible; visual stages do not prove provider progress. Edit/Stop waiting preserves current in-memory form values; navigating away/reloading, including navigation to Login, does not persist them. Stopping local waiting, timing out or invalidating identity never guarantees backend cancellation; another deliberate submission may initiate another chargeable operation.

`watchGenerationIdentity` subscribes directly to verified session-state transitions. `TripPlannerPage` clears request ownership and invalidates the controller's unique operation token on account change, signout or definitive identity loss, even for batched A → B → A. Old success/error cannot navigate or overwrite newer state. Same-account re-verification alone is not an identity change. The guard never submits or retries. `generationIdentity.test.mjs` covers late completion, repeated attempts, identity loss, same-account verification and subscription cleanup.

Server debug/error messages are never echoed; recognized codes/field names map to safe local copy. Malformed responses retain status-based Sign in (401) or Edit trip (400/422) guidance instead of offering retries. Malformed bodies cannot supply field errors or request references; only a safe, accessible `X-Request-ID` header can supply a reference. Valid envelopes require a matching body/header reference. Rate-limit cooldowns still apply to malformed 429 responses.

Supported errors include 400 unsupported location/invalid dates, 422 field validation, 401 or expired/missing sessions, 429 rate limits, 502 AI generation failure, 503 provider unavailable, 504 generation timeout, 500 internal errors and network failures. Retry is deliberate; expiry of a Retry-After countdown never submits, and editing does not bypass the deadline. Backend CORS must expose `X-Request-ID` and `Retry-After`. API 401 does not replay generation or automatically sign out.

## Real Results handoff and separate fixture previews

`tripResultHandoff.ts` and `TripResultProvider` retain a structured clone of the validated public response only in memory for its verified account. Successful real generation navigates to `/results`; Back/Forward within Planner/Results retains the response without resubmitting. Refresh, leaving that route scope, signout or account changes clear it. No JWT/session object is stored with Results and no trip persistence is added. Direct access without a retained response shows an empty state, never an automatic fixture.

Shared Results components display itinerary, backend-selected offer IDs, sources, UTC retrieval timestamps, taxes, warnings, expense items, missing categories and backend-supplied budget totals/statuses. They preserve unavailable categories, null/unknown values and explicit zeros without recalculation or cheapest-offer selection. Taxes remain included/additional/unknown. A zero activity estimate may read Estimated free; a null amount is never free. Known-minimum-over-budget and uncertain/non-calculable totals remain as supplied.

Real responses carry `data_mode=validated_api`, `live_evidence=false`, and Retrieved price labels, not Live guarantees. Quotes describe the reported retrieval time, including older cached quotes; successful schema/transport checks do not independently prove freshness. A hotel quote may coexist with unavailable flights. The development-only Results selector separately renders six repository success scenarios through `../fixtures/resultsFixtures.ts`, preserving manifest context and permanent MOCK/Sample price labels. It is offered only when no real response is retained.

The Results selector and generation inspector are separate development tools. Selecting a result fixture does not authenticate a user or complete a generation operation. Their controls and fixture adapters/imports are excluded from production assets by DEV gates and verified by the Results tests. They are neither production failure fallbacks nor the final FE-03 offline demo.

## Verification evidence and remaining coordination

The [October 28, 2026 real E2E record](../../README.md#fe-04-authenticated-e2e-verification--october-28-2026) reports authenticated Istanbul → Rome generation for December 1–4, 2026, 2 adults and USD 1,500. Results rendered Booking hotel prices, sources, retrieval timestamps, itinerary and budget/unknown-cost handling. Flights returned unavailable; no retrieved flight prices or all-provider success is claimed. The exact cause is unconfirmed and belongs to Adel/Ziyad's backend/provider investigation. No frontend defect explaining unavailable flights has been established.

The lifecycle correction passed 335 mocked frontend tests (14 identity regressions), TypeScript, production build and whitespace checks in the preceding implementation step; this is separate from manual E2E evidence.

The [real unsupported-city rejection record](../../README.md#real-authenticated-unsupported-city-rejection--october-28-2026) closes the backend-400 evidence gap: on October 28, 2026, one separately authorized authenticated POST to the local BE-03 endpoint used Istanbul → Atlantis, December 1–4, 2026, 2 adults and USD 1,500. The sanitized UI showed HTTP 400, `UNSUPPORTED_LOCATION`, a recognized `destination_city` detail displayed as “Check your destination city.”, and matching header/body request references. Authentication used the shared client and existing session, without extracting or recording JWTs. No retry or valid-trip generation was performed.

Source at backend commit `7987f73` confirms city validation rejects the request before provider search and the endpoint returns before AI generation. This is **source-confirmed early rejection, not independently monitored/captured provider traffic**. The test made no direct provider calls. The temporary rejection control and its dedicated tests have been removed; the original development-only JWT/session probe is preserved and remains excluded from production. No new real request is required by reading or running the mocked tests below. Ali's DES-03 visual review remains pending; the unavailable-flight investigation belongs to Adel/Ziyad and is not a confirmed frontend defect.

Offline Demo uses separate bundled production samples outside Auth providers and never initializes these services. Figtree/Fraunces fonts and OFL licenses are bundled locally, with relative font-face paths; no external font host is needed. See the [frontend offline documentation](../../README.md#fe-03-production-offline-verification).

Run all frontend tests from `frontend/` with:

```sh
node --experimental-strip-types --test tests/*.test.mjs
```

## BE-02 Auth increment 1

`supabase.ts` lazily creates the one configured client with SDK-managed persistence/refresh and automatic SDK callback detection disabled (callbacks are handled explicitly). `authConfig.ts` accepts public project/application origins and publishable keys only. `authActions.ts` contains injectable Signup/Login adapters and maps provider codes to safe local errors. `auth.ts`/`signup.ts` are the existing page-facing boundaries. Signup uses Auth `display_name` metadata and `${VITE_APP_URL}/login` as the confirmation return URL; no database writes or duplicate Auth endpoints are added.

`authSession.ts` verifies restored/refreshed sessions with `getUser` before publishing only user ID and a filtered display name to React. It handles expiry, stale asynchronous responses, subscription cleanup and SDK browser-local logout. `AuthSessionProvider` wraps only online routes; direct demo access creates no client. Email confirmation/recovery use the shared client through `EmailAuthProvider`. Real trip generation uses the shared authenticated FastAPI transport. Confirmation-required UI never claims delivery or an authenticated session. See the frontend README for configuration and live-test limitations.

Verified sessions now drive Welcome planning links and shared account navigation. During session initialization, entry actions wait without redirecting; Login/Signup show a signed-in Riviera card only after verification. Metadata names are presentation-only, filtered as plain text, and never used for authorization. Email addresses are not included in UI session snapshots.

## BE-02 email links and recovery

`emailAuth.ts` is the injectable callback/recovery boundary. `emailAuthRuntime.ts` captures/scrubs callback URL parameters before Router mount and supplies one shared controller. New flows use PKCE with explicit `exchangeCodeForSession`; confirmation returns to `/login`, recovery to `/reset-password`. Legacy implicit confirmation remains compatible, but implicit recovery with generic OTP claims stays locked. `EmailAuthProvider` renders safe callback states and observes session invalidation. It stays outside the offline route. `passwordRecovery.ts` retains the public request/update boundary.

Recovery requires server-verified identity plus SDK-verified, recent recovery AMR and matching session claims; URL type and normal sign-in are insufficient. Authorization is memory-only, time-limited, checked again at update, and consumed after a real accepted update. StrictMode processing is deduplicated. Raw errors and URL credentials never enter UI snapshots. Refer to the frontend README for exact redirect prerequisites, the bounded authorization policy and manual email/password testing.

After the SDK update settles, its captured epoch/grant/deadline must still be valid before any local completion is published. Signout, account changes, expiry and navigation invalidate the operation. Late successes and failures are ignored without a retry or an assumption about the remote outcome. A valid successful update consumes recovery authorization and clears the callback notice while preserving the SDK session.

Recovery diagnosis: implicit email verification may issue OTP claims rather than recovery-specific AMR. PKCE requests/code exchange align the transport with the strict claim gate instead of broadening accepted authorization. Captured code/optional flow ID survive URL cleanup in memory and are explicitly passed to the SDK. Retest only with a new email after cooldown, in the same browser/origin that stored the verifier. No live credential-changing calls were used for diagnosis; the installed SDK is exercised through intercepted mock HTTP in tests.

## BE-02 FastAPI transport and verified JWT integration

`apiClient.ts` is an injectable JSON transport; `api.ts` supplies the existing lazy Supabase client and `VITE_API_BASE_URL`. Construction makes no requests and creates no Auth client. No routes or endpoints are registered by this code. Methods currently match the foundation's GET/POST CORS support.

Configure the API **origin**, without `/api/v1`, credentials, query or fragment. HTTPS is required except for loopback development. Request paths must be root-relative (including any `/api/v1` prefix). Protected calls are the default. They obtain `auth.getSession()` at request time and call SDK `refreshSession()` for sessions within 30 seconds of expiry. Missing, invalid, expired or unrefreshable sessions fail before HTTP. This is a transport freshness check; only Adel's backend can verify JWT signature, issuer, audience and authorization.

`{ auth: 'none' }` skips Auth and sends no Authorization header. Callers cannot supply headers, external URLs or fetch policy overrides. Requests omit cookies, reject redirects, disable caching and suppress referrers. The transport adds no token persistence or logging; existing SDK session storage remains SDK-managed. Importing or entering the offline-demo route still does not call this service.

`ApiError` exposes safe local copy, a stable code, optional HTTP status and an optional UUID `X-Request-ID` in default JSON mode. HTTP 401 is `UNAUTHORIZED` even with a missing/malformed error body. In endpoint mode, generation receives the HTTP status, untrusted parsed body and bounded/safe accessible `X-Request-ID`/`Retry-After` headers for its own error normalizer; it never renders raw response messages. Raw SDK/network errors are not exposed. There are no automatic API retries, Auth redirects or signouts. Callers can pass an AbortSignal; generation owns its timeout/lifecycle policy. Successful JSON stays `unknown` until `tripGenerationApi.ts` validates it with `generationValidation.ts`; the transport itself does not validate v0.4 responses.

Adel's [backend PR #23](https://github.com/Nasrawy1/TravelMate/pull/23), tested at commit `e4fe192`, supplies JWT verification and the locally gated `GET /api/v1/auth/probe`; this commit exposes `X-Request-ID` through CORS. Supabase signing is **ES256**. Diyar reported these real outcomes: Account A — HTTP 200, identity matches; Account B — HTTP 200, identity matches; missing JWT — HTTP 401 UNAUTHORIZED. This is sanitized manual integration evidence, separate from mocked test coverage.

The temporary `/dev/auth-probe` remains development-only and excluded from production. It displays only HTTP status and an identity-match result. It is separate from the real generation endpoint adapter, runtime validation and Results handoff described above. The earlier JWT probe verifies authentication only; the FE-04 E2E record documents real generation separately.
