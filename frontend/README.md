# TravelMate frontend — FE-01 foundation and FE-02 increments

React + Vite + TypeScript frontend owned by Diyar. The Welcome and authentication UI follow [Ali’s original Riviera design archive](../docs/design/travelmate-des01-welcome-auth.zip), stored at `docs/design/travelmate-des01-welcome-auth.zip` from the repository root. The unchanged ZIP contains `design/welcome-auth.md` and the original Welcome/authentication HTML sources under `travelmate-des01-welcome-auth/`. Signup/Login and session management now have a real Supabase SDK boundary. Auth requires local configuration; authenticated trip generation is not connected.

## Implemented UI and current limits

- **Welcome:** Riviera landing sections, sample postcards, price-label explanations, and links to Signup, Login and the demo entry. Hard-coded prices are marked Sample/Example; they are not live provider data.
- **Login:** email/password fields, password visibility, required/email validation, accessible errors, pending-state controls and navigation to Signup, Forgot Password, Home and Demo.
- **Signup:** display name, email, password and confirmation; a live password-rule checklist; shared password visibility; validation, accessible errors and pending-state controls. Name is a display name, not trip traveler data.
- **Forgot Password:** email validation and a reset-link request form in the centered Riviera layout.
- **Reset Password:** new-password/confirmation validation and password visibility in the same layout.

Signup and Login call the shared Supabase client when configured. Signup sends `display_name` as Auth user metadata and shows account-neutral confirmation instructions when no session is returned; it does not prove email delivery or a new account. Login uses password authentication. Restored and refreshed sessions remain unverified in the UI until `getUser` confirms identity; expired or unverifiable sessions never show as signed in. Auth pages show the verified session, a Trip Planner link, and browser-local logout. No automatic generation or successful trip is implied. Forgot/Reset Password now use Supabase. Email confirmation callbacks are handled explicitly; automatic SDK URL detection stays disabled so callback errors cannot silently fall back to an existing session. See the recovery verification section below. The current UI password rule is 8+ characters, including a letter and a number; it must be aligned with Adel’s configured Supabase policy before integration.

**Trip Planner** implements the six-field v0.4 candidate form, UTC date/night/adult/budget validation and an honest local request preview. In development only, prepare valid details and expand **Development only · MOCK generation previews** to inspect loading and error states. Repository fixtures retain their original metadata; missing error cases are labeled frontend examples. No successful trips are fabricated, no requests are sent, and the production build excludes these preview controls/fixtures. See [the generation service boundary](src/services/README.md) for injection and validation requirements.

**Results** implements reusable Riviera trip summary, selected offers, daily itinerary, warnings, budget and itemized-expense components. Direct `/results` navigation shows an honest empty state. In development, expand **Development only · Results fixture preview** and choose one of the six repository success fixtures. A sticky, non-dismissible MOCK banner remains visible; provider-shaped fixture amounts say **Sample price**, never Live. Supplied totals/status are formatted without recalculation, and unknown amounts remain unknown. The manifest and matching case metadata travel with each response; fixture imports and controls are excluded from production assets.

Offline Demo remains a **placeholder page**. There is no real generated itinerary or complete offline demo. Supabase Auth and a reusable FastAPI HTTP client are implemented; the development-only JWT probe uses that client, while product trip-generation flows remain unconnected. The Supabase SDK connects only when valid local configuration is supplied. Complete offline-demo journeys remain FE-03 work. Final API contract adoption still requires PLAN-02 (#11) review.

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

For local FastAPI testing, set `VITE_API_BASE_URL` locally to Adel's confirmed origin only, such as `http://127.0.0.1:8000`; do not append `/api/v1`. The example file retains a placeholder. Missing or unsafe configuration fails closed. Setting the value does not enable generation or trigger requests. No local environment file is changed by this implementation.

The shared `api` in `src/services/api.ts` takes root-relative paths. Its default is protected access: each request obtains the current SDK session and refreshes a nearly expired token before attaching its bearer header. Public endpoints require `{ auth: 'none' }`; the foundation's existing `/api/v1/health` is public. The client rejects external destinations and redirects and never retries API operations or signs out automatically. Handle `ApiError.code === 'UNAUTHORIZED'` with a user-controlled sign-in action while preserving form inputs. Success bodies remain `unknown` until endpoint-specific runtime validation. See [service documentation](src/services/README.md#be-02-fastapi-transport-preparation) for policies and dependencies.

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
| `/trip-planner` | Validated Trip Planner with local request preview; development-only MOCK lifecycle/error inspector |
| `/results` | Empty state by default; reusable Results UI with development-only structural fixture previews |
| `/offline-demo` | Explicitly labeled DEMO placeholder; no bundled trips loaded |
| Any other path | Page-not-found placeholder |

Routes remain public in this increment; Auth session UI does not protect backend data or enable generation. Opening `/reset-password` is not authorization to update credentials; a fresh verified recovery callback/session is required. There is no fake link-sent or password-updated screen.

BrowserRouter supports client navigation and direct links through Vite. A future static host must serve `index.html` for application routes.

## Main files and folders

- `src/main.tsx`: React entry point, BrowserRouter and global CSS.
- `src/App.tsx`: route definitions.
- `src/pages/`: Welcome/auth/recovery, Trip Planner and Results UI; demo placeholder.
- `src/components/welcome/`: shared Riviera logo, price badges and illustrative postcards.
- `src/components/auth/`: reusable password input and recovery layout/error/submit components.
- `src/components/results/`: presentation components accepting v0.4 candidate responses and explicit provenance; a separate development-only fixture selector.
- `src/components/layout/AppLayout.tsx`: navigation and layout for the remaining placeholders and unknown routes.
- `src/components/PlaceholderPage.tsx`: reusable page content wrapper.
- `src/styles/`: global defaults, shared Riviera/Login styling and scoped Signup/recovery additions.
- `src/services/`: configured Supabase Auth, SDK session management, verified recovery authorization, and a reusable FastAPI API client with safe errors. The development probe uses the client; real trip generation remains unconnected. Credentials/tokens are never logged; session persistence is SDK-managed.
- `src/types/`: shared types and v0.4 candidate request/Results presentation interfaces. Types alone do not validate HTTP responses.
- `src/assets/`: reserved for approved local assets.
- `src/fixtures/generationMocks.ts`: development-only error fixture/example adapter; not offline demo data.
- `src/fixtures/resultsFixtures.ts`: development-only imports of the six original `docs/fixtures/` responses and manifest; not copied prototype data or a production fallback.
- `vite.config.ts`, `tsconfig.json`: Vite React plugin and strict TypeScript configuration.

## Integration and offline boundaries

Scope follows the repository’s MVP scope and architecture: one destination, 1–4 adults, 1–7 nights, whole-trip USD budget, backend-owned budget calculations, and a separate read-only demo. The planner validates these form constraints locally. The API v0.4 review candidate is not implicitly approved by this implementation; confirm adoption and full response validation with the team before real integration.

Supabase Auth and protected JWT transport have been implemented and tested locally as recorded below. Real trip-generation endpoint integration and its generation-to-Results handoff remain pending. Future generation responses need full schema and semantic validation before passing them to the shared Results components. A trusted adapter must construct the `validated_api` provenance context; `live_evidence` must come from verified provider-sourced backend output. The public API does not carry the fixture manifest, and a badge alone is not live-price evidence. Fixture loading is isolated from the generation controller: selecting a fixture never completes a pending generation or establishes a session.

The current pages use local UI assets but request Fraunces/Figtree from Google Fonts. Fallback system/serif fonts are available without that network access. Direct Offline Demo does not initialize Auth or contact providers; configured online routes may contact Supabase. Offline Demo is only a labeled entry placeholder, not the FE-03 implementation or a verified offline handover. Complete online/demo operation and second-computer testing remain later work.

## BE-02 Auth and JWT verification

Run `npm run typecheck`, `npm run build`, and `node --experimental-strip-types --test tests/*.test.mjs` from `frontend/`. Auth unit tests use explicitly labeled SDK doubles, not real accounts. They cover missing/unsafe configuration, signup metadata and confirmation, login errors, stored-session verification, refresh, expiry, logout and stale-event cleanup.

Signup, login, logout, email confirmation, session persistence and password recovery are implemented and reported working locally. The following sanitized real integration outcomes were reported by Diyar from joint testing against [backend PR #23](https://github.com/Nasrawy1/TravelMate/pull/23), commit `e4fe192`, using Supabase **ES256** signing:

| Manual test | Observed result |
| --- | --- |
| Account A | HTTP 200, identity matches |
| Account B | HTTP 200, identity matches |
| Missing JWT | HTTP 401 UNAUTHORIZED |

PR #23's development-only probe verifies the bearer JWT; commit `e4fe192` exposes `X-Request-ID` through CORS. These reported real results are separate from automated mocked tests and do not prove real trip generation, provider integration or Results response validation. No live authentication or password changes are performed by the automated tests. Never record credentials, confirmation links or personal identifiers in test evidence.

Verified session state now controls Welcome planning links and shared account navigation. Signed-in users go directly to Trip Planner; anonymous users keep the signup/login entry flow. Session initialization waits without redirecting, and Login/Signup replace their forms with a Riviera signed-in card. Only a filtered display name from verified Auth metadata is presented; full email is not shown by default. Authenticated navigation does not enable FastAPI generation or change fixture pricing behavior.

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
