# TravelMate — MVP Scope

**Version:** 1.3 (Documentation and task alignment)  
**Status:** Scope baseline approved by team lead Nasrawy (Nasrawy1) on 2026-10-15; team acknowledgment and provider feasibility remain pending  
**Project:** TravelMate Graduation Project  
**Related documents:** `architecture.md`, `api-contracts.md`, `database-schema.md`

**PLAN-02 preparation update (2026-10-15):** [API contract v0.4](api-contracts.md), [internal adapter contracts](adapter-contracts.md), and [validated structural fixtures](fixtures/README.md) are now available as a review candidate. References below to v0.3 describe the preceding baseline; v0.4 adoption requires Diyar/Adel/Ziyad review and provider compatibility evidence. This update does not approve implementation, provider selection, or optional storage execution.

## 1. MVP Objective

Build a locally runnable, AI-powered travel-planning web application. A user signs in, enters trip details, and receives a structured day-by-day itinerary with a transparent trip-wide budget assessment. In normal online mode, the itinerary is generated through a real AI API and **at least one of the two travel categories (flights or hotels) must provide real provider-sourced price data** for a supported trip search.

The MVP emphasizes a reliable end-to-end experience over breadth. The application runs on the evaluator's computer; online authentication and live AI/travel APIs require internet access. A separate, clearly labeled offline demo remains available for presentation if external services fail.

**Primary success path:** Sign in -> enter trip details -> generate an AI itinerary -> retrieve at least one real flight/hotel price -> review the itinerary and budget breakdown.

**Secondary success path:** Save and reopen a generated plan, if time permits.

## 2. Fixed MVP Boundaries

| Area | Team-lead-approved v1.3 boundary |
|---|---|
| Target user | One individual planning a trip for themselves or a small adult group |
| Locations | One departure city and one destination city; supported locations only |
| Trip pattern | One round trip, one destination, one continuous hotel stay |
| Dates | Future start date; **1–7 nights**; end date is the return/departure date |
| Passengers | **1–4 adults**; children/infants excluded |
| Accommodation | A single hotel/property option for the stay, with occupancy and total cost appropriate for all travelers; do not assume one room fits four adults |
| Budget | One **total budget for all travelers and the whole trip**, not per person |
| Currency | **USD for budget input and displayed totals** in v1 |
| Platform | Desktop-friendly, responsive local web application (React + Vite and FastAPI) |
| Storage/auth | Supabase Auth for normal mode; Supabase PostgreSQL if saved trips are implemented |
| Deployment | No public deployment required; provide runnable code and launch instructions |
| Payments/bookings | No real booking, checkout, ticket issuance, or payments |

**Dates convention:** A trip of 3 nights runs from its start date through the return date 3 days later. The itinerary may describe arrival and departure days; it must not present the return date as an additional hotel night.

**Supported locations policy:** The v1 list of selectable departure/destination cities or routes must be based on the selected provider's verified geographic coverage, established during feasibility testing. The team documents which locations/search combinations it has tested. React should offer only supported choices (or clearly validate unsupported ones); FastAPI is the final authority on validation. Do not claim worldwide coverage. A search without live offers may still return a complete AI itinerary with transparently missing travel-price data, but cannot count as a successful live-price acceptance case.

## 3. Feature Scope and Priorities

| ID | Feature | Priority | Required behavior |
|---|---|---|---|
| F-01 | User authentication | Must Have | Sign up, sign in, sign out with Supabase Auth in normal online mode |
| F-02 | Trip input form | Must Have | Departure city, destination city, start date, return date, adult count, total budget; currency defaults to USD |
| F-03 | Input validation | Must Have | Reject invalid/missing fields, unsupported limits, and inconsistent dates with clear messages |
| F-04 | Real AI itinerary generation | Must Have | Generate a structured itinerary using a real AI API for valid normal-mode requests |
| F-05 | Results page | Must Have | Show day-by-day activities, travel-data availability, price labels, total/cost categories, and warnings |
| F-06 | Budget assessment | Must Have | Backend computes totals from normalized amounts; outputs `within_budget`, `over_budget`, or `uncertain` |
| F-07 | Offline demo mode | Must Have | Read-only, explicitly labeled sample trip experience without live AI, travel APIs, or hosted Supabase sign-in |
| F-08A | **At least one live travel-price integration** | **Must Have** | Successfully retrieve and display **real provider-sourced flight OR hotel prices** for an explicitly supported search; show source and retrieval time |
| F-08B | Second live travel-price integration | Should Have | Add the other category after the first works; missing category remains labeled estimate/unavailable, never passed off as live |
| F-09 | Save, list, and reopen trips | Should Have | Signed-in users explicitly save plans and retrieve only their own saved plans |
| F-10 | Failure and retry handling | Must Have | Loading, understandable errors, retry, partial-data states, and honest fallback labels |

**Definition of “live integration”:** A genuine request from the FastAPI backend to an authorized third-party travel-data service that returns data for the user's supported route/dates/occupancy. A static fixture, AI-invented price, hard-coded response, or provider's fixed mock/sandbox example **does not satisfy F-08A**. If a provider offers only test-mode access, the team must verify whether the returned data counts as real for project assessment before claiming acceptance.

**Decision B is a minimum, not a restriction:** Integrate both flight and hotel providers if feasible, but do not let the second integration delay delivery of the working core.

**Dynamic integration requirement:** The mandatory provider adapter must construct queries from actual user-entered supported locations, dates, and passenger count or hotel occupancy. It must not return one hard-coded route/date as if it were a dynamic live search. Verify at least two distinct supported input combinations when the provider offers sufficient coverage and data. Record requests, sanitized response evidence, and whether actual offers were returned; at least one successful real-price response is still mandatory.

## 4. Trip Input and Validation

| Field | Example | Rule |
|---|---|---|
| Departure city | Istanbul | Required; valid supported city, different from destination |
| Destination city | Rome | Required; valid supported city |
| Start date | 2026-11-10 | Required; future calendar date |
| Return date | 2026-11-15 | Required; later than start date; 1–7 nights total |
| Adult passengers | 2 | Required integer between 1 and 4 |
| Total trip budget | 1500 | Required positive number in USD |
| Currency | USD | Fixed to USD in v1; no currency-selection requirement |

**Not collected:** Passport numbers, payment information, traveler names, child ages, accessibility/preference questionnaires, or multiple destinations.

## 5. Minimum Successful Trip Result

A successful **normal-mode result** must:

1. Match the requested destination, date range, and adult count.
2. Contain a structured itinerary with meaningful activities for each relevant travel day, including sensible arrival/return-day handling.
3. Show **at least one real flight or hotel offer** for the supported acceptance-test search, sourced through the live integration, with provider name and retrieval timestamp. A supported search may return no offers at a particular moment; acceptance must use an agreed reproducible supported test case with actual available data.
4. Identify the other travel category as **provider-sourced**, **estimated**, or **unavailable**. Never silently replace missing live data with demo data.
5. Show an understandable trip-wide budget breakdown and its status: `within_budget`, `over_budget`, or `uncertain`.
6. Label all prices as provider-sourced, estimated, or unavailable; do not present provisional quotes as guaranteed bookable prices.
7. Render in the React UI, not only as raw JSON, with warnings where data is incomplete.

**Minimum AI activity structure:** Each itinerary day must include its date and an ordered list of meaningful activities. Each activity must include an activity name, a destination-appropriate location or area, a short description, and an estimated USD cost or an explicit `unknown` cost status. Arrival and return days may have fewer activities. AI-generated flight/hotel names, offers, or prices are suggestions at most: they must never be shown as provider-sourced offers unless validated against actual provider results.

The **offline demo result** is evaluated separately. It must display a complete, preloaded itinerary in the same results UI, clearly marked **DEMO**, but does **not** count toward the real-AI or live-price acceptance criteria.

## 6. Budget Scope and Calculation Rules

The entire entered budget applies to **all travelers and all nights**. The backend, not the AI, performs arithmetic.

| Category | Treatment in MVP |
|---|---|
| Round-trip flights | Total for all adult passengers; use provider quote when available; otherwise label any estimate or missing amount |
| Accommodation | Total for the entire stay at appropriate occupancy; include multiple rooms if a returned quote requires them, or mark occupancy/pricing as uncertain |
| Activities/attractions | Show estimated costs where reasonably supportable; otherwise explicitly mark unknown |
| Food and local transportation | Include clearly labeled trip-wide or daily estimates if available; otherwise explicitly mark as missing/not included |
| Taxes and fees | Include known amounts and disclose exclusions or uncertain provider fees |

**Currency rule:** Request USD quotes when a provider supports it. Do not add a non-USD price to a USD total unless an identifiable exchange rate/source and conversion timestamp are available; otherwise show it separately and treat the comparable amount as unavailable.

**Budget status:**

- `over_budget` if the known minimum cost already exceeds the entered budget, or the calculated complete projected total exceeds it.
- `within_budget` only if every material category has a usable provider amount or explicitly labeled estimate and the projected total does not exceed budget. This is an **estimate of affordability**, not a price guarantee.
- `uncertain` if significant categories, occupancy details, or currency conversions are missing and a meaningful whole-trip comparison cannot be made.

Display **provider-known subtotal**, **estimated subtotal**, **projected trip total when calculable**, and **missing/excluded costs** separately. Do not replace missing values with zero.

## 7. Core User Journey

1. Open TravelMate and sign in using Supabase Auth (normal online mode).
2. Enter a supported departure/destination, 1–7-night date range, 1–4 adults, and total USD budget.
3. Submit **Generate Trip** and show progress/loading feedback.
4. FastAPI validates input, retrieves available live flight/hotel information, and passes normalized travel context to the real AI API.
5. FastAPI validates the itinerary response and independently assesses the trip budget.
6. React shows daily activities, available travel offers, provenance labels, cost breakdown, budget status, and missing-data warnings.
7. If F-09 is delivered, select **Save Trip**, then reopen the saved itinerary from the user's account.

## 8. Error Handling, Partial Data, and Demo Behavior

| Situation | Required behavior |
|---|---|
| Invalid form | Explain invalid fields before or after submission; do not call external APIs needlessly |
| AI unavailable/invalid output | Display an error and offer retry; never claim a fresh AI plan was generated |
| One travel provider unavailable | Continue only with a complete valid AI itinerary; label missing travel prices clearly |
| Neither travel provider yields real data | A complete valid itinerary with missing travel prices may still appear, but **it does not satisfy F-08A/live integration acceptance** for that test |
| Provider rate limit, timeout, or key issue | Handle safely, expose a user-readable error, and avoid endless retries |
| Budget cannot be reliably assessed | Return `uncertain`, not a misleading success message |
| Offline demo selected | Use predetermined fixtures; clearly mark DEMO; make no online provider requests or hosted Supabase login |

**Demo scope:** Provide **2–3 selectable predefined example trips** (not arbitrary live generation), each with sample input and a complete results view. Demo mode is read-only and must not create fake real accounts or claim live prices.

## 9. Out of Scope

- Demo booking/confirmation screens are deferred beyond this MVP; the mandatory demo is the read-only offline trip experience, not a simulated checkout.

- Real bookings, ticket purchases, or payment processing.
- AI chat assistant, conversational plan changes, or unlimited regeneration.
- Maps, live navigation, GPS, route optimization, or multi-city trips.
- Travelers under 18 and detailed traveler profiles.
- Multi-currency budget selection or unverified currency conversions.
- Personalization based on historical user behavior, social features, reviews, or admin panel.
- Native Android/iOS apps and public production deployment.
- Guaranteed pricing or guaranteed flight/hotel availability.

## 10. Quality, Testing, and Handover

- **Local launch:** Provide `README.md`, `.env.example`, dependency installation instructions, and a startup script for the evaluator's computer. Do not commit secrets.
- **Honest sourcing:** Preserve price category, source/provider, retrieval time, coverage (per-person/per-night versus total), and missing data in the UI.
- **Safety:** Validate input; keep API keys in the backend; authorize protected operations and restrict saved trips to their owner.
- **User experience:** Show visible loading feedback and friendly failures; prevent multiple accidental generation requests; use bounded backend provider timeouts/retries.
- **Testing:** Check form validation, supported-location rules, minimum AI activity fields, real AI output parsing, at least one actual live-price response plus a second distinct supported query where feasible, both price categories absent, budget logic, demo mode, and (if built) account ownership for saved trips.
- **Handover:** Verify normal online operation and offline demo operation on a second computer before submission.

## 11. MVP Acceptance Checklist

### Mandatory (MVP passes only if these are satisfied)

- [ ] Application launches locally according to the README.
- [ ] Normal-mode sign-up, sign-in, and sign-out work using Supabase Auth.
- [ ] The trip form enforces **1–4 adults**, **1–7 nights**, distinct locations, and **USD total budget**.
- [ ] A valid online request invokes a real AI API and displays days and activities with dates, order, names, locations, descriptions, and estimated or unknown costs.
- [ ] **At least one live travel API (flight OR hotel)** returns real, search-relevant provider price information for a documented supported test case; provider queries use user inputs rather than fixed response fixtures.
- [ ] The provider adapter has been exercised with two different supported input combinations where feasible, with results/evidence documented (at least one real price result is mandatory).
- [ ] Supported cities/routes are documented, and unsupported queries receive an honest message.
- [ ] Live offer displays provider/source, retrieval time, and clear amount coverage.
- [ ] The second category is displayed when available, or honestly labeled estimated/unavailable.
- [ ] Backend returns budget subtotals, missing-cost warnings, and a correct status; no missing cost is counted as zero.
- [ ] UI handles invalid input, loading, API failure, partial availability, and retry.
- [ ] Read-only offline demo shows **2–3 predefined complete sample trips** without online dependencies and is visibly marked DEMO.
- [ ] Protected user data cannot be accessed using another user's identity.
- [ ] Full local setup and demo have been tested on a second computer.

### Secondary (does not block MVP acceptance)

- [ ] The second travel-data category uses a real provider API.
- [ ] Users can save, list, and reopen their own plans.

## 12. Decisions, Feasibility Gate, and Change Control

**Scope and v1.3 working limits approved by team lead Nasrawy (Nasrawy1) on 2026-10-15 under PLAN-01 (#10). Review/acknowledgment by the remaining team members is not yet recorded:**

- **Confirmed by team lead:** Delivery policy is **Option B — at least one live flight or hotel integration is mandatory**.
- 1–4 adult passengers; one destination; 1–7 nights; round-trip travel.
- USD as the sole budget/display currency for MVP totals.
- Provider quotes and estimates are explicitly distinguishable.
- Read-only offline demo with 2–3 predefined journeys.
- Real AI generation is mandatory in normal online mode; save/reopen and the second travel integration remain secondary.

**Provider feasibility checkpoint (first two working days of integration work):**

1. Test candidate flight and hotel APIs for accessible credentials, permitted use, supported routes/dates, usable real price results, currency/occupancy coverage, rate limits, and cost. **Start this research immediately, alongside the API-contract drafting, rather than waiting for frontend/backend implementation.**
2. Demonstrate at least one real end-to-end price response from FastAPI for a documented, dynamically constructed trip search; test a second supported input combination where possible.
3. Record the chosen mandatory provider, verified locations/routes, example search inputs, limitations, and sample normalized output. Prioritize that provider before the optional second one.
4. If **neither** provider is viable, escalate immediately to the team lead and supervisor for an explicit scope decision. Do not silently mark demo/mock prices as meeting the live requirement.

**Defined in companion documents:** `api-contracts.md` v0.3 specifies core HTTP schemas and `database-schema.md` v0.2 specifies the optional one-table backend-only storage design. `implementation-plan.md` proposes the task sequence and owners.

**Still pending:** exact provider names and verified city searches, evidence for the AI provider choice, estimation/conversion policy, confirmation of offer selection and timeouts, and exact F-09 HTTP payloads if saving is prioritized. This approval covers scope and architecture only; it does not establish provider feasibility, full-team acknowledgment, or PLAN-02 integration-contract approval.

**Change control:** New MVP functionality requires team approval after considering time, API access, and integration cost. Any change to the live-price acceptance gate must be documented and agreed explicitly.

---

**Architecture compatibility:** This scope follows `architecture.md` v1.2: React + Vite frontend, FastAPI modular-monolith backend, Supabase Auth/PostgreSQL, real AI/travel adapters, and an explicit offline demo flow.

