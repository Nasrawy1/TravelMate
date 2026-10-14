# TravelMate — System Architecture

**Version:** 1.2 (Scope and contract alignment)  
**Status:** Review candidate — pending team-lead approval and provider feasibility  
**Project:** TravelMate Graduation Project

## 1. Overview

TravelMate is an AI-powered travel-planning web application. A user enters departure and destination locations, travel dates, passenger count, and a total budget. The system obtains available flight and hotel data, asks an AI provider to propose a day-by-day itinerary, and presents a cost breakdown with clear distinctions between live prices and estimates.

The MVP prioritizes a working end-to-end journey over advanced features. It runs as a **local web application** on the evaluator's computer, while real Supabase and external API integrations require internet access.

**Companion documents:** [MVP scope](mvp-scope.md) defines priorities; [API contracts](api-contracts.md) defines wire formats; [database schema](database-schema.md) defines optional storage. [Implementation plan](implementation-plan.md) defines ownership and dependencies. This revision aligns these documents; it does not claim that implementation or provider feasibility has been completed.

**Minimum delivery:** Supabase Auth + real AI generation + at least one live flight OR hotel price integration + budget assessment + offline demo. Saving trips and the second travel integration are optional. Generation does not write to the database.

## 2. Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | React + Vite | Forms, authentication UI, trip results; optional saved trips |
| Backend | Python + FastAPI | REST endpoints, validation, orchestration, cost checks |
| Authentication | Supabase Auth | Account sign-up, sign-in, session management |
| Database (F-09 only) | Supabase PostgreSQL (Free Tier) | Optional explicit save/list/reopen using one `public.trips` table |
| AI | External AI API (provider TBD) | Generate proposed day-by-day itineraries |
| Travel data | One mandatory flight OR hotel API; second optional (providers TBD) | Retrieve verified, input-dependent price data |
| UI/UX | Figma | Wireframes and screen designs |
| Collaboration | GitHub + GitHub Projects | Version control, issues, review and task tracking |

API provider choices remain **unconfirmed** until feasibility testing verifies access, coverage, limits, and pricing. The architecture must not depend on a particular provider.

## 3. Architectural Style and System Boundaries

TravelMate uses a **three-tier architecture** and a **modular monolith backend**: one React frontend, one FastAPI application, and external data/authentication services. Backend modules are logical code boundaries, **not separate deployable microservices**.

```text
                 User (browser)
                       |
                       v
                React + Vite UI
                  |         |
             REST/JSON   Supabase Auth SDK
                  |         |
                  v         v
              FastAPI   Supabase Auth
                  |
       +----------+-----------+--------------+
       |          |           |              |
       v          v           v              v
  Trip/Budget  AI adapter  Travel adapters  Database access
    logic         |        (flight/hotel)         |
                  v           v                  v
               AI API      Travel APIs    Supabase PostgreSQL
```

- The frontend talks to FastAPI for trip generation, retrieval, and saving.
- The frontend may use the Supabase client for sign-up, sign-in, and session handling.
- FastAPI validates Supabase access tokens on protected routes and enforces user ownership.
- External AI and travel API credentials remain on the backend; they must never be bundled in browser code.
- The database is the source of truth for **saved** trips. A newly generated trip is not automatically persisted.

## 4. Backend Modules and Responsibilities

| Module | Responsibility |
|---|---|
| API routes and schemas | REST routes, typed request/response models, validation and error responses |
| Auth/security | Verify access tokens and obtain authenticated user identity |
| Trip service | Coordinate input, external data, AI generation, validation, and saved-trip operations |
| Flight adapter | Convert selected flight provider responses into a consistent internal format |
| Hotel adapter | Convert selected hotel provider responses into a consistent internal format |
| AI adapter | Build prompts/request payloads and parse structured itinerary output |
| Budget service | Calculate estimated totals, missing costs, and budget status |
| Persistence layer | Read/write user-owned trips through Supabase PostgreSQL |
| Demo fixtures | Provide deterministic example inputs and outputs without live AI/travel API calls |

Adapters isolate third-party APIs so providers can be replaced without rewriting the frontend or trip service.

## 5. Core Trip Generation Flow

1. The user signs in and enters departure city, destination city, future start date, return date (1–7 nights), adult count (1–4), and whole-trip USD budget.
2. React submits the data as JSON to the FastAPI trip-generation endpoint with the user's access token.
3. FastAPI verifies the token and validates the request (required fields, positive budget, valid dates, sensible passenger count).
4. The trip service requests the selected mandatory travel provider; it may also query the second provider if implemented. Queries use actual supported user inputs. Missing offers are represented as unavailable, never replaced by fictitious live prices.
5. Normalized travel options, budget constraints, trip dates, and user inputs are supplied to the AI adapter to generate a structured day-by-day itinerary.
6. FastAPI validates the generated structure and calculates the cost breakdown. The backend—not the AI's unsupported claims—determines whether the known costs fit the budget.
7. FastAPI returns the itinerary, travel options, price metadata, total known/estimated cost, budget status, and any missing-data warnings.
8. React renders the results. Generation does not persist a trip or return a persisted trip ID. Explicit saving is available only if optional F-09 is implemented.

**Budget rule:** Do not label a trip as “within budget” unless the relevant total is sufficiently accounted for. If material costs are missing, set `budget.status` to `uncertain` unless the reliable known minimum already proves `over_budget`. HTTP 200 still requires `generation_status: complete` and an itinerary covering all `nights + 1` dates. If the known cost exceeds the budget, show **over budget** and offer retry/adjustment rather than silently pretending the plan fits.

**Pricing rule:** Every price displayed as live must originate from an external provider and carry its source and retrieval time. Normalize flight quotes to the round trip for all adults and hotel quotes to all nights with verified occupancy. AI-suggested activity costs and other unverified amounts must be labeled **estimates**. Live travel prices are time-sensitive and are not booking guarantees.

## 6. Authentication, Authorization and Storage

- Supabase Auth handles sign-up, sign-in, and sessions from the frontend.
- Protected FastAPI routes require a valid Supabase access token, which the backend independently verifies.
- Saved trips reference the authenticated user's Supabase user ID as their owner.
- F-09 uses one `public.trips` table only. React uses Supabase Auth but never the Supabase Data API for application tables. FastAPI uses a separate server-only elevated client; its queries bypass RLS, so explicit verified `user_id` filters enforce ownership. Browser roles have no table privileges; RLS remains enabled. See the schema for the exact grants and tests.
- Do not create `profiles`, `travel_requests`, or `itineraries` tables. Supabase Auth and core generation do not depend on the optional migration.
- Saved snapshots are validated user-submitted historical copies, not verified live-price evidence; label them saved/unverified and potentially outdated.
- Database administrator/service-role credentials, if used, are kept exclusively in backend environment variables; they bypass RLS and must not be exposed to the frontend.
- The frontend never accepts a client-supplied `user_id` as proof of ownership.
- The MVP stores only the information needed for saved trips; do not store API secrets or payment card data.

Detailed tables, relationships, and RLS policies belong in `database-schema.md`.

## 7. API Design Principles

- Interface: versioned REST endpoints under `/api/v1/` using JSON.
- FastAPI/Pydantic models define and validate request and response shapes.
- Required endpoints: `GET /api/v1/health` and protected `POST /api/v1/trips/generate`. Optional F-09 endpoints: create, list, and retrieve saved trips; their HTTP models must be agreed before implementation.
- Authentication endpoints are provided by Supabase Auth, so duplicate custom login endpoints are unnecessary.
- Error responses use consistent machine-readable codes and user-safe messages.
- Generation returns a structured result with no persisted trip ID. All public fields use the snake_case API contract.
- Frontend development may use mock JSON matching the agreed contract before the backend integrations are ready.

Exact methods, paths, schemas, and example payloads belong in `api-contracts.md`. Once agreed, changes should be coordinated between frontend and backend owners.

## 8. Failure Handling and Demo Mode

| Situation | Expected MVP behavior |
|---|---|
| All providers available | Generate itinerary using available live travel data; clearly label estimates |
| Travel provider fails or has no results | Return 200 only if AI produces a complete valid itinerary; use `no_price`, unavailable categories and budget warnings as applicable |
| AI provider fails or returns invalid data | Return a clear error with a retry option; do not present fabricated live results |
| Rate limit, timeout, or invalid API credentials | Log a safe diagnostic on the backend and show an understandable user message |
| Budget cannot be verified | Return `uncertain` unless the reliable known minimum already exceeds budget; missing amounts stay null |
| Demo mode selected | Load 2–3 read-only frontend fixtures with a visible DEMO banner; no backend generation, online login, or provider calls |

**Demo mode is explicit**, never an invisible substitution for live results. A separate client entry loads bundled fixtures without Supabase login or network requests. This is not an authentication bypass on protected FastAPI endpoints. The normal authenticated flow still requires internet connectivity. Demo fixtures never satisfy the real-price acceptance gate.

## 9. Local Execution and Handover

The deliverable is runnable source code, not a deployed website.

Expected setup:

1. Install documented prerequisites (Python, Node.js/npm, and dependencies).
2. Configure `.env` files from `.env.example` without committing secrets.
3. Run a startup script that launches FastAPI and the Vite frontend locally.
4. Open the local URL in a browser and test the full user flow.
5. Select demo mode when external services or API credentials are unavailable.

The project README must include OS-specific launch instructions, the required environment variable names, troubleshooting notes, and sample demo credentials/steps where applicable. Test the handover on a **second computer** before submission.

## 10. Security, Reliability, and Constraints

- Keep third-party secrets server-side and out of Git history.
- Validate and sanitize input, enforce authorization on protected operations, and restrict CORS to expected local origins.
- Use request timeouts and bounded retries for third-party services; avoid repeated requests that exhaust free quotas.
- Validate AI-generated JSON before processing or displaying it.
- Record useful non-sensitive errors for debugging; avoid logging tokens or personal secrets.
- Supabase Free Tier and external API free tiers have quotas, availability constraints, and may change. Feasibility testing must confirm they are adequate.
- No real payment processing or booking confirmation is included in the MVP. Any payment UI, if later added for demonstration, must be clearly marked simulated.

## 11. Team Responsibilities

| Owner | Initial responsibility |
|---|---|
| Team Lead | Architecture, repository/project board, contracts, integration and acceptance testing |
| Ali | Figma wireframes, screen flows and UI/UX specifications |
| Diyar | React frontend, screens, authentication UI and consuming API contracts |
| Adel | FastAPI backend, Supabase Auth integration, database and protected endpoints |
| Ziyad | Feasibility tests and implementation of AI, flight and hotel API adapters |

Work can proceed in parallel using agreed mock responses and shared contracts.

## 12. Remaining Decisions and Delivery Order

Resolved by companion documents: snake_case request/response schemas, separate client-only offline demo, generation without persistence, and backend-only optional storage.

Still pending:

- Confirm AI provider evidence and choose the mandatory real-price provider.
- Verify supported cities/routes and currency/occupancy coverage.
- Agree estimation policy for food, local transport and activities; missing categories remain explicit.
- Confirm the provisional cheapest-eligible-offer selection rule and tune timeouts using measured tests.
- Define saved-trip HTTP payloads only when F-09 is prioritized.

Delivery order:

1. Review contracts, start provider feasibility, frontend setup, backend setup and wireframes in parallel.
2. Integrate Supabase Auth and build UI against fixtures while adapters are implemented.
3. Deliver the real AI + one live-price end-to-end flow and deterministic budget calculation.
4. Verify failure handling, offline fixtures and second-computer startup.
5. Consider F-09 and the second live provider only after the core acceptance gate.

Provider feasibility is a gate for claiming the final baseline and live-price acceptance; it does not block setup or mock-based UI work. Full task proposals are in [implementation-plan.md](implementation-plan.md).

---

**Architecture principle:** Build the smallest secure, testable end-to-end travel-planning experience first; add complexity only when the MVP demonstrates a real need.

