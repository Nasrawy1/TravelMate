# TravelMate

AI-assisted travel planning — graduation project.

**Current state:** The local frontend includes the React/Vite foundation and Riviera Welcome, Login, Signup, Forgot Password and Reset Password UI. Trip Planner, Results and Offline Demo remain placeholders. Supabase Auth, FastAPI and live provider integrations are not connected; no working authentication or trip generation is claimed.

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

## Authentication Configuration

Authentication provider: Supabase Auth
Sign-in method: Email and password
Email confirmation: Enabled. Users must confirm their email before signing in.

### Local URLs

Site URL: `http://localhost:5173`

Allowed redirect URLs:

- `http://localhost:5173/**`
- `http://localhost:5173/reset-password`
- `http://127.0.0.1:5173/**`

The local frontend URLs were provided by Diyar for the React development setup.
Supabase's Site URL and allowed redirect URLs must match the frontend URLs used
during development.

### Environment Variables

Examples below use placeholders only. Real values are shared through an approved
private channel and kept in local, uncommitted `.env` files. Do not commit files
containing real project credentials.

Frontend environment example (`.env.example`):

```dotenv
VITE_SUPABASE_URL=https://<project-ref>.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=<your-supabase-publishable-key>