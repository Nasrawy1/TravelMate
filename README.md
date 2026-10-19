# TravelMate

AI-assisted travel planning — graduation project.

**Current state:** The React/Vite frontend includes the Auth UI. Diyar reports successful Supabase signup, login, email confirmation, password recovery, and sign-out tests on his separate frontend branch. That branch has not yet been merged into `main`; these results do not describe an integrated frontend running on `main`. FastAPI token verification and protected backend session handling remain BE-02 work. Trip Planner, Results and Offline Demo remain placeholders; trip generation is not connected.

## Documentation

- [Frontend setup and current UI status](frontend/README.md) — prerequisites, installation, routes, development commands and integration limits.
- [MVP scope](docs/mvp-scope.md) — mandatory versus optional functionality.
- [Architecture](docs/architecture.md) — React/Vite, FastAPI and service boundaries.
- [API contracts](docs/api-contracts.md) — v0.3 core request/response/error formats.
- [Database schema](docs/database-schema.md) — optional saved trips and backend-only access.
- [Implementation plan](docs/implementation-plan.md) — proposed priorities, owners and issue corrections.

## Core delivery

Online: Supabase Auth → trip input → real AI itinerary + at least one real flight OR hotel price integration → results and backend-calculated budget assessment.

Limits: one destination, 1–4 adults, 1–7 nights, whole-trip USD budget. Generation does not persist trips. Saving and the second live provider are optional; booking/payment UI is deferred.

Offline: a separate read-only frontend demo with 2–3 bundled example trips, visibly marked DEMO, no hosted login or provider calls. It does not satisfy the real-price acceptance gate.

## Development and handover

Follow the [frontend setup instructions](frontend/README.md) to run the current UI locally. Combined frontend/backend startup and complete offline-demo handover remain future work. Implementation owners must document tested prerequisites, safe .env.example files and startup commands as integrations are built. Verify full online and demo operation on a second computer before final submission.

Keep API keys and elevated Supabase credentials server-side and outside Git. Never put secrets in VITE-prefixed variables. Use a dedicated non-production Supabase project.

## Review status

Documentation is a review candidate, not evidence of team approval or provider feasibility. Pending: AI evidence, mandatory live provider and supported searches, estimation/conversion policy, offer selection confirmation and measured timeout tuning. See the implementation plan for ownership.

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

Diyar reports successfully testing signup, email confirmation, login, password recovery, and sign-out on his separate frontend branch, which has not yet been merged into `main`. The following optional PowerShell smoke test calls Supabase Auth directly and can independently verify the project. Supabase’s default SMTP only sends confirmation emails to authorized team members of the Supabase project; an arbitrary new email address may not receive one. For a new test account, use an authorized team member’s email address. For repeat runs, remove the previous test account in the Dashboard or use another authorized email. Do not paste credentials or access tokens into source files, terminal transcripts, or Git.

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

This direct smoke test verifies Supabase Auth through its API; it does not verify FastAPI token verification or protected backend session handling. Those remain BE-02 work.

## Setup Verification Record

Recorded BE-01 test-account evidence (UTC; no credentials or tokens):

- [x] Confirmation email sent: **2026-10-17 17:14 UTC**.
- [x] Email confirmed: **2026-10-17 20:14 UTC**.
- [x] Password sign-in succeeded: **2026-10-17 21:06 UTC**.
- [x] Test account was visible in Supabase `auth.users`.
- Password recovery: Initial attempt blocked by HTTP 429 rate limit (Supabase default limit is 2 emails/hour). After the rate limit reset, Diyar tested the full recovery flow successfully in the frontend. To address email delivery limits for production, the team plans to configure a custom SMTP provider once a verified sending domain is available. Custom SMTP lets the project configure sending limits; it does not remove limits entirely. SMTP setup is not required for BE-01 and is a separate future task.
- [x] Sign-out succeeded in Diyar's frontend test; no timestamp was recorded.
- [ ] FastAPI bearer-token verification and protected backend session handling: **pending BE-02**.

Diyar’s successful frontend Auth tests were performed on his separate frontend branch, which has not yet been merged into `main`. They cover signup, confirmation, login, password recovery, and sign-out. FastAPI JWT verification and protected backend session handling remain BE-02 deliverables and are not claimed as complete.

