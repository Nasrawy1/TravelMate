# TravelMate — MVP Scope

**Version:** 1.0 (Proposed)  
**Status:** Draft — team review required  
**Project:** TravelMate Graduation Project  
**Related:** `architecture.md`, `api-contracts.md`, `database-schema.md`

## 1. MVP Objective

Build a locally runnable web application that lets a user enter trip details and receive an AI-generated, day-by-day travel plan with a transparent budget breakdown. Where supported, the plan includes externally sourced flight and hotel options. The evaluator must be able to complete a dependable end-to-end demonstration.

**Primary success scenario:** Sign in → enter trip details → generate a plan → review the itinerary and costs. Saving and reopening the generated trip is a secondary goal.

## 2. Target User and Scope Boundary

- **Target user:** An individual planning one trip for themselves or a small group.
- **Trip format:** One departure location, one destination, one date range, one total trip budget.
- **Platform:** Desktop-friendly responsive web application running locally in a browser.
- **Delivery:** Source code and launch instructions; **no public deployment** required.
- **Bookings and payments:** No real bookings or payments in the MVP.

## 3. Functional Requirements and Priorities

| ID | Feature | Priority | Expected MVP behavior |
|---|---|---|---|
| F-01 | User authentication | Must Have | Sign up, sign in, and sign out using Supabase Auth in normal online mode. |
| F-02 | Trip input form | Must Have | Collect departure, destination, departure/start date, return/end date, passenger count, total budget, and currency. |
| F-03 | Input validation | Must Have | Reject missing or inconsistent values and show understandable errors. |
| F-04 | AI itinerary generation | Must Have | Produce a structured day-by-day plan using the submitted trip details. |
| F-05 | Trip results page | Must Have | Display dates, daily activities, available travel options, budget breakdown, and data warnings. |
| F-06 | Budget assessment | Must Have | Calculate known/estimated costs and label budget status without hiding missing amounts. |
| F-07 | Demo mode | Must Have | Provide a clearly labeled, deterministic sample journey independent of external AI/travel APIs. |
| F-08 | Flight and hotel price integrations | Target for MVP; feasibility gate | Query real providers for selected supported searches and display provider-sourced results; confirm achievable access before making this a delivery dependency. |
| F-09 | Save and reopen trips | Should Have | Authenticated users can explicitly save, list, and reopen their own generated plans. |
| F-10 | Basic retry/error handling | Must Have | Show meaningful errors, partial-data warnings, and retry where appropriate. |

**Priority definitions:** Must Have = required to demonstrate the core flow; Should Have = implement after the core works; Feasibility gate = confirm availability, limits, and legal/technical access before committing to delivery. If price APIs cannot be used, the team must explicitly approve a scope change rather than present simulated prices as live.

## 4. Trip Input — Minimum Fields

| Field | Example | Validation |
|---|---|---|
| Departure | Istanbul | Non-empty supported city/location |
| Destination | Rome | Non-empty supported city/location; distinct from departure |
| Start date | 2026-11-10 | Valid future date |
| End date | 2026-11-15 | After start date |
| Passengers | 2 | Positive integer; initial supported limit to be agreed |
| Total budget | 1500 | Positive number |
| Currency | USD | Currency supported by the cost-calculation rules |

**Not required in v1:** Passport details, traveler names, preferences questionnaire, multi-destination routes, or payment details.

## 5. Minimum Successful Trip Result

A generated result counts as **successful** only if it:

1. Matches the submitted destination and travel dates.
2. Provides a structured daily itinerary for the trip dates, with meaningful activities for each day.
3. Displays the available flight and hotel options **or clearly explains why they are unavailable**.
4. Shows a budget breakdown and labels each amount by its source/type: provider price, estimate, or unavailable.
5. States whether the budget is `within_budget`, `over_budget`, or `uncertain`; it must not claim a fit when material costs are missing.
6. Presents the result in the UI without requiring the user to inspect raw JSON.

A successful **live-priced** result additionally contains provider metadata and retrieval times for the prices actually received from travel providers. An AI-generated number must never be labeled a live price.

## 6. Budget Scope and Rules

The total user budget applies to **the whole trip and all passengers**, not per person or per night.

| Cost category | MVP treatment |
|---|---|
| Round-trip flights | Use provider prices if available; otherwise mark missing or estimated (never live). |
| Accommodation | Use quote for relevant dates and occupancy when available; otherwise mark missing or estimated. |
| Activities / attractions | Show estimates only when grounded enough to be useful; label as estimated. |
| Food and local transport | May be represented by explicitly labeled estimates; otherwise list as not included/unknown. |
| Taxes, fees, currency conversion | Include if returned by provider; disclose unknowns. Currency conversion method must be decided before mixing currencies. |

The backend, not the AI, computes totals and budget status. If costs are incomplete, show known totals separately from estimates and use `uncertain` when a reliable full-budget comparison is impossible.

## 7. Core User Journey

1. The user opens TravelMate and signs in (normal mode).
2. The user completes the trip form and presses **Generate Trip**.
3. The frontend shows a loading state while FastAPI validates and processes the request.
4. The backend requests available travel prices and generates an AI itinerary.
5. The backend validates the result and computes budget totals/status.
6. The user sees the plan, source labels, warnings, and budget assessment.
7. If the Should Have scope is completed, the user can **Save Trip** and reopen it later.

## 8. Failure Handling and Demo Behavior

- **No flight/hotel results:** Show a partial itinerary where meaningful, with explicit missing-data notices.
- **AI generation error or invalid output:** Show a clear error and allow the user to retry; do not invent successful live results.
- **Provider timeout / quota / authentication error:** Handle gracefully and show a user-safe message.
- **Demo mode:** Show sample inputs and predetermined sample output marked `DEMO`; do not call live AI, flight, or hotel APIs.
- **Offline presentation:** A fully offline demo may bypass hosted Supabase login through a separate read-only demo flow. This is not a replacement for normal authentication and must not pretend to be a real account.

## 9. Out of Scope for MVP

- Actual flight/hotel booking or payment processing.
- Payment gateway; if displayed later, only a clearly labeled simulation.
- AI chat assistant or conversational itinerary editing.
- Real-time route navigation, GPS, and maps integration.
- Multi-city/multi-country itinerary optimization.
- Recommendation engine based on user history.
- Social features, sharing accounts, reviews, or an admin dashboard.
- Native Android/iOS apps and public production deployment.

## 10. Non-Functional and Handover Requirements

- **Reliability:** Support a repeatable end-to-end demo even when external integrations cannot be accessed.
- **Security:** Keep secret API keys server-side; authenticate protected operations; isolate saved trips per user.
- **Clarity:** Clearly separate actual provider-sourced prices, estimates, and missing costs.
- **Maintainability:** Frontend and backend follow the agreed API contracts; third-party services use adapters.
- **Local run:** Provide `README.md`, `.env.example`, and a documented launch script/instructions for the evaluator's computer.
- **Testing:** Verify the happy path, invalid input, AI error, missing travel data, and demo mode. Test the launch instructions on another machine.

## 11. MVP Acceptance Checklist

- [ ] The app launches locally using documented instructions.
- [ ] Normal online sign-up/sign-in/sign-out works with Supabase Auth.
- [ ] Trip form captures and validates all minimum fields.
- [ ] A valid request produces a structured daily itinerary using a real AI API.
- [ ] Results page shows itinerary, costs, statuses, and warnings.
- [ ] Backend performs budget calculations; missing costs are not hidden.
- [ ] Failure and retry states are understandable.
- [ ] Demo mode displays a complete labeled sample trip without live AI/travel calls.
- [ ] Travel API feasibility has been tested and the team has documented whether live flight/hotel integration is part of the final acceptance gate.
- [ ] Normal-mode protected data cannot be read by another user.
- [ ] App was successfully tested on a second computer before submission.

### Secondary Acceptance (Should Have)

- [ ] Signed-in users can explicitly save a generated plan.
- [ ] Signed-in users can list and reopen only their own saved plans.

## 12. Decisions Required Before Implementation

1. **Travel API feasibility:** Which providers cover the intended routes/dates, and are sandbox/free credentials available? Confirm whether both live integrations can be mandatory.
2. **Passenger limit:** What is the maximum passenger count supported in v1?
3. **Currencies:** One display currency initially, or conversion support? If converting, what exchange-rate source?
4. **Activity estimates:** Are food, local transportation, and attraction costs required or optional estimates?
5. **Demo authentication:** Read-only guest demo or a different local demonstration path?
6. **Result storage:** Whether/how much of external price snapshots should be saved with trips.

**Scope rule:** A new feature enters the MVP only if it is required for the core end-to-end experience or explicitly approved by the team after evaluating its time and integration cost.
