# TravelMate

AI-assisted travel planning — graduation project.

**Current state on the FE-04 review branch:** Supabase Auth, authenticated v0.4 trip generation, validated in-memory Results handoff, and the independent three-trip Offline Demo are implemented. PR #35 is under review; this statement does not claim that FE-04 is merged into `main`.

**Latest live E2E — October 28, 2026:** One authenticated Istanbul → Rome generation (December 1–4, 2026; 2 adults; USD 1,500) returned HTTP 200 against BE-03 `bbe1a84` with confirmed runtime `TRAVELMATE_FLIGHT_MODE=live`. Results displayed three flight offers, hotel information and four itinerary days; the budget was Uncertain because some costs remained unknown. The exact flight-status field and complete warnings array were not retained after diagnostic capture failed. No visible Warnings section does not establish an empty warnings array. See the [detailed FE-04 evidence and limitations](frontend/README.md#fe-04-authenticated-e2e-verification--october-28-2026), which separately preserves the earlier unavailable-flight run.

**Automated verification after local review fixes:** 372 frontend tests passed; TypeScript and production build passed. City-sync `--check` and 13 focused regression tests passed on each of Python 3.12.14 and 3.14.5. These checks are separate from live E2E evidence; no additional generation/provider requests were made for the review fixes or documentation.

## Documentation

- [Frontend setup and current UI status](frontend/README.md) — prerequisites, installation, routes, development commands and integration limits.
- [MVP scope](docs/mvp-scope.md) — mandatory versus optional functionality.
- [Architecture](docs/architecture.md) — React/Vite, FastAPI and service boundaries.
- [API contracts](docs/api-contracts.md) — adopted v0.4 request/response/error formats and implementation observations.
- [Database schema](docs/database-schema.md) — optional saved trips and backend-only access.
- [Implementation plan](docs/implementation-plan.md) — proposed priorities, owners and issue corrections.

## Core delivery

Online: Supabase Auth → trip input → real AI itinerary + at least one real flight OR hotel price integration → results and backend-calculated budget assessment.

Limits: one destination, 1–4 adults, 1–7 nights, whole-trip USD budget. Generation does not persist trips. Saving and the second live provider are optional; booking/payment UI is deferred.

Offline: a separate read-only frontend demo with 2–3 bundled example trips, visibly marked DEMO, no hosted login or provider calls. It does not satisfy the real-price acceptance gate.

## Development and handover

Follow the [frontend setup instructions](frontend/README.md) for local commands, Auth/API configuration and verification records. Real generation requires the separately configured BE-03 backend and provider credentials; frontend fixtures and Offline Demo do not replace it. The demo and local fonts were manually tested with Wi-Fi disconnected while the local preview server remained running. Full online/demo handover on a second computer remains unverified. Keep local environment files outside Git.

Keep API keys and elevated Supabase credentials server-side and outside Git. Never put secrets in VITE-prefixed variables. Use a dedicated non-production Supabase project.

## Review status

PR #35 contains FE-04 integration and Ali-reviewed DES-03 polish. The latest live run supplies authenticated generation/Results evidence, but does not establish guaranteed current prices, every-provider success or complete captured warnings. The earlier flight-unavailability cause remains unconfirmed for Adel/Ziyad; the later three-offer run does not retrospectively explain it. Public budget tie-breaking confirmation from Adel is still pending; the frontend review fix matches the inspected BE-03 public request schema. See the [detailed verification record](frontend/README.md#fe-04-authenticated-e2e-verification--october-28-2026) and [contract implementation note](docs/api-contracts.md#budget-cent-normalization--implementation-observation).

## Supabase Configuration and Setup

BE-01 configures the dedicated TravelMate development project and documents safe handoff values. It does not implement frontend login/session behavior or backend JWT verification; those integrations are BE-02.

For a fresh project, create/select the dedicated TravelMate development project in the Supabase Dashboard and enable the **Email** provider under **Authentication → Sign In / Providers**. Keep email confirmation enabled.

### Auth and local redirect settings

- Provider: Supabase Auth email/password.
- Email confirmation: enabled; a new account must confirm its email before password sign-in.
- Site URL: `http://localhost:5173`.
- Allowed redirects: `http://localhost:5173/**`, `http://localhost:5173/reset-password`, and `http://127.0.0.1:5173/**`.

Set these in the Supabase Dashboard under **Authentication → URL Configuration**. If Vite runs on another port, update the Site URL and allowed redirect URLs to match the local frontend origin.

### Frontend configuration for BE-02

Find the Project URL and public publishable key in the project's **Connect** dialog. The key is also listed under **Project Settings → API Keys**. Use the publishable key in browser code; never put a secret/service-role key in the frontend or a `VITE_` variable.

`frontend/.env.example` uses placeholders only:

```dotenv
VITE_SUPABASE_URL=https://<project-ref>.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=<publishable-key>
VITE_APP_URL=http://localhost:5173
```

The `.env.example` uses the confirmed variable names from Diyar's frontend code.

Copy the example to a local, ignored `.env.local` and replace the placeholders for BE-02 integration. Do not commit local environment files or real project-specific values.

### Backend token verification settings for BE-02

The backend verifies user access-token signatures and claims. These values are project configuration, not secret keys. Find the Project URL in the **Connect** dialog. Supabase Auth's JWKS URL and issuer are derived from that project URL; the signing-key controls are under **Project Settings → JWT Keys**. The expected audience for a normal signed-in user access token is `authenticated`; BE-02 should verify it against the token's `aud` claim.

Placeholder-only backend example:

```dotenv
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_JWKS_URL=https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json
SUPABASE_JWT_ISSUER=https://<project-ref>.supabase.co/auth/v1
SUPABASE_JWT_AUDIENCE=authenticated
```

Do not put access tokens, signing secrets, or service-role/secret API keys in this file or commit them. Supabase documents [publishable keys](https://supabase.com/docs/guides/getting-started/api-keys), [JWT claims](https://supabase.com/docs/guides/auth/jwt-fields), and [JWT verification/JWKS](https://supabase.com/docs/guides/auth/jwts).

## Local Authentication Testing

Diyar reported successful frontend signup, email confirmation, login, password recovery and sign-out testing. Subsequent BE-02 JWT and FE-04 generation evidence is recorded in the [frontend documentation](frontend/README.md). The following optional PowerShell smoke test calls Supabase Auth directly and can independently verify the project; it is not required to reproduce the already recorded E2E evidence. Supabase’s default SMTP only sends confirmation emails to authorized team members of the Supabase project; an arbitrary new email address may not receive one. For a new test account, use an authorized team member’s email address. For repeat runs, remove the previous test account in the Dashboard or use another authorized email. Do not paste credentials or access tokens into source files, terminal transcripts, or Git.

1. Set the project values in the current terminal session and enter the test account details:

   ```powershell
   $env:SUPABASE_URL = "https://<project-ref>.supabase.co"
   $env:SUPABASE_PUBLISHABLE_KEY = "<publishable-key>"
   $email = Read-Host "Test account email"
   $securePassword = Read-Host "Test account password" -AsSecureString
   $password = [System.Net.NetworkCredential]::new("", $securePassword).Password
   $headers = @{ apikey = $env:SUPABASE_PUBLISHABLE_KEY }
   ```

2. Submit signup. This sends a confirmation email because email confirmation is enabled:

   ```powershell
   $signupBody = @{ email = $email; password = $password } | ConvertTo-Json
   $signup = Invoke-RestMethod -Method Post -Uri "$($env:SUPABASE_URL)/auth/v1/signup" -Headers $headers -ContentType "application/json" -Body $signupBody
   "Signup request completed; check the test inbox for the confirmation link."
   ```

3. Open the email and follow its confirmation link. In the Dashboard, check **Authentication → Users** and confirm the test account appears with a confirmed email.
4. Sign in with the confirmed account. Keep the response in a variable and do not print or copy its access token:

   ```powershell
   $signinBody = @{ email = $email; password = $password } | ConvertTo-Json
   $session = Invoke-RestMethod -Method Post -Uri "$($env:SUPABASE_URL)/auth/v1/token?grant_type=password" -Headers $headers -ContentType "application/json" -Body $signinBody
   "Password sign-in succeeded."
   ```

5. In **Authentication → Users**, verify the account's last sign-in time. Remove the local variables when finished:

   ```powershell
   Remove-Variable signup, signupBody, signinBody, session, password, securePassword, headers, email
   ```

This direct smoke test verifies Supabase Auth through its API; it does not itself verify FastAPI token verification or protected backend session handling. Subsequent real frontend JWT-probe and authenticated generation evidence is recorded separately in the frontend documentation.

## Setup Verification Record

Historical BE-01 test-account evidence (UTC; no credentials or tokens). Pending labels below describe that earlier setup stage, not the current FE-04 review branch:

- [x] Confirmation email sent: **2026-10-17 17:14 UTC**.
- [x] Email confirmed: **2026-10-17 20:14 UTC**.
- [x] Password sign-in succeeded: **2026-10-17 21:06 UTC**.
- [x] Test account was visible in Supabase `auth.users`.
- Password recovery: Initial attempt blocked by HTTP 429 rate limit (Supabase default limit is 2 emails/hour). After the rate limit reset, Diyar tested the full recovery flow successfully in the frontend. To address email delivery limits for production, the team plans to configure a custom SMTP provider once a verified sending domain is available. Custom SMTP lets the project configure sending limits; it does not remove limits entirely. SMTP setup is not required for BE-01 and is a separate future task.
- [x] Sign-out succeeded in Diyar's frontend test; no timestamp was recorded.
- [ ] FastAPI bearer-token verification and protected backend session handling: **pending BE-02**.

The historical setup record above is supplemented by the [BE-02 Auth/JWT verification](frontend/README.md#be-02-auth-and-jwt-verification) and the [FE-04 authenticated generation records](frontend/README.md#fe-04-authenticated-e2e-verification--october-28-2026). These distinguish Auth-only tests, protected backend tests and complete generation/Results observations.

