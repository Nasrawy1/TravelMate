# TravelMate frontend — Auth, real trip generation and Offline Demo

React + Vite + TypeScript frontend owned by Diyar. The Welcome and authentication UI follow [Ali’s original Riviera design archive](../docs/design/travelmate-des01-welcome-auth.zip), stored at `docs/design/travelmate-des01-welcome-auth.zip` from the repository root. The unchanged ZIP contains `design/welcome-auth.md` and the original Welcome/authentication HTML sources under `travelmate-des01-welcome-auth/`. Supabase Auth and authenticated FastAPI trip generation are implemented; real operation requires local configuration and the backend. The adopted public [API contract v0.4](../docs/api-contracts.md) defines the integration.

## Implemented UI and current limits

- **Welcome:** Riviera landing sections, sample postcards, price-label explanations, and links to Signup, Login and the demo entry. Hard-coded prices are marked Sample/Example; they are not live provider data.
- **Login:** email/password fields, password visibility, required/email validation, accessible errors, pending-state controls and navigation to Signup, Forgot Password, Home and Demo.
- **Signup:** display name, email, password and confirmation; a live password-rule checklist; shared password visibility; validation, accessible errors and pending-state controls. Name is a display name, not trip traveler data.
- **Forgot Password:** email validation and a reset-link request form in the centered Riviera layout.
- **Reset Password:** new-password/confirmation validation and password visibility in the same layout.

Signup and Login call the shared Supabase client when configured. Signup sends `display_name` as Auth user metadata and shows account-neutral confirmation instructions when no session is returned; it does not prove email delivery or a new account. Login uses password authentication. Restored and refreshed sessions remain unverified in the UI until `getUser` confirms identity; expired or unverifiable sessions never show as signed in. Auth pages show the verified session, a Trip Planner link, and browser-local logout. No automatic generation or successful trip is implied. Forgot/Reset Password now use Supabase. Email confirmation callbacks are handled explicitly; automatic SDK URL detection stays disabled so callback errors cannot silently fall back to an existing session. See the recovery verification section below. The current UI password rule is 8+ characters, including a letter and a number; it must be aligned with Adel’s configured Supabase policy before integration.

**Trip Planner** submits the six-field v0.4 request through the authenticated FastAPI client after city, UTC date, night-count, adult-count and budget validation. The Generate Trip action is real; it can invoke backend AI/travel services. Separately, development-only MOCK generation controls inspect loading/error states without contacting them. Repository fixtures retain their original metadata; missing error cases are labeled frontend examples. These preview controls/fixtures are excluded from production. See [the generation service boundary](src/services/README.md).

**Results** renders the validated real response retained from Trip Planner: trip summary, backend-selected offers, daily itinerary, warnings, budget and itemized expenses. Direct navigation or refresh without retained data shows an honest empty state. Real offers say **Retrieved price**, with source and retrieval timestamp; availability and final prices are not guaranteed. In development only, a separate Results fixture preview offers six structural cases when no real response is retained. Fixtures always show a permanent MOCK banner and **Sample price**, never Live. Fixture imports/controls are excluded from production and never replace a failed real request.

**Offline Demo** at `/offline-demo` displays three bundled read-only journeys using shared Results components: Rome (within budget), Paris (over budget) and Barcelona (uncertain with missing hotel/tax costs). Native trip buttons support keyboard selection, `?trip=rome|paris|barcelona` supports direct links and browser history, and a permanent DEMO ribbon explains that prices are samples. Offers say **Demo price**, sources/timestamps are explicitly sample metadata, and unknown costs remain unknown. No signup, generation or saving is involved. The route stays outside Auth providers and makes no Supabase, FastAPI, AI or provider calls. See the [offline sample-data documentation](src/data/offlineDemo/README.md) and the separate manual evidence below. Public v0.4 adoption is recorded under PLAN-02 in the API contract; adoption does not imply every integration acceptance test has passed.

## Prerequisites

Use Node.js 22.12 or newer and npm. Development checks were run with Node.js 24.15.0 and npm 11.12.1; the declared minimum version has not been separately tested. Exact dependencies are in `package.json` and `package-lock.json`.

Initial dependency installation requires access to the npm registry unless all required packages are cached. No backend or environment file is needed to view the UI. Real Auth requires the development Supabase configuration and internet access.

## Install and start

From the repository root (PowerShell, macOS or Linux shell):

```sh
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Stop with Ctrl+C. Port 5173 must be free; the command fails instead of silently choosing another port.

If localhost resolution prevents access, bind explicitly to the loopback address:

```sh
npm run dev -- --host 127.0.0.1 --port 5173
```

Then open http://127.0.0.1:5173. Keep the terminal/process running during preview. If the port is occupied, stop the server you own or select a free port:

```sh
npm run dev -- --host 127.0.0.1 --port 5174
```

Use the actual Local URL printed by Vite. These are frontend-only commands; they do not start FastAPI. A combined application launcher is not implemented.

## Environment configuration

For real Signup/Login, copy `.env.example` locally to `.env.local` and supply `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY`. Use `VITE_APP_URL=http://localhost:5173` (Adel's configured Site URL). Restart Vite after changing environment values. Examples contain placeholders only; no actual project values are committed. Missing/invalid configuration shows an honest unavailable state without Auth requests. Only `sb_publishable_...` browser keys are accepted; elevated or legacy JWT-shaped keys are rejected.

For local FastAPI testing, set `VITE_API_BASE_URL` locally to Adel's confirmed origin only, such as `http://127.0.0.1:8000`; do not append `/api/v1`. The example file retains a placeholder. Missing or unsafe configuration fails closed. Configuration/import alone sends no request; explicit Generate Trip submission uses the configured backend. Backend provider secrets stay server-side. No local environment file is changed by these instructions.

The shared `api` in `src/services/api.ts` takes root-relative paths. Its default is protected access: each request obtains the current SDK session and refreshes a nearly expired token before attaching its bearer header. Public endpoints require `{ auth: 'none' }`; the foundation's existing `/api/v1/health` is public. The client rejects external destinations and redirects and never retries API operations or signs out automatically. Generation maps HTTP 401 or session expiry to a user-controlled sign-in action; form values remain only while the planner is mounted. Success bodies remain `unknown` until endpoint-specific runtime validation. See [service documentation](src/services/README.md#be-02-fastapi-transport-and-verified-jwt-integration) for policies and dependencies.

Temporary BE-02 testing: in `npm run dev`, open `/dev/auth-probe` in the same browser/profile where you signed in and choose **Run JWT probe**. It calls PR #23's locally enabled `GET /api/v1/auth/probe` through the shared client, without accessing storage or exposing credentials. Only HTTP status and an identity-match result are shown; no response body, user ID or request ID is rendered. No request runs on page load, and account changes/navigation clear the result and cancel pending work. A **No response** status means no HTTP result was available; check local API configuration, session availability and server connectivity. The backend must have `ENABLE_AUTH_PROBE=true`. No backend/probe is started automatically. This route and its module are excluded from production builds and remain available for development follow-up until explicitly removed.

Use one origin consistently: the default command serves localhost; the loopback override serves 127.0.0.1. Set `VITE_APP_URL` to the chosen allowed origin and ensure `${VITE_APP_URL}/login` is allowed in Supabase. Browser storage differs between these origins. Preview on port 4173 requires its own allowed origin if Auth is tested there.

The shared client uses SDK-managed persistence and refresh. It is created lazily by online routes; direct `/offline-demo` and unknown routes do not initialize Supabase. Leaving the online route boundary stops its Auth subscriptions/refresh. No custom token storage, logging or application tables are introduced. Logout uses `scope: 'local'` and does not claim to revoke already issued access tokens everywhere.

All `VITE_*` values are public browser configuration. Never add provider API secrets, access tokens, passwords or service-role keys. Local environment files, dependency folders and generated output are ignored; `.env.example` remains includable. Ignore rules do not protect a secret already committed to Git, so review the delivery diff before staging.

## Checks and production preview

From `frontend/`:

```sh
npm run typecheck
npm run build
npm run preview
```

Build runs strict TypeScript checking and writes production assets to `dist/`. Preview serves them at http://localhost:4173 (port must be free). It requires a successful build first. For a fresh checkout, always run `npm ci` before these commands.

Preview also supports explicit loopback/port overrides:

```sh
npm run preview -- --host 127.0.0.1 --port 4174
```

Open the URL printed by Vite (http://127.0.0.1:4174 for this example). Stop with Ctrl+C. Preview is for inspecting a local production build, not a production deployment. Do not commit `dist/` or `node_modules/`. No npm test or lint script is configured. Run the planner/lifecycle tests directly with `node --experimental-strip-types --test tests/*.test.mjs` from `frontend/`. These checks do not prove Auth or backend integration.

Verification on 2026-10-15 (Windows, Node.js 24.15.0, npm 11.12.1): a clean `npm ci` succeeded in a temporary directory containing copies of the manifest and lockfile; `npm run typecheck` and `npm run build` passed in the working frontend. Development and preview startup also passed with the documented overrides on ports 5174 and 4174. This is same-machine evidence, not a second-computer handover test.

## Routes

| Path | Current behavior |
| --- | --- |
| `/` | Implemented Riviera Welcome / landing UI |
| `/login` | Password login, verified session state and browser-local logout; requires configuration |
| `/signup` | Supabase signup with display metadata and confirmation-required UI; requires configuration |
| `/forgot-password` | Supabase reset request with account-neutral acknowledgement; delivery requires manual verification |
| `/reset-password` | Password update gated by a verified, recent recovery callback/session |
| `/auth/callback` | Optional confirmation callback/error UI; new-path use requires redirect allowlisting |
| `/trip-planner` | Supported-city form and authenticated real generation; separate development-only MOCK lifecycle/error inspector |
| `/results` | Retained validated real result, otherwise empty state; separate development-only structural fixture previews |
| `/offline-demo` | Three read-only sample trips; permanent DEMO label; no Auth/backend |
| Any other path | Riviera Not Found page with Home and session-aware planning navigation |

Page routes are accessible without a route-level login redirect; real generation requires a current SDK session and backend JWT authorization. The UI is not the backend security boundary. Opening `/reset-password` is not authorization to update credentials; a fresh verified recovery callback/session is required. Recovery acknowledgement does not prove email delivery, and password-update success requires a confirmed SDK response.

BrowserRouter supports client navigation and direct links through Vite. A future static host must serve `index.html` for application routes.

## Main files and folders

- `src/main.tsx`: React entry point, BrowserRouter and global CSS.
- `src/App.tsx`: route definitions.
- `src/pages/`: Welcome/auth/recovery, Trip Planner, Results and Offline Demo UI.
- `src/components/welcome/`: shared Riviera logo, price badges and illustrative postcards.
- `src/components/auth/`: reusable password input and recovery layout/error/submit components.
- `src/components/results/`: shared v0.4 presentation components, account-bound in-memory Results provider and a separate development-only fixture selector.
- `src/components/trip/CityCombobox.tsx`: accessible local supported-city search and keyboard selection.
- `src/data/supportedCities/`: adapter-derived 80-city snapshot, normalization and update provenance.
- `src/components/layout/AppLayout.tsx`: shared layout for placeholder content.
- `src/components/PlaceholderPage.tsx`: reusable page content wrapper.
- `src/styles/`: global defaults, shared Riviera/Login styling and scoped Signup/recovery additions.
- `src/services/`: Supabase Auth/recovery, request-time JWT transport, validated real generation, lifecycle/identity invalidation and in-memory Results handoff. Credentials/tokens are never logged; Auth session persistence is SDK-managed.
- `src/types/`: shared v0.4 request/Results interfaces; `generationValidation.ts` supplies runtime validation because types alone do not validate HTTP responses.
- `src/assets/fonts/`: bundled Figtree/Fraunces WOFF2 files and their OFL licenses; `src/styles/fonts.css` declares local font faces.
- `src/fixtures/generationMocks.ts`: development-only error fixture/example adapter; not offline demo data.
- `src/fixtures/resultsFixtures.ts`: development-only imports of the six original `docs/fixtures/` responses and manifest; not copied prototype data or a production fallback.
- `vite.config.ts`, `tsconfig.json`: Vite React plugin and strict TypeScript configuration.

## Integration and offline boundaries

Scope follows the repository’s MVP scope and architecture: one destination, 1–4 adults, 1–7 nights, whole-trip USD budget, backend-owned budget calculations, and a separate read-only demo. The planner validates these form constraints locally against the adopted public v0.4 baseline. Saved trips, booking and payments are outside this flow.

The implemented online flow is Login → Trip Planner → authenticated `POST /api/v1/trips/generate` → runtime response validation → account-bound in-memory handoff → `/results`. The response boundary checks the adopted schema structure and referential semantics before success. It does not choose offers or recompute budget arithmetic. The real Results context is `validated_api` with `live_evidence=false`: successful transport/schema validation does not independently verify provider freshness. Fixture selection never completes a pending real generation or establishes a session. Refreshing or leaving the Planner/Results route scope clears the retained trip; Back/Forward within that scope does not resubmit generation. No trip results or JWTs are added to localStorage by the handoff.

Figtree body text (400/500/700) and Fraunces headings (600 normal/italic and 800 normal) use bundled WOFF2 files with relative asset paths and `font-display: swap`. Fallback stacks remain available. Their OFL licenses are included beside the files. There is no runtime Google Fonts/CDN dependency. Demo illustrations are inline SVG; JavaScript, CSS, fonts and all three sample journeys are served locally. Production asset tests check local references and demo inclusion. Diyar additionally reported a hard reload and all three journeys working with Wi-Fi disconnected after the local-font build, with fonts visible and the preview server running. This is manual evidence, not an automated network-disconnection test; second-computer handover remains unverified.

### Supported cities and validation

Local suggestions are derived from Ziyad's authoritative adapter `SUPPORTED_CITIES` mapping, not an independently maintained frontend allowlist. The snapshot records source commit `3d3c79a8912de70b6892fed7d2d6d313ce7f4c3e`; its 80 records and normalization were also checked against the E2E backend commit `7987f73`. See [snapshot provenance and update instructions](src/data/supportedCities/README.md). Trim/collapse adapter-defined whitespace, lowercase for matching, and resolve only canonical labels or explicit aliases; submit canonical `departure_city`/`destination_city` names. Country codes come from the mapping. Partial search matches are suggestions, not valid submitted locations; arbitrary qualifiers, accent folding and unsupported aliases are not invented.

The form rejects blank/over-200-character city input, unsupported or identical mapped cities, invalid calendar dates, dates not strictly after today's UTC date, stays outside 1–7 nights, non-integer adults outside 1–4, and non-finite/non-positive budgets. Local suggestions make no provider calls and do not guarantee offers, availability or prices. Backend validation remains authoritative; safe unsupported-city field errors differ from a supported route returning unavailable prices or a provider failure. Dynamic/live autocomplete is not implemented or required by the approved fixed-set scope.

### Generation lifecycle and Results semantics

Pending operations show an accessible loading state, disable duplicate submission and use a 70-second local transport allowance. Progress steps are an unverified visual guide. Errors retain form values on the mounted planner and offer appropriate edit, sign-in or deliberate retry actions: 400 city/date errors, 422 validation, 401/session expiry, 429 rate limit, 500/502/503/504 service failures and network errors. Recognized field names map to safe local messages; raw server/debug text is not displayed. A valid accessible request reference can be shown. CORS must expose `X-Request-ID` and `Retry-After`.

Retry-After seconds or HTTP dates disable retry until the deadline; editing does not bypass the cooldown. Expiry of the countdown never submits anything. Stopping local waiting, timeout or identity invalidation does not guarantee cancellation of server processing; another deliberate submission may start another chargeable operation. No generation request is retried automatically and no failure falls back to sample results. Navigating away, including to Login, or refreshing does not persist the form.

Verified account changes, signout or definitive loss of identity invalidate the local operation token and request owner synchronously, including A → B → A. Late success/error cannot navigate or replace newer state. Same-account re-verification is not itself an identity transition. Retained Results are also account-bound and cleared on identity loss/change.

Results display backend-selected offer IDs, source names, retrieval timestamps in UTC, itinerary, warnings, cost items, missing categories and budget statuses as supplied. **Retrieved price** describes a returned quote at its reported retrieval time, including older cached quotes; it is not a guarantee of present availability or a Live claim. Flight/hotel availability is separate, so a valid trip may contain hotels but unavailable flights. Taxes distinguish included, additional and unknown. Unknown/null costs never become $0.00; explicit zero activity estimates may read **Estimated free**. Provider/estimated subtotals, projected totals and within-budget/over-budget/uncertain status are not recalculated or corrected in the browser, including supplied zero subtotals and known-minimum-over-budget cases.

## FE-04 authenticated E2E verification — October 28, 2026

This sanitized record documents Diyar's reported real browser test, separate from mocked tests. Backend under test: isolated BE-03 commit `7987f73a9f2b1754a0cd1c3da1aafb90eac65a36`. No credentials, account identifiers, tokens or raw provider payloads are included.

| Test detail | Reported observation |
|---|---|
| Route and dates | Istanbul → Rome; December 1–4, 2026 |
| Travelers and budget | 2 adults; USD 1,500 whole-trip budget |
| Authenticated workflow | Login → Generate Trip → successful authenticated POST → Results rendered |
| Hotel and itinerary output | Retrieved Booking hotel prices, source names, retrieval timestamps, day-by-day itinerary and budget/unknown-cost handling appeared |
| Flights | API returned unavailable flights; no flight-price retrieval is claimed |

The real frontend partial-price integration succeeded. This does not prove every provider succeeded. The exact flight-unavailability cause remains unconfirmed; Adel/Ziyad own backend/provider investigation. No frontend defect explaining missing flights has been established.

The subsequent lifecycle correction was verified with **335 mocked frontend tests passing, 0 failures**, including 14 identity-transition regressions; TypeScript, production build and whitespace checks passed. The build retains the existing large-chunk warning. These are prior implementation-check results, not new live tests or a claim that documentation editing reran them.

### Real authenticated unsupported-city rejection — October 28, 2026

One separately authorized POST used the existing verified browser session and shared authenticated API client against the local BE-03 endpoint at `http://127.0.0.1:8000/api/v1/trips/generate`. The fixed request was Istanbul → Atlantis, December 1–4, 2026, 2 adults, USD 1,500. Before submission, the temporary development-only control checked the local origin, future dates, supported Istanbul and unsupported Atlantis against the approved mapping. It bypassed only the normal form's local city rejection to exercise backend validation; authentication was not bypassed.

| Observed result | Sanitized evidence |
|---|---|
| HTTP status | 400 |
| Error code | `UNSUPPORTED_LOCATION` |
| Field detail | `destination_city` was recognized; safe frontend wording: “Check your destination city.” |
| Request references | Accessible response header and body references matched; values are not recorded here |
| Submission count | One explicit POST; no retry or valid-trip generation |

This result was observed through the control's sanitized UI, not inferred from a mock. Backend source at `7987f73` confirms `search_travel()` validates city membership before entering provider search; its unsupported error maps to HTTP 400 and returns before itinerary/AI generation. **Early rejection before paid provider calls is source-confirmed; provider traffic was not independently captured or monitored.** No direct provider requests were made by the test. This is not a claim of packet-level proof that no external traffic occurred.

The temporary rejection control, its state/imports and dedicated tests were removed after evidence review. The original development-only JWT/session probe remains at `/dev/auth-probe`; neither tool is a production feature. The unsupported-city real-backend acceptance evidence gap is now closed. Ali's DES-03 visual review remains pending; no confirmed frontend functional blocker remains from this verification. The unavailable-flight cause remains unconfirmed for Adel/Ziyad's backend/provider investigation, not a demonstrated frontend defect.

## BE-02 Auth and JWT verification

Run `npm run typecheck`, `npm run build`, and `node --experimental-strip-types --test tests/*.test.mjs` from `frontend/`. Auth unit tests use explicitly labeled SDK doubles, not real accounts. They cover missing/unsafe configuration, signup metadata and confirmation, login errors, stored-session verification, refresh, expiry, logout and stale-event cleanup.

Signup, login, logout, email confirmation, session persistence and password recovery are implemented and reported working locally. The following sanitized real integration outcomes were reported by Diyar from joint testing against [backend PR #23](https://github.com/Nasrawy1/TravelMate/pull/23), commit `e4fe192`, using Supabase **ES256** signing:

| Manual test | Observed result |
| --- | --- |
| Account A | HTTP 200, identity matches |
| Account B | HTTP 200, identity matches |
| Missing JWT | HTTP 401 UNAUTHORIZED |

PR #23's development-only probe verifies the bearer JWT; commit `e4fe192` exposes `X-Request-ID` through CORS. These reported real results are separate from automated mocked tests and do not prove real trip generation, provider integration or Results response validation. No live authentication or password changes are performed by the automated tests. Never record credentials, confirmation links or personal identifiers in test evidence.

Verified session state controls Welcome planning links and shared account navigation. Signed-in users go directly to Trip Planner; anonymous users keep the signup/login entry flow. Session initialization waits without redirecting, and Login/Signup replace their forms with a Riviera signed-in card. Only a filtered display name from verified Auth metadata is presented; full email is not shown by default. Navigation alone never submits generation or changes fixture pricing behavior.

## BE-02 email confirmation and recovery

New email flows use `flowType: 'pkce'`. The SDK stores the code verifier when signup/recovery is requested and exchanges the captured single-use code on return. Signup still requests `${VITE_APP_URL}/login`; recovery still uses `${VITE_APP_URL}/reset-password`. No Dashboard/template changes are made. Open the email link in the same browser profile and exact origin that requested it; localhost and 127.0.0.1 are different storage origins. Do not switch origins, clear browser storage, or start several overlapping email flows during testing. Missing/wrong verifiers and expired/reused codes fail closed. Optional `sb_flow_id` is captured and forwarded explicitly if present. `/auth/callback` remains an optional destination requiring its own allowlist entry. Custom token-hash templates are not processed automatically.

Before BrowserRouter renders, recognized URL credentials/errors are captured in memory and removed using history replacement. Referrer policy is `no-referrer`. Tokens, full callback URLs and raw provider errors are never logged or placed in React state. Confirmation requires a verified user and valid SDK-verified JWT claims, then establishes the SDK session. Invalid/expired/reused email-link errors show safe guidance even if another session already exists.

Forgot Password calls `resetPasswordForEmail` and shows the same accepted-request acknowledgement regardless of whether the address is registered; acceptance does not prove delivery. No automatic retries occur.

Reset Password requires a captured recovery callback, server-verified user, verified JWT `amr` recovery method/timestamp, matching `session_id`, and an unexpired in-memory authorization. The local authorization lasts at most 15 minutes from recovery authentication, bounded by token expiry. A URL `type=recovery` or ordinary login alone never authorizes a change. Session/claims are rechecked immediately before `updateUser({ password })`. Successful updates consume authorization. Reloading, signing out, changing identity, expiry or leaving recovery revokes it; request another email after losing authorization. Password-policy errors allow an explicit edit/retry while authorization remains valid.

Update completion is also checked against the captured lifecycle epoch, grant and expiry deadline. Late responses after signout, account change, expiry or navigation are ignored locally, including errors. They do not restore success, retry the password update or imply that the remote request failed. A current, confirmed successful update displays **Password updated successfully** and **Return to sign in**; it preserves the SDK session instead of automatically signing out.

For repeat manual verification, the account owner must open fresh email links and enter new passwords themselves. Automated tests cover invalid/expired/reused callbacks and unauthorized access with mocks; do not treat those tests as additional real-email evidence. If custom access-token hooks omit recovery AMR/session claims, recovery fails closed; coordinate the actual claim shape with Adel rather than weakening the gate. No application tables are required for these Auth flows.

### Recovery callback compatibility

Supabase's implicit verification path can issue generic `otp` claims, which remain insufficient for recovery authorization. PKCE flows preserve the recovery authentication method through server code exchange, and existing identity/session/expiry checks remain mandatory. Legacy implicit confirmation remains supported; old recovery links with generic OTP claims still fail closed. A new email is required after migrating from implicit recovery to PKCE.

URL cleanup is intentional: credentials/codes and optional flow correlation are captured in memory before history replacement, then passed explicitly to SDK methods while automatic URL detection stays off. React StrictMode/concurrent processing shares one exchange promise. Cleanup does not consume the email verification link or remove its captured credentials prematurely.

PKCE requires the browser/profile and exact origin that stored its verifier. Requesting an email in the Codex in-app browser and opening it in Chrome does not share that verifier. Respect provider cooldowns and avoid overlapping flows when repeating a manual test. If verification fails, record only safe error categories and have Adel inspect Auth logs privately; never share full recovery links or credentials.

## FE-03 production offline verification

Prepare dependencies while internet is available, then build and serve locally:

```sh
cd frontend
npm ci
npm run build
npm run preview
```

Open `http://localhost:4173/offline-demo` directly; no account or environment
configuration is required. Preview must stay running. Disconnect external internet
while keeping localhost/loopback available, then cold-load/reload each of:

- `/offline-demo?trip=rome`
- `/offline-demo?trip=paris`
- `/offline-demo?trip=barcelona`

Use a fresh browser context or disable the HTTP cache to avoid relying on cached
Google fonts or assets. Check selection, Back/Forward, reloads, all itinerary days,
budget details, unknown costs and the permanent DEMO banner. Inspect the network
log: only the local preview origin should be requested; no font CDN, Supabase,
FastAPI, AI, analytics or travel-provider request should occur. Do not select a
browser Offline setting that also blocks localhost when testing a cold load.

The demo data is statically imported into local production JavaScript; switching
trips needs no lazy fetch. Production chunk/import tests check that any emitted
JavaScript dependencies resolve to bundled files. Development-only fixture and
JWT-probe chunks remain excluded. This is a locally served offline presentation,
not a service-worker installation: stopping the server or blocking loopback is
not supported. The manual results below record the reported disconnected-browser
run; second-computer testing is not claimed.

### Manual offline evidence reported by Diyar

**Recorded:** 2026-10-24. **Branch:** `feat/fe-03-offline-demo`.
**Environment reported:** Chrome, production preview at
`http://localhost:4173/offline-demo`, Wi-Fi disconnected, localhost preview server
still running after dependencies and production assets were prepared locally.

This is sanitized **user-reported manual evidence**, not an automated test or an
agent-observed network-disconnection test. No raw Network export/HAR or screenshot
was supplied with this report; the observations below are recorded as reported.
They contain no credentials, account identifiers or private configuration.

| Manual check | Reported observation | Result |
|---|---|---|
| Istanbul → Rome | Hard reload succeeded with Wi-Fi disconnected. | PASS |
| London → Paris | Loaded offline; Over budget with a $670 sample projected total. | PASS |
| Dubai → Barcelona | Loaded offline; Uncertain budget, hotel unavailable and flight taxes unknown. | PASS |
| Sample provenance | All screens retained a visible DEMO banner and sample-price labels. | PASS |
| Local application assets | Chrome Network showed only localhost document, JavaScript and CSS requests returning HTTP 200, plus the favicon request below. | PASS |
| External requests | No Supabase, FastAPI, Google Fonts or other external requests appeared in the captured log, according to the report. | PASS |
| Local favicon | `favicon.ico` returned HTTP 404 from localhost. | Non-blocking polish issue |

The favicon failure does not prevent sample loading and is not an external
request. It was not fixed in this documentation-only update. No claim is made
that separate cold-cache reloads of Paris/Barcelona, Back/Forward while
Wi-Fi-disconnected, a signed-out fresh-profile run, other browsers or a second
computer were manually tested. No-sign-in access is additionally supported by
route inspection and configured-client isolation tests. The reported hard reload,
all-three-trip display and local-only Network observations cover Issue #27's
required offline demonstration; the extra cases above remain useful handover
checks rather than silently assumed results.

### Historical FE-03 automated verification rerun

These checks were executed separately from Diyar's original manual browser test
when recording FE-03 evidence. Counts below are historical, not the current
FE-04 suite count. They do not simulate a physical Wi-Fi disconnection:

| Check | Result |
|---|---|
| `node --experimental-strip-types --test tests/*.test.mjs` from `frontend/` | 232 passed, 0 failed |
| `python tests/validate_offline_demo.py` from `frontend/`, with `jsonschema` available | 23 passed: all three original datasets, schema/semantic checks, provenance and 15 rejected invalid mutations |
| `python docs/contracts/validate_fixtures.py` from the repository root | 12 shared fixtures passed; 8 invalid mutations rejected |
| `npm run typecheck` from `frontend/` | PASS |
| `npm run build` from `frontend/` | PASS; existing warning for a JavaScript chunk larger than 500 kB |
| `git diff --check` and new-file whitespace inspection | PASS |

Schema and semantic checks use the checked-in v0.4 schema and shared validator,
with the documented fixed fixture clock of 2026-10-15 UTC. They verify selected
offer references, fee-aware selection, ledger links and arithmetic, complete
itinerary dates, tax semantics, budget status, unknown/null amounts and explicit
zero estimates. The frontend formats supplied totals without recalculating them.
Automated coverage also checks that all three journeys are in production assets,
all emitted asset/chunk references are local, DEV fixture tools and the JWT probe
are excluded, and direct demo rendering does not initialize the configured Auth
client. These are complementary checks, not evidence of live travel prices.

### Issue #27 task and acceptance coverage

Source: [FE-03: Implement Explicit Offline Demo](https://github.com/Nasrawy1/TravelMate/issues/27).
All six tasks and all three acceptance criteria are covered by the implementation
and evidence below. This local record does not change GitHub checkbox states or
claim team review/merge approval.

| Issue requirement | Status | Implementation and evidence |
|---|---|---|
| Task: bundle 2–3 complete predefined trips locally | PASS | `src/data/offlineDemo/{rome,paris,barcelona}.json`; `offlineDemo.test.mjs`, `validate_offline_demo.py` and production asset tests. |
| Task: clear DEMO status; samples are not real-price evidence | PASS | Permanent banner in `src/pages/OfflineDemoPage.tsx`; shared Demo price labeling through `src/utils/results.ts`; UI tests and reported manual observations. |
| Task: reuse Results components with explicit demo context | PASS | `OfflineDemoPage` passes `data_mode=offline_demo`, `live_evidence=false` to `TripResults`; shared offers, budget and itinerary components; `offlineDemoUi.test.mjs`. |
| Task: access without sign-in, backend generation, Supabase or external-provider calls | PASS | Route outside Auth providers in `src/App.tsx`; local data imports, Auth initialization sentinel in `authRoutes.test.mjs`, service-free demo graph test, and reported local-only Network log. No manual fresh-profile claim. |
| Task: initialize online services only for the selected online flow | PASS | Lazy `getSupabaseClient` construction and online route providers; demo stays outside both providers. Auth isolation tests and reported absence of Auth/API requests. Online exit links leave the demo explicitly. |
| Task: verify operation with network disabled after local installation | PASS | Diyar's reported Wi-Fi-disconnected production preview test, with localhost server kept running. |
| Acceptance: all sample trips open/display without network access | PASS | All three trips reported displayed while Wi-Fi was disconnected; Rome hard reload explicitly reported. |
| Acceptance: no authentication, generation or save requests | PASS | Demo has no request/save controls or service imports; configured-client isolation tests and reported local-only Network log. |
| Acceptance: clear DEMO status; unknown prices are not zero | PASS | Reported visible labels and Barcelona missing-price state; UI/data tests verify unknown hotel/taxes/total remain null or Unknown/Not calculable, while explicit free activities remain zero. |
| Deliverables: offline demo, local samples, instructions and test evidence | PASS | Implemented route and bundled data; setup/retest instructions and separate manual/automated evidence in this README. |

### Delivery assessment and remaining review items

**PASS for implemented FE-03 #27 functionality and recorded evidence.** No
confirmed functional blocker remains from these checks. The local favicon 404
and existing bundle-size warning are non-blocking and remain documented.

The original FE-03 record requested Ali/Nasrawy's agreement on the proposed
journeys; it does not invent that approval. Current typography uses bundled
Figtree/Fraunces rather than the earlier Georgia/system-ui-only fallback.
Public v0.4 is now adopted; revalidate samples if the adopted contract changes.
Ali's current DES-03 visual review remains pending. Second-computer handover
remains outside the evidence provided here and is broader MVP handover work.

The original FE-03 evidence was recorded before its delivery. That historical
record is not a statement of current Git delivery status. This FE-04
documentation-only update performs no staging, commit, push, PR or merge action
and leaves application source, environment files and running servers unchanged.
