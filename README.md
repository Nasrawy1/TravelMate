# TravelMate

AI-assisted travel planning — graduation project.

**Current state:** Documentation and implementation planning. The reviewed main snapshot contains README and docs only; the runnable frontend/backend and launch scripts are not yet delivered. This documentation update does not claim working software or verified provider integrations.

## Documentation

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

Implementation owners must add tested prerequisites, install/run commands, safe .env.example files and startup script(s) as the application is built. Do not assume a launch command exists yet. Document first-time dependency installation separately from offline runtime, and verify both online and demo operation on a second computer before submission.

Keep API keys and elevated Supabase credentials server-side and outside Git. Never put secrets in VITE-prefixed variables. Use a dedicated non-production Supabase project.

## Review status

Documentation is a review candidate, not evidence of team approval or provider feasibility. Pending: AI evidence, mandatory live provider and supported searches, estimation/conversion policy, offer selection confirmation and measured timeout tuning. See the implementation plan for ownership.

