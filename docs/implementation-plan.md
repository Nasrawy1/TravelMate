# TravelMate — Implementation Plan

**Status:** Proposed for review; no GitHub issues or Project fields have been changed.
**Date:** 2026-10-14
**Baseline:** architecture v1.2, scope v1.3, API wire schema v0.3, database v0.2.

## Priorities and ownership

P0 unlocks work or resolves feasibility. P1 delivers the mandatory MVP. P2 is optional after core acceptance. Priorities below are proposals, not observed Project statuses. Existing issue assignees are preserved. New task codes are local proposals, not assigned GitHub issue numbers.

| Owner | Account | First deliverable | Collaboration |
|---|---|---|---|
| Nasrawy | Nasrawy1 | Reviewed scope/contracts + shared fixtures | All owners; reviews integration |
| Ali | aliyousifalqudsi-bot | Core wireframes, then incremental UI designs | Diyar + Nasrawy |
| Diyar | dyarraed | React setup and fixture-driven screens | Ali for UI; Adel for Auth/API |
| Adel | AdelbahaMattar | FastAPI foundation + Supabase Auth environment | Diyar for Auth; Ziyad for adapters |
| Ziyad | zee0x | AI evidence + real-price provider feasibility | Adel for schemas; Nasrawy for provider decision |

## Work sequence

1. Start #10/#11 review, #3 wireframes, #12 React setup, BE-00/#7 backend/Auth setup, and #4/#5 feasibility in parallel. Review the reported #2 completion evidence rather than repeating completed research.
2. Within the first two integration working days, choose one viable travel category and document supported searches. Escalate if neither works; never silently weaken F-08A.
3. Ali releases approved screens one at a time. Diyar builds with fixtures; Adel implements auth/schemas/budget; Ziyad implements AI and the selected travel adapter after agreeing the boundary.
4. Combine the protected real generation endpoint with the UI, then verify failure paths, explicit offline demo and second-computer handover.
5. Optional F09 and API-06 start only after core acceptance and explicit prioritization.

## Collaboration rules

- One implementation owner per task; collaborators review interfaces rather than editing the same module without coordination.
- Adel owns routes, auth verification, trip orchestration and budgets; Ziyad owns provider adapters. Agree Python input/output shapes before coding them independently.
- Diyar owns frontend code; Ali owns Figma. Wireframes and setup can proceed together; full high-fidelity design is not a setup blocker.
- Small PRs linked to issues; Nasrawy reviews. Mock-based checks may precede live integration but never prove live pricing.
- This plan assigns no board status: the Project columns were not available through the connector.

## Existing issue replacements

The sections below are proposed title/body replacements for review. Preserve assignees, labels, state and existing discussion unless separately approved. For #2, retain all existing completed checklist items and append the evidence-review section; no checkbox or state reset.

### #1: PLAN-00: Track MVP Foundations

**Owner:** Nasrawy1  
**Proposed priority:** P0  
**Start:** Tracking only; not an additional implementation task

**Tasks**

- [ ] Track #10 and #11 as the authoritative planning tasks.
- [ ] Link accepted documentation and provider feasibility evidence.
- [ ] Remove duplicated architecture/API work from this issue.

**Acceptance**

- [ ] #10 and #11 have reviewed deliverables; remaining provider decisions are explicit.

**Dependencies:** #10, #11

### #2: API-01: Research & Test AI API

**Owner:** zee0x  
**Proposed priority:** P0  
**Start:** Review reported completed research

**Tasks**

- [ ] Preserve the existing completed research checklist.
- [ ] Attach the provider/model, sanitized request and structured output, measured latency, observed cost/limits and recommendation.
- [ ] Compare the sample with API v0.3: complete nights + 1 itinerary; no invented live travel offers.
- [ ] Team lead reviews evidence before changing issue state.

**Acceptance**

- [ ] Evidence is linked and compatible with the contract; no repeated research required if existing evidence is adequate.

**Dependencies:** None

### #3: DES-01: Create Core User Flow & Wireframes

**Owner:** aliyousifalqudsi-bot  
**Proposed priority:** P0  
**Start:** Start now

**Tasks**

- [ ] Design online sign-in → trip form → loading → results/error/retry.
- [ ] Design a separate offline-demo entry and selection of 2–3 predefined trips.
- [ ] Use 1–4 adults, 1–7 nights, USD whole-group budget and supported-city selections.
- [ ] Show unknown prices, warnings, selected offers and three budget statuses.
- [ ] Review incrementally with Diyar and the team lead; exclude booking/checkout and defer saved-trip screens.

**Acceptance**

- [ ] Figma flow covers core states; Diyar can begin one approved screen without waiting for the whole set.

**Dependencies:** #10 and #11 candidate docs

### #4: API-02: Evaluate Flight Price Provider Feasibility

**Owner:** zee0x  
**Proposed priority:** P0  
**Start:** Start feasibility now

**Tasks**

- [ ] Check access, permitted use, cost/limits and whether prices are real versus fixed sandbox fixtures.
- [ ] Construct searches from supported cities, dates and adult count.
- [ ] Record round-trip/all-adult coverage, currency, source and retrieval time.
- [ ] Test two distinct input combinations where feasible and preserve sanitized evidence.
- [ ] Compare with #5; recommend one mandatory provider with team lead and Adel within the first two integration working days.

**Acceptance**

- [ ] Document actual outcome and limitations; a viable provider has at least one real-priced result. An unsuccessful candidate may be ruled out, but does not satisfy F-08A.

**Dependencies:** None; coordinate #5

### #5: API-03: Evaluate Hotel Price Provider Feasibility

**Owner:** zee0x  
**Proposed priority:** P0  
**Start:** Start feasibility now

**Tasks**

- [ ] Evaluate Agoda access and alternatives without assuming partner access.
- [ ] Check permitted use, limits/cost and real price availability.
- [ ] Test dates, destination and occupancy; verify full-stay/all-adult coverage and room count where needed.
- [ ] Record currency, source, timestamp and sanitized output; distinguish fixed test data from real offers.
- [ ] Compare with #4 and prioritize the first viable category; escalate if neither is feasible.

**Acceptance**

- [ ] Document actual outcome and limitations; chosen category supplies at least one real price and a second distinct supported query where feasible.

**Dependencies:** None; coordinate #4

### #6: DES-02: Design Core MVP Screens & States

**Owner:** aliyousifalqudsi-bot  
**Proposed priority:** P1  
**Start:** After each approved wireframe

**Tasks**

- [ ] Define small reusable color/type/spacing/button/form/card styles.
- [ ] Deliver auth, input, results, loading, errors and offline-demo screens incrementally.
- [ ] Specify price origin, missing-data labels, selected-offer highlighting and budget states.
- [ ] Show laptop/desktop responsive behavior; defer booking and saved-trip UI.

**Acceptance**

- [ ] Diyar has usable Figma specifications and assets for all mandatory states; team lead reviews.

**Dependencies:** #3 per screen; not all screens at once

### #7: BE-01: Configure Supabase Auth Environment

**Owner:** AdelbahaMattar  
**Proposed priority:** P0  
**Start:** Start now

**Tasks**

- [ ] Create/configure a dedicated development Supabase project.
- [ ] Configure email/password Auth, local redirect settings and document signup/email-confirmation behavior.
- [ ] Document frontend public URL/key and backend token-verification configuration using placeholders.
- [ ] Coordinate access with Diyar without committing secrets.
- [ ] Do not create profiles, travel_requests, itineraries or trips tables for core setup; F-09 migration is deferred.

**Acceptance**

- [ ] The project is available for Auth integration; safe environment instructions exist; no application-table dependency blocks core generation.

**Dependencies:** #10 candidate stack

### #8: BE-02: Integrate Supabase Auth & Verify Backend Tokens

**Owner:** AdelbahaMattar  
**Proposed priority:** P1  
**Start:** After Auth and app foundations

**Tasks**

- [ ] Diyar owns React signup/signin/signout/session forms; Adel owns FastAPI token verification.
- [ ] Verify signature, expiration and issuer/audience as appropriate; derive identity from verified token.
- [ ] Require bearer authentication on generation; map invalid/missing/expired token to common 401 envelope.
- [ ] Document session refresh/expiry behavior and verify with Diyar using multiple accounts.
- [ ] Offline demo is client-only; do not add a server-side authentication bypass.

**Acceptance**

- [ ] Online signup/login/logout work; protected calls reject invalid tokens; no duplicate FastAPI login/signup routes or unnecessary tables.

**Dependencies:** #7, #12, BE-00

### #9: BE-03: Implement Generate Trip Endpoint

**Owner:** AdelbahaMattar  
**Proposed priority:** P1  
**Start:** Build schemas first; integrate after dependencies

**Tasks**

- [ ] Implement POST /api/v1/trips/generate using API v0.3 request fields and validation.
- [ ] Enforce supported locations, future dates, 1–7 nights, 1–4 adults and positive whole-trip USD budget.
- [ ] Verify bearer token, orchestrate normalized travel and AI adapters, then call the budget service.
- [ ] Return 200 only for a complete validated itinerary covering nights + 1 dates.
- [ ] Use independent price/budget states and common error envelope/request_id; enforce bounded deadlines.
- [ ] Never persist generation, require a trips table, or return a persisted trip ID.

**Acceptance**

- [ ] Core contract and error/auth cases pass; actual generation integrates real AI and chosen live travel adapter; unavailable prices remain explicit.

**Dependencies:** #11 baseline, #8, API-04, API-05, BE-04; scaffold/schema work can start after BE-00

### #10: PLAN-01: Align MVP Scope & Architecture

**Owner:** Nasrawy1  
**Proposed priority:** P0  
**Start:** Start now

**Tasks**

- [ ] Review architecture v1.2 and scope v1.3 with team.
- [ ] Confirm React/Vite + FastAPI + Supabase Auth and mandatory AI/one-live-provider flow.
- [ ] Keep second provider and saving optional; defer booking UI.
- [ ] Confirm client-only offline demo and local handover requirements.
- [ ] Link the reviewed docs; do not label provider feasibility complete without evidence.

**Acceptance**

- [ ] Core boundaries and owners are understood; provider gate and deferred scope are explicit.

**Dependencies:** None

### #11: PLAN-02: Review API v0.3 & Shared Fixtures

**Owner:** Nasrawy1  
**Proposed priority:** P0  
**Start:** Start now; final provider sign-off after feasibility

**Tasks**

- [ ] Use canonical docs/api-contracts.md; confirm public snake_case request/response/error schemas.
- [ ] Agree normalized adapter boundary with Adel and Ziyad and UI fixtures with Diyar.
- [ ] Provide structural fixtures for live-price-shaped results, no-price results, over-budget and errors; mark mocks visibly in development.
- [ ] Keep separate offline-demo wrapper/metadata; fixture data never counts as live evidence.
- [ ] Record pending provider/city list, estimates, offer selection and measured deadlines; approve integration baseline after feasibility.

**Acceptance**

- [ ] Core contract is shared; fixtures validate against it; unresolved choices are documented; F-09 payloads remain deferred.

**Dependencies:** #10; #4/#5 for final supported searches

### #12: FE-01: Initialize React + Vite Frontend

**Owner:** dyarraed  
**Proposed priority:** P0  
**Start:** Start now

**Tasks**

- [ ] Initialize React/Vite folder structure and routes for core journey and offline demo.
- [ ] Prepare pages, components, services, assets and local fixture folders.
- [ ] Add placeholder-only .env.example; keep secrets and service-role keys out of VITE variables.
- [ ] Set up API client conventions, loading/error handling foundation and shared styles with Ali.
- [ ] Document installation/start commands that actually work and submit a small PR.

**Acceptance**

- [ ] Frontend runs locally; routes work; no secret credentials; mock response can be rendered without completed backend.

**Dependencies:** #10 candidate stack; coordinate #3

## New implementation issues proposed

### BE-00: Initialize FastAPI Backend

**Owner:** AdelbahaMattar  
**Proposed priority:** P0  
**Start:** Start alongside frontend

**Tasks**

- [ ] Set up modular FastAPI structure: routes/schemas, auth, services and adapters.
- [ ] Add GET /api/v1/health, explicit local CORS origins, sanitized logging and common exception envelope with request_id.
- [ ] Document pinned/tested dependency installation, startup and placeholder-only environment settings.

**Acceptance**

- [ ] Health endpoint works locally; no secret committed; Diyar can call backend from local frontend.

**Dependencies:** #10

### API-04: Implement AI Adapter

**Owner:** zee0x  
**Proposed priority:** P1  
**Start:** After evidence and adapter agreement

**Tasks**

- [ ] Implement real provider call with validated structured output.
- [ ] Accept normalized trip/travel context; return complete itinerary for every date.
- [ ] Keep keys server-side, validate output and map failure/timeout; do not auto-retry chargeable AI generation.

**Acceptance**

- [ ] Real AI produces a valid itinerary; invalid/incomplete output fails safely; no invented provider prices.

**Dependencies:** #2 evidence, #11, BE-00

### API-05: Implement Mandatory Live Travel Adapter

**Owner:** zee0x  
**Proposed priority:** P1  
**Start:** After selecting one feasible provider

**Tasks**

- [ ] Implement dynamic supported searches for the chosen flight OR hotel provider.
- [ ] Normalize USD prices, coverage/occupancy, offer IDs, source and retrieved_at.
- [ ] Implement no-results/error mapping and bounded timeout/retry.
- [ ] Document actual price evidence and two distinct supported searches where feasible.

**Acceptance**

- [ ] At least one genuine search-relevant real-priced result; mocks/sandbox fixed examples do not count; missing prices remain unavailable.

**Dependencies:** #4/#5 provider decision, #11, BE-00

### BE-04: Implement Deterministic Budget Assessment

**Owner:** AdelbahaMattar  
**Proposed priority:** P1  
**Start:** Can use normalized fixtures before adapters finish

**Tasks**

- [ ] Select one eligible comparable offer per category using the reviewed rule; expose selected IDs.
- [ ] Compute provider and estimate subtotals once, without duplicated fees.
- [ ] Use null for missing total and report missing categories; reliable known minimum over budget takes precedence.
- [ ] Cover within_budget, over_budget, uncertain and no-offer cases.

**Acceptance**

- [ ] All arithmetic is backend-owned; referenced offers exist; unknown never becomes zero; whole-trip/all-adult coverage is enforced.

**Dependencies:** #11 cost/selection agreement, BE-00

### FE-02: Implement Core Forms, Auth UI & Results

**Owner:** dyarraed  
**Proposed priority:** P1  
**Start:** Implement incrementally with fixtures

**Tasks**

- [ ] Implement auth UI jointly with Adel under #8.
- [ ] Build trip form with supported-location choices and contract validation.
- [ ] Render complete itinerary, source/time/coverage, selected offers, missing costs and budget states.
- [ ] Implement loading, prevent duplicate submits, show safe errors/retry and handle session expiry.

**Acceptance**

- [ ] Core screens work with agreed fixtures and then actual API; no independent budget/offer selection contradicts backend.

**Dependencies:** #12, #3/#6 per screen, #11; #8/#9 for live integration

### FE-03: Implement Explicit Offline Demo

**Owner:** dyarraed  
**Proposed priority:** P1  
**Start:** Parallel with results UI

**Tasks**

- [ ] Bundle 2–3 complete predefined sample trips with visible DEMO identification.
- [ ] Use the same result components with explicit demo context; prevent fixture fields being presented as real live evidence.
- [ ] Allow offline access without backend generation, Supabase SDK network activity or saving.
- [ ] Lazy-initialize online auth/services only when online flow is selected.

**Acceptance**

- [ ] All demo cases run with network disabled after local dependencies/assets are installed; no online sign-in or provider requests.

**Dependencies:** #12, FE-02 result components; #3/#6 demo design

### QA-01: Verify Core End-to-End Acceptance

**Owner:** Nasrawy1  
**Proposed priority:** P1  
**Start:** Prepare checklist now; execute incrementally

**Tasks**

- [ ] With Adel/Diyar/Ziyad, test real sign-in → form → AI + selected live provider → results.
- [ ] Verify auth/input errors, invalid AI output, deadlines, missing prices, budget outcomes and double-submit prevention.
- [ ] Test offline demo without network; capture sanitized live-provider evidence separately.
- [ ] Record failures and fixes; do not mark optional saving as mandatory.

**Acceptance**

- [ ] Mandatory scope checklist passes with evidence; known failures and open provider constraints are explicit.

**Dependencies:** #8/#9, API-04/API-05, BE-04, FE-02/FE-03

### OPS-01: Package Local Startup & Second-Computer Handover

**Owner:** Nasrawy1  
**Proposed priority:** P1  
**Start:** Prepare during setup; verify before delivery

**Tasks**

- [ ] Agree supported evaluator OS; add startup script(s) for implemented frontend/backend.
- [ ] Document tested prerequisites, dependency installation, environment configuration, ports and troubleshooting.
- [ ] Separate internet-dependent online operation from offline demo; explain initial dependency installation requirement.
- [ ] Test on a second computer; use dedicated demo credentials securely and never package production secrets.

**Acceptance**

- [ ] A teammate can follow README for online and offline-demo runs on a second computer; commands/scripts are actually tested.

**Dependencies:** #12, BE-00; final validation after QA-01 fixes

### F09: Implement Optional Saved Trips

**Owner:** AdelbahaMattar  
**Proposed priority:** P2  
**Start:** Deferred until core passes and feature approved

**Tasks**

- [ ] Finalize HTTP models with Diyar before implementation.
- [ ] Review and execute one public.trips migration in a test project.
- [ ] Implement explicit save/list/reopen through FastAPI only, with verified owner filtering, size/schema validation and historical/unverified labels.
- [ ] Test cross-user isolation and denial of browser Data API access; no update/delete endpoints.

**Acceptance**

- [ ] Only if approved: documented schema/permission/ownership tests pass; generation remains independent.

**Dependencies:** Core acceptance, explicit F-09 prioritization, agreed HTTP schemas; Diyar handles optional UI

### API-06: Implement Optional Second Travel Provider

**Owner:** zee0x  
**Proposed priority:** P2  
**Start:** Deferred until core passes

**Tasks**

- [ ] Implement the other travel category using the same normalized interface and provenance rules.
- [ ] Retest budget selection and missing-category handling with both providers.

**Acceptance**

- [ ] Second provider supplies genuine supported prices without delaying core delivery.

**Dependencies:** QA-01 core pass and explicit prioritization

## Approval and publication boundary

This is a local review package. No commits, remote branches, PRs, issue updates or Project mutations have been made. After user approval, re-read current GitHub files/issues and reconcile any newer team changes before publishing. The canonical rename must add docs/api-contracts.md and remove docs/api-contracts (2).md together. Do not close #2 without evidence review or mark tasks Done merely because documentation exists. F-09 migration execution is not authorized by this documentation review.

