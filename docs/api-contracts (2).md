# TravelMate — API Contracts

**Version:** 0.3 (Implementation baseline candidate)  
**Status:** Draft — pending team review and provider feasibility sign-off  
**Related:** `architecture.md` v1.1; `mvp-scope.md` v1.2

## 1. Purpose and conventions

This document defines the interface between the React frontend and FastAPI backend. It is **not** a provider-specific AI, flight, or hotel API specification.

- Base URL (local development): `http://localhost:8000`
- Prefix: `/api/v1`
- Transport: HTTP; JSON request/response (`application/json`).
- Property naming: `snake_case`.
- Monetary amounts: JSON numbers in **USD**. Round/display to two decimal places; backend calculations should use decimal-safe arithmetic.
- Dates: `YYYY-MM-DD`; timestamps: ISO 8601 UTC with `Z`.
- Normal-mode protected endpoints: `Authorization: Bearer <supabase_access_token>`.
- Frontend uses Supabase Auth SDK for sign-up/sign-in/sign-out; FastAPI validates access tokens on protected endpoints.
- The backend owns validation, third-party API calls, cost aggregation, and budget status. The frontend must not infer missing costs as zero.
- The offline demo is a **separate, read-only client flow** using bundled fixtures; it does not call the live generation endpoint or require Supabase login.
- The backend attaches an opaque `request_id` to error responses and logs for troubleshooting; it must not log secrets or full access tokens.
- One successful HTTP 200 generation response always contains a **complete, schema-valid itinerary**. Missing travel prices are conveyed by offer availability, budget status, and warnings—not by an incomplete itinerary.

## 2. Endpoint inventory

| Method | Path | Authentication | Status | Purpose |
|---|---|---|---|---|
| GET | `/api/v1/health` | None | MVP | Local health check |
| POST | `/api/v1/trips/generate` | Supabase bearer token | MVP | Generate itinerary with available travel prices |
| POST | `/api/v1/trips` | Supabase bearer token | Should Have | Save a generated itinerary |
| GET | `/api/v1/trips` | Supabase bearer token | Should Have | List own saved trips |
| GET | `/api/v1/trips/{trip_id}` | Supabase bearer token | Should Have | Retrieve own saved trip |

No separate FastAPI `/login` or `/signup` route is planned.

## 3. Generate trip — request

**POST** `/api/v1/trips/generate`

```http
Authorization: Bearer <supabase_access_token>
Content-Type: application/json
```

```json
{
  "departure_city": "Istanbul",
  "destination_city": "Rome",
  "start_date": "2026-11-10",
  "return_date": "2026-11-15",
  "adults": 2,
  "budget_usd": 1500.00
}
```

| Field | Type | Rule |
|---|---|---|
| `departure_city` | string | Required; canonical supported city label; different from destination |
| `destination_city` | string | Required; canonical supported city label |
| `start_date` | date string | Required; future local calendar date |
| `return_date` | date string | Required; after `start_date`; 1–7 nights |
| `adults` | integer | Required; 1–4 |
| `budget_usd` | number | Required; greater than 0; entire trip/all travelers |

**Location contract for v0.3:** use agreed canonical city labels in the public API; adapters map them to provider-specific identifiers (e.g., airport/city codes). The supported city/route list is to be finalized after Ziyad's provider feasibility tests. Do not silently pass arbitrary user text as a provider ID. If the provider forces a stronger canonical ID scheme, revise the contract *before frontend/backend integration*.

## 4. Generate trip — successful response

**HTTP 200** — a successful request returns `generation_status: "complete"` when the AI itinerary covers every trip date and passes backend validation. This status is **independent** of travel-price availability and budget completeness. An invalid or incomplete itinerary is **not** a successful 200 response. The example below is a complete six-day illustrative response for a five-night trip, suitable as a structural mock (but never evidence of real provider data).

```json
{
  "generation_status": "complete",
  "live_integration_status": "price_received",
  "trip": {
    "departure_city": "Istanbul",
    "destination_city": "Rome",
    "start_date": "2026-11-10",
    "return_date": "2026-11-15",
    "nights": 5,
    "adults": 2
  },
  "itinerary": [
    {
      "date": "2026-11-10",
      "activities": [
        { "order": 1, "name": "Historic center walk", "area": "Central Rome", "description": "Explore local squares after arrival.", "cost": { "amount_usd": 0, "kind": "estimate", "coverage": "all_travelers" } }
      ]
    },
    {
      "date": "2026-11-11",
      "activities": [
        { "order": 1, "name": "Colosseum visit", "area": "Colosseo", "description": "Visit the ancient amphitheater.", "cost": { "amount_usd": 40, "kind": "estimate", "coverage": "all_travelers" } }
      ]
    },
    {
      "date": "2026-11-12",
      "activities": [
        { "order": 1, "name": "Trastevere walking tour", "area": "Trastevere", "description": "Discover the neighborhood on foot.", "cost": { "amount_usd": 0, "kind": "estimate", "coverage": "all_travelers" } }
      ]
    },
    {
      "date": "2026-11-13",
      "activities": [
        { "order": 1, "name": "Museum visit", "area": "Central Rome", "description": "Explore a museum during the afternoon.", "cost": { "amount_usd": 20, "kind": "estimate", "coverage": "all_travelers" } }
      ]
    },
    {
      "date": "2026-11-14",
      "activities": [
        { "order": 1, "name": "Public gardens walk", "area": "Villa Borghese", "description": "Spend time outdoors in the park.", "cost": { "amount_usd": 0, "kind": "estimate", "coverage": "all_travelers" } }
      ]
    },
    {
      "date": "2026-11-15",
      "activities": [
        { "order": 1, "name": "Departure preparation", "area": "Rome", "description": "Pack and prepare for the return journey.", "cost": { "amount_usd": 0, "kind": "estimate", "coverage": "all_travelers" } }
      ]
    }
  ],
  "travel_options": {
    "flights": {
      "status": "unavailable",
      "offers": []
    },
    "hotels": {
      "status": "live",
      "offers": [
        {
          "id": "hotel-offer-1",
          "name": "Example Hotel",
          "area": "Central Rome",
          "source": "example-provider",
          "retrieved_at": "2026-10-14T11:00:00Z",
          "price": { "amount_usd": 650, "kind": "provider", "coverage": "entire_trip_all_travelers" },
          "check_in": "2026-11-10",
          "check_out": "2026-11-15",
          "occupancy_adults": 2
        }
      ]
    }
  },
  "budget": {
    "budget_usd": 1500,
    "selected_flight_offer_id": null,
    "selected_hotel_offer_id": "hotel-offer-1",
    "provider_subtotal_usd": 650,
    "estimated_subtotal_usd": 60,
    "projected_total_usd": null,
    "status": "uncertain",
    "missing_categories": ["flights", "food", "local_transport"],
    "notes": ["Flight, food and local transportation costs are not available."]
  },
  "warnings": [
    { "code": "FLIGHTS_UNAVAILABLE", "message": "Live flight prices are not available for this search." },
    { "code": "BUDGET_INCOMPLETE", "message": "Some significant costs are missing; the total is uncertain." }
  ]
}
```

**Example data only:** All itinerary suggestions, the hotel name, provider string, and amounts are **illustrative fixture values**, not verified live offers. A real response may use `kind: "provider"` and `live_integration_status: "price_received"` only after the backend genuinely receives and validates a live offer. Do not use this fixture to claim live integration acceptance.

### Response semantics and independent status fields

| Field | Allowed values | Meaning |
|---|---|---|
| `generation_status` | `complete` | The AI-generated itinerary passed structural validation and covers every day. **HTTP 200 returns only `complete` in MVP v0.3.** |
| `live_integration_status` | `price_received`, `no_price` | Whether this request returned at least one validated, real priced flight/hotel offer. |
| `budget.status` | `within_budget`, `over_budget`, `uncertain` | Affordability assessment, computed independently by the backend. |
| `travel_options.<category>.status` | `live`, `unavailable` | Whether that category has one or more usable, real priced offers. |

- **Breaking clarification from v0.2:** `generation_status: "partial"` is retired for the MVP. Missing prices or partial travel data must **not** downgrade a complete AI itinerary. A malformed, incomplete, or unusable AI itinerary must cause an error rather than HTTP 200.
- `live_integration_status: "price_received"` means at least one genuine provider offer was obtained **for this particular request**, but does not on its own prove the project passed the dynamic integration acceptance tests. If none is obtained (including zero-result searches), return `no_price`.
- `travel_options.<category>.status` is `live` only if a valid live price exists. `unavailable` covers unsupported searches, provider errors, and zero results; distinguish causes through warning codes.
- `cost.kind`: `provider` for validated supplier prices; `estimate` for approximations; `unknown` with `amount_usd: null` and `coverage: null` for missing amounts. Any cost counted in USD subtotals must already be normalized to **all adults** or **the entire stay/round trip**.
- `projected_total_usd` is `null` when any material budget component is unknown or currency normalization is unreliable. **Never replace unknown with zero.**
- The backend returns exactly one itinerary entry per date from `start_date` to `return_date` inclusive (`nights + 1` dates), in order. Arrival/return days may have zero activities only if explicitly justified by travel; day entries cannot be omitted.
- Provider offers include `source`, UTC `retrieved_at`, all-adult coverage, and occupancy/traveler count. A quote is **not** guaranteed current availability or bookability.
- An unsaved generated response includes **no persisted trip ID**. Saving is a separate Should Have endpoint.

### Budget calculation — normative MVP rules

Budgeting uses exactly one **selected valid offer per flight/hotel category** (when available), not the sum of every alternative offer. Each price that contributes to a subtotal must already be normalized to USD and the whole relevant trip/group coverage.

1. `provider_subtotal_usd` = selected real-priced flight total (if present) + selected real-priced accommodation total (if present) + any other **distinct** provider-priced expenses explicitly included. Known taxes/fees already included in a quote are **not added again**.
2. `estimated_subtotal_usd` = sum of distinct available estimates for all-adult activities, food and local transport, and other disclosed expenses **not already counted**. Daily estimates are multiplied by their applicable days exactly once; one-off activities are counted once per occurrence.
3. If **all material cost categories** are accounted for with usable provider prices or labeled estimates: `projected_total_usd = provider_subtotal_usd + estimated_subtotal_usd`. Any known or estimated taxes/fees not already included in an offer must first be added to the appropriate subtotal exactly once; **no hidden third subtotal**.
4. If a material cost category is missing (or occupancy/currency is unverified): `projected_total_usd = null`, retain the known/estimated subtotals, and list missing categories. Do **not** silently use zero.
5. Assign `budget.status` in this order:
   - `over_budget` when the reliable known minimum (provider-priced subtotal and any other **verified, unavoidable** charges) already exceeds `budget_usd`, **even if the projected total is null**; or when a complete projected total is greater than the budget.
   - `within_budget` only when the projected total is non-null and less than or equal to the budget; this is a *projected fit*, not a price guarantee.
   - `uncertain` otherwise.

**Selected-offer references:** `budget.selected_flight_offer_id` and `budget.selected_hotel_offer_id` are required fields, each either a string matching an `id` in the corresponding returned `offers[]` array or `null` when no valid offer was chosen. Only the referenced offers contribute flight/hotel amounts to the budget. The frontend highlights these offers and must not calculate a different selection independently.

**Example from above:** chosen hotel = $650; all-adult activity estimates = $60; flights, food, and local transport unknown. Thus `provider_subtotal_usd = 650`, `estimated_subtotal_usd = 60`, `projected_total_usd = null`, and `budget.status = uncertain` (because the known minimum does not exceed $1,500 and the entire trip is not priced).

### Travel offer and price schema (normative for MVP)

Both offer types below are **backend-normalized response objects**, not third-party API payloads. `source` and `retrieved_at` must identify real source data; example offers are not evidence of live integration.

**Shared price object**

| Field | Type | Meaning |
|---|---|---|
| `amount_usd` | number or null | Normalized USD amount; null if unknown |
| `kind` | `provider` / `estimate` / `unknown` | Provenance of price |
| `coverage` | `entire_trip_all_travelers` / `all_travelers` / null | Total coverage, never ambiguous per-night or per-person amounts |

For real flight/hotel offers, `kind` must be `provider`, `amount_usd` must be non-negative, `coverage` must be `entire_trip_all_travelers`, and `source`/`retrieved_at` are required. A provider quote in a non-USD currency may only be normalized with a recorded conversion source and time; if conversion cannot be performed, it cannot be included as a USD priced offer. The backend may retain original currency and quote internally.

**Flight offer shape** (`travel_options.flights.offers[]`):

```json
{
  "id": "flight-offer-1",
  "airline": "Example Airline",
  "departure_airport_code": "IST",
  "arrival_airport_code": "FCO",
  "outbound_departure_at": "2026-11-10T07:00:00Z",
  "return_departure_at": "2026-11-15T18:00:00Z",
  "adults": 2,
  "source": "example-provider",
  "retrieved_at": "2026-10-14T11:00:00Z",
  "price": { "amount_usd": 480.00, "kind": "provider", "coverage": "entire_trip_all_travelers" }
}
```

Times are UTC ISO 8601. The flight quote must cover the **round trip for all adults**; if a provider returns one-way fares, the adapter must construct and validate a combined round-trip price before presenting this shape.

**Hotel offer shape** (`travel_options.hotels.offers[]`):

```json
{
  "id": "hotel-offer-1",
  "name": "Example Hotel",
  "area": "Central Rome",
  "check_in": "2026-11-10",
  "check_out": "2026-11-15",
  "occupancy_adults": 2,
  "source": "example-provider",
  "retrieved_at": "2026-10-14T11:00:00Z",
  "price": { "amount_usd": 650.00, "kind": "provider", "coverage": "entire_trip_all_travelers" }
}
```

Hotel quotes must cover **all nights and all travelers**, including room count where needed. If the provider cannot establish suitable occupancy, exclude the offer or return an explicit warning; never assume a single room accommodates four adults.

**Selection rule (provisional):** Offers are **alternatives**, never costs to sum. The backend selects the cheapest eligible, comparable priced offer in each category (tie-break by offer ID), after confirming round-trip coverage or correct hotel occupancy/all nights and currency normalization. The `budget.selected_*_offer_id` fields make the chosen offers visible to React. If no valid offer exists in a category, return `null` for its selected ID and do not invent a price. This selection algorithm requires team sign-off and may be revisited if the provider offers non-comparable fare or room types.

**Activity costs:** `amount_usd` describes the cost **for all adults in that activity**, not per adult. Every activity still needs `order`, `name`, `area`, `description`, and a price object (`kind: unknown` if no sound estimate).

### Complete itinerary fixture rule

The full example in Section 4 contains **November 10–15 inclusive** (six dates for five nights). Diyar and Adel can use this structure for frontend/backend mock contract tests. It intentionally uses illustrative amounts and MUST NOT be displayed as a live result without a real provider request. Demo mode uses separately marked read-only fixtures. Date-validation tests should calculate future dates relative to the test runtime, rather than relying indefinitely on the static November 2026 dates.

## 5. Error response contract

Non-2xx responses use the common shape below. Never leak credentials or raw provider payloads. FastAPI default Pydantic validation errors **must** be translated via exception handlers to the same envelope. `details` is an object (or null), with field-specific errors optionally represented as `details.fields` (array of `{field, message}` objects). `request_id` is a backend-generated opaque identifier present on every API error response and mirrored in the `X-Request-ID` response header; it helps the team correlate failures with **sanitized** server logs.

```json
{
  "error": {
    "code": "INVALID_TRIP_DATES",
    "message": "Trip duration must be between 1 and 7 nights.",
    "details": { "field": "return_date" }
  },
  "request_id": "e1adf1ba-26ee-4f5c-9b5b-6f6f4ef4fe16"
}
```

| HTTP | Code | Meaning / frontend action |
|---|---|---|
| 400 | `INVALID_TRIP_DATES` | Correct date fields |
| 400 | `UNSUPPORTED_LOCATION` | Select supported cities |
| 401 | `UNAUTHORIZED` | Sign in / refresh session |
| 403 | `FORBIDDEN` | Authenticated but insufficient permission (where applicable) |
| 404 | `NOT_FOUND` | Record not found or not owned; do not reveal existence |
| 422 | `VALIDATION_ERROR` | Correct invalid input fields |
| 429 | `RATE_LIMITED` | Wait and retry later |
| 502 | `AI_GENERATION_FAILED` | Generation failed; retry; no fabricated plan |
| 503 | `PROVIDER_UNAVAILABLE` | Required upstream service unavailable; retry |
| 504 | `GENERATION_TIMEOUT` | Timed out; retry |
| 500 | `INTERNAL_ERROR` | Generic safe error; log details server-side |

Travel-provider failures may still produce **HTTP 200 with `generation_status: "complete"`** if a complete valid AI itinerary was generated. In that case, missing travel data is explicit through category `status`, `live_integration_status`, budget `status`, and warning codes. Use `VALIDATION_ERROR` for generic 422 schema errors; use specific 400 codes for domain validation. `429` may include `Retry-After` if known. If AI generation fails or remains invalid after bounded recovery, return a non-2xx error, never a fabricated itinerary.

### Timeouts and retries — initial implementation defaults

- `TRAVEL_API_TIMEOUT_SECONDS = 10` **per provider request**; an unavailable travel provider may yield an otherwise valid result with missing-price warnings.
- `AI_API_TIMEOUT_SECONDS = 35` **per attempt**; failure to obtain a usable AI itinerary yields `504 GENERATION_TIMEOUT` for timeouts or `502 AI_GENERATION_FAILED` for invalid/unusable output.
- `GENERATION_TIMEOUT_SECONDS = 60` **overall server-side deadline**, including adapters, generation, and validation. Exceeding it yields `504 GENERATION_TIMEOUT`; frontend should allow a slightly longer transport deadline (e.g., 70 seconds) and show a loading state.
- At most **one retry** for idempotent travel-provider lookups on transient failures, only if it fits the overall deadline; **do not automatically retry chargeable AI generation** in the MVP. Do not retry authentication, validation, or unsupported-location errors. Honor known rate limits/`Retry-After` if compatible with the deadline.
- These are **proposed configuration defaults**, not measured provider guarantees. Adel and Ziyad should adjust them after real feasibility tests. Prevent duplicate generation submissions in the frontend.

## 6. Other endpoints — provisional

### GET `/api/v1/health` (MVP)

HTTP 200:

```json
{ "status": "ok", "service": "travelmate-api" }
```

This checks the locally running backend; it does not guarantee Supabase or external providers are currently reachable.

### Saved-trip endpoints (Should Have; not mandatory MVP gate)

- `POST /api/v1/trips`: explicitly save a validated generated plan; server derives owner from the access token; never trust client-supplied `user_id`.
- `GET /api/v1/trips`: return a list of the signed-in user's saved trips.
- `GET /api/v1/trips/{trip_id}`: return one saved trip only if owned by that user; otherwise respond `404` (do not expose ownership).

**Exact saved-trip request/response models are intentionally deferred** until the team decides the storage schema and snapshots in `database-schema.md`. Do not begin implementing these endpoints against assumed payloads.

## 7. API contract testing and ownership

- **Diyar (React):** use example JSON as mock data; implement form validation, loading/error/partial UI states, budget labels, and result rendering.
- **Adel (FastAPI):** implement the endpoint route, Pydantic schemas, token verification, normalized responses, and budget calculations.
- **Ziyad (integrations):** supply provider feasibility findings, supported search cases, stable internal travel adapter output, and actual source/timestamp metadata.
- **Team Lead:** review contract changes and verify that frontend/backend agree on field names and error codes.

Contract acceptance tests: HTTP 200 always has `generation_status: "complete"` and exactly `nights + 1` dates; invalid/incomplete AI output yields non-2xx; both `live_integration_status` values with independently computed `budget.status`; selected offer IDs either reference returned eligible offers or are null; only selected offers counted; flight/hotel normalized schemas and all-traveler coverage; no missing cost treated as zero; common error envelope with `request_id`; input/auth validation; expected timeout behavior; metadata for actual live offers; no secrets in browser responses. Test a real provider using user-dependent searches before counting the live-price MVP requirement as met.

## 8. Decisions pending before v1.0 approval

1. **Live provider:** choose flight or hotel as the mandatory live integration and list verified supported searches.
2. **Location identifiers:** confirm whether canonical city labels are enough or public `city_id`/IATA codes are preferable.
3. **Cost model details:** define estimated food/local transport and activity pricing policy, plus handling provider quotes in currencies other than USD.
4. **Budget completeness:** finalize which cost categories are significant enough to require `projected_total_usd: null` and `uncertain`.
5. **Saved trips:** decide saved payload format and RLS schema if F-09 is implemented.
6. **Offer selection:** confirm or adjust the provisional cheapest-valid-offer rule and whether taxes/fees are sufficiently represented.
7. **Timeout tuning:** confirm the proposed provider, AI, and overall deadlines through measured integration tests; the starting values in this draft are not guarantees.

**v0.2 → v0.3 change note:** A successfully validated itinerary now always returns `generation_status: "complete"`; the old 200 `partial` state is removed. Missing travel data and cost coverage remain observable through their independent fields. The budget response now exposes the two selected-offer IDs; error responses include `request_id`; timeout/retry defaults are documented.

**Change rule:** Altering field names or meanings requires agreement between frontend, backend, and integration owners before merging implementation branches. This draft becomes an implementation baseline only after team review and confirmation that the selected provider can satisfy the mandatory live-price requirement.
