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

The reusable FastAPI transport and request-time bearer-token boundary are implemented in `apiClient.ts`/`api.ts`. Only the temporary development-only `/dev/auth-probe` page calls the transport; product pages and generation remain unconnected. Endpoint adapters, a full runtime schema and semantic response validator, and the real generation-to-Results handoff/navigation are **not connected**. Signup/Login use the real Supabase SDK when configured; live verification still requires project configuration and test accounts. The generation validator is mandatory for success; the generation development preview rejects every success response. Fixture type assertions are not HTTP response validation.

Diyar's frontend adapter/validation work must be coordinated with Adel's backend/Auth implementation and team approval of candidate v0.4. The backend must expose matching `X-Request-ID` and `Retry-After` headers through CORS.

- Use the agreed FastAPI `/api/v1` contract and snake_case wire fields; confirm v0.4 adoption before real integration.
- Configure the trusted FastAPI origin through `VITE_API_BASE_URL`; use `api.ts` for future endpoint adapters. Keep provider credentials server-side.
- Preserve backend budget decisions and null/unknown amounts; never calculate replacement totals or select offers in the browser.
- Retain bounded timeouts, duplicate-submit protection, safe errors and explicit loading states when HTTP requests are introduced. Never automatically retry AI generation.
- Final FE-03 offline demo must use local fixtures without hosted sign-in or backend/provider calls; online services must not initialize on entering demo.

Run all frontend tests from `frontend/` with:

```sh
node --experimental-strip-types --test tests/*.test.mjs
```

## BE-02 Auth increment 1

`supabase.ts` lazily creates the one configured client with SDK-managed persistence/refresh and automatic SDK callback detection disabled (callbacks are handled explicitly). `authConfig.ts` accepts public project/application origins and publishable keys only. `authActions.ts` contains injectable Signup/Login adapters and maps provider codes to safe local errors. `auth.ts`/`signup.ts` are the existing page-facing boundaries. Signup uses Auth `display_name` metadata and `${VITE_APP_URL}/login` as the confirmation return URL; no database writes or duplicate Auth endpoints are added.

`authSession.ts` verifies restored/refreshed sessions with `getUser` before publishing only user ID and a filtered display name to React. It handles expiry, stale asynchronous responses, subscription cleanup and SDK browser-local logout. `AuthSessionProvider` wraps only online routes; direct demo access creates no client. Email confirmation/recovery use the shared client through `EmailAuthProvider`. The FastAPI transport is available but not wired to product flows. Confirmation-required UI never claims delivery or an authenticated session. See the frontend README for configuration and live-test limitations.

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

`ApiError` exposes safe local copy, a stable code, optional HTTP status and an optional UUID `X-Request-ID` from an accessible response header. HTTP 401 is `UNAUTHORIZED` even with a missing/malformed error body. Error bodies and raw SDK/network errors are not exposed. There are no automatic API retries, Auth redirects or signouts. Callers choose user-facing recovery actions and can pass an AbortSignal; generation retains its own timeout/lifecycle policy. Successful JSON remains `unknown` until an endpoint adapter validates it; this transport does not validate v0.4 generation responses.

Adel's [backend PR #23](https://github.com/Nasrawy1/TravelMate/pull/23), tested at commit `e4fe192`, supplies JWT verification and the locally gated `GET /api/v1/auth/probe`; this commit exposes `X-Request-ID` through CORS. Supabase signing is **ES256**. Diyar reported these real outcomes: Account A — HTTP 200, identity matches; Account B — HTTP 200, identity matches; missing JWT — HTTP 401 UNAUTHORIZED. This is sanitized manual integration evidence, separate from mocked test coverage.

The temporary `/dev/auth-probe` frontend remains available only in development and is excluded from production. It displays only HTTP status and an identity-match result. No permanent probe, generation call or backend code is introduced here. Real trip-generation endpoint integration, runtime generation-response validation and the Results handoff remain pending; future rate-limit handling also needs accessible `Retry-After` metadata from its agreed backend contract.
