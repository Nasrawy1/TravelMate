# TravelMate — API Contracts

**Version:** 0.4 (complete contract and fixture review candidate)  
**Status:** Draft — prepared with team-lead authorization on 2026-10-15; pending Diyar/Adel/Ziyad review and provider feasibility sign-off.  
**Scope authority:** Team-lead-approved scope v1.3 and architecture v1.2. PLAN-01 approval does not approve this integration contract.

## 1. Purpose and authoritative artifacts

This contract defines React ↔ FastAPI HTTP messages. [Internal adapter contracts](adapter-contracts.md) define FastAPI ↔ Ziyad's adapters. [JSON Schema](contracts/api-v0.4.schema.json) is the normative field/type/required/nullability definition; the semantic rules below are also mandatory. [Fixtures](fixtures/README.md) demonstrate valid shapes and arithmetic, not real prices or provider feasibility.

v0.4 changes the response: required `budget.cost_items`, offer `taxes`, nullable hotel `room_qty`, and daily `empty_day_reason` are added. Request fields, endpoints and status enums are unchanged from v0.3. Coordinate adoption before integrating branches. Do not silently validate v0.4 using v0.3 models.

## 2. HTTP and conventions

- Local base: `http://localhost:8000/api/v1`; JSON bodies; public fields use snake_case.
- Currency: USD only; budget and totals cover all adults and the entire trip. Server arithmetic uses decimal-safe amounts and rounds each normalized ledger item to cents before summing; display two decimals. Reject NaN/infinity.
- Calendar dates: YYYY-MM-DD. Proposed validation reference is today's **UTC calendar date**, consistently in client tests and server validation; start_date must be strictly later. This is a validation convention, not a conversion of destination travel dates.
- Travel dates refer to local dates at the relevant departure airport/hotel. UTC offer timestamps end in Z. The flight adapter retains airport timezone information internally to verify that UTC departures correspond to the requested local travel dates.
- Every schema property is required unless its enclosing object is absent by design; unknown allowed values are explicit nulls. Arrays such as warnings, notes and offers are always present, including when empty. Unknown properties are rejected for this candidate.
- Schema format checks must be enabled. Cross-field/date/reference/arithmetic rules require additional semantic validation.

| Method | Path | Auth | Scope |
|---|---|---|---|
| GET | /health | None | Mandatory |
| POST | /trips/generate | Supabase bearer token | Mandatory |
| POST | /trips | Supabase bearer token | Optional F-09, payload deferred |
| GET | /trips | Supabase bearer token | Optional F-09, payload deferred |
| GET | /trips/{trip_id} | Supabase bearer token | Optional F-09, payload deferred |

Supabase Auth SDK provides signup/signin/signout and session management. Do not duplicate login/signup routes in FastAPI. Protected routes verify token signature, expiry and issuer/audience as appropriate and derive identity from that verified token.

## 3. Generate request

`POST /api/v1/trips/generate` with `Authorization: Bearer <access_token>`.

```json
{
  "departure_city": "Istanbul",
  "destination_city": "Rome",
  "start_date": "2026-11-10",
  "return_date": "2026-11-12",
  "adults": 2,
  "budget_usd": 1500
}
```

| Field | Type | Constraint |
|---|---|---|
| departure_city | string | Canonical supported city label |
| destination_city | string | Canonical supported label; distinct from departure |
| start_date | date string | Future UTC calendar date under validation convention above |
| return_date | date string | 1–7 nights after start_date |
| adults | integer | 1–4 adults; reject booleans, fractions and numeric strings |
| budget_usd | number | Positive whole-trip, all-adult budget |

No currency selector, one-way switch or client user_id. Reject unsupported cities with 400 UNSUPPORTED_LOCATION. Provider adapters map canonical labels to provider IDs. A supported city pair with no offers is distinct from an unsupported city input. The actual supported list and identifier mapping remain pending feasibility; fixture cities do not establish coverage.

## 4. Successful response and required fields

HTTP 200 requires a complete, validated itinerary, even when travel prices are unavailable. No persistence occurs and no saved trip ID is returned.

| Object/field | Required interpretation |
|---|---|
| generation_status | Always complete on HTTP 200; partial is not supported |
| live_integration_status | price_received if at least one valid live flight/hotel offer exists, otherwise no_price |
| trip | departure_city, destination_city, start_date, return_date, adults match request; nights equals date difference |
| itinerary | Exactly nights + 1 entries, ordered, one per date inclusive |
| travel_options | Both flights and hotels objects always present |
| budget | Original budget, selected offer IDs, itemized costs, subtotals, projected total, status, missing categories and notes |
| warnings | Array of code/message pairs; empty when none |

Each itinerary day has date, activities and empty_day_reason. Activities require order, name, area, description and cost. Order is contiguous from 1 within a day. Each nonempty day has empty_day_reason null. Only first/last days may have zero activities; they require a nonempty travel-related reason. Other days must contain at least one meaningful activity.

Activity cost uses amount_usd, kind and coverage. Normal AI activities permit estimate (nonnegative, coverage all_travelers) or unknown (amount and coverage null). Do not present AI prices as provider facts. An explicit zero estimate is allowed for a justified free activity; missing is not zero.

### Travel offers

The JSON Schema defines every field. Both categories always return status live or unavailable and offers array. live requires at least one usable offer; unavailable requires [].

- Flight fields: id, airline, departure_airport_code, arrival_airport_code, outbound_departure_at, return_departure_at, adults, source, retrieved_at, price, taxes.
- Hotel fields: id, name, area, check_in, check_out, occupancy_adults, room_qty, source, retrieved_at, price, taxes.
- Hotel area and room_qty may be null if the provider does not expose them. Null room_qty does not waive verified all-adult occupancy; exclude any quote whose occupancy cannot be established.
- IDs are unique across all offers in a response. They identify options, not stored database records.
- Offer price.kind is provider; amount_usd is nonnegative; coverage is entire_trip_all_travelers. Flight quotes cover the round trip for all adults. Hotel quotes cover all requested nights/adults; never multiply an already totalled quote again.
- The adapter may combine two valid one-way quotes internally; the public shape still describes one complete round trip.
- source identifies the actual data service; retrieved_at is the UTC retrieval time, not a guarantee of booking availability. Preserve any older supplier quotation timestamp internally.
- Only offers matching the request's dates, route and passenger/occupancy scope qualify. Arbitrary route-page deals are not eligible.
- Request USD upstream when possible. Non-USD amounts require a documented conversion source/rate/time retained internally before normalization. Without an approved conversion method, exclude the offer from USD-priced results and warn; never relabel GBP as USD.

Each offer has taxes:
- included: additional_amount_usd = 0; the price already includes all known mandatory fees.
- additional_known: additional_amount_usd > 0, the mandatory additional total for all travelers/whole stay or round trip; this amount is NOT already in price.amount_usd.
- unknown: additional_amount_usd = null; fee completeness cannot be established. A known base quote can remain visible, but the budget must disclose missing taxes_fees and cannot claim a complete projected total.
- Where fees are partly known, normalize the known portion into price with internal evidence, then mark remaining fee uncertainty unknown. Never discard known charges.

**Proposed selection rule:** Prefer comparable offers with known fee totals (included/additional_known); choose the lowest base + additional total, tie-break by ID. If all eligible offers have unknown fees, choose lowest known base, warn that this is not a verified cheapest final total. Select exactly one offer per available category, or null when no valid offer exists. Diyar highlights the backend selection and never selects independently. This refines the provisional v0.3 rule and needs team review.

### Itemized budget

budget.cost_items is the only source for budget arithmetic. Each entry has:

| Field | Rule |
|---|---|
| id | Unique cost-item ID within result |
| category | flights, accommodation, activities, food, local_transport, taxes_fees |
| label | User-readable expense name |
| amount_usd | Whole-group/whole-trip amount, or null for unknown |
| kind | provider, estimate, unknown |
| coverage | Always entire_trip_all_travelers after normalization |
| basis | Explain source/estimate calculation or why unknown; no secrets |
| source_offer_id | Selected offer ID for provider lines; otherwise null |
| activity_ref | {date, order} for activity entries; otherwise null |

Ledger rules:
1. Include exactly one base line for flights and one for accommodation. If no valid selected offer exists, use unknown; this candidate does not invent estimates for missing flights/hotels.
2. Provider base lines equal the selected offer's base price. Non-selected alternatives never enter the ledger.
3. Add exactly one provider taxes_fees line for each selected offer with additional_known fees; add one unknown taxes_fees line for each with unknown fees. Included fees require no extra line.
4. Include one activities entry per itinerary activity; preserve its amount/kind and activity_ref. No duplicate activity references. These are whole-group one-occurrence costs, counted once.
5. Include one food and one local_transport entry for the whole trip. Use an estimate only when a reviewed estimation policy exists; otherwise unknown. Do not multiply by days or adults again after normalization.
6. For this candidate, provider ledger entries come only from selected flight/hotel quotes and their fees. Activity/food/transport expenses are estimates or unknown. Extra categories or supplier activity offers require a contract revision.
7. Core material categories are flights, accommodation, activities, food and local_transport. taxes_fees is material when a selected offer has additional/unknown charges. missing_categories is the unique set of categories containing unknown entries. For a two-day travel-only itinerary with no activities, no activity cost is missing merely because there is no planned activity.
8. Unknown entries have amount null; provider/estimate entries have nonnegative amounts. A zero subtotal means there are no known costs of that kind, not that unknown travel is free.

Calculation order:
- provider_subtotal_usd = sum(provider ledger entries).
- estimated_subtotal_usd = sum(estimate ledger entries).
- projected_total_usd = null if any unknown entry exists; otherwise sum of both subtotals.
- status = over_budget if the reliable provider-known subtotal already exceeds budget, even with missing costs; otherwise over_budget if a complete projected total exceeds budget; otherwise within_budget when total is non-null and ≤ budget; otherwise uncertain.
- Estimates do not prove a reliable minimum when other categories are missing.
- Fees are counted in either the quote's base or its additional line, never both.
- Selected IDs must exist in the corresponding offers array; missing IDs are null.
- notes and warnings explain missing costs and fee assumptions. within_budget means a projected fit, not guaranteed prices.

Full ready-to-load responses are in [fixtures](fixtures/README.md). within-budget totals: provider $950, estimates $190, projected $1,140. partial-prices: provider $550, estimates $40, total null. These are artificial test amounts.

## 5. Errors, availability and retries

Non-2xx body:
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Adults must be between 1 and 4.",
    "details": {"fields": [{"field": "adults", "message": "Must be between 1 and 4."}]}
  },
  "request_id": "opaque-request-id"
}
```

error.details is always present as an object or null. Field errors use details.fields with field/message pairs. Error responses always include request_id and a matching X-Request-ID header. Translate FastAPI/Pydantic errors into this envelope.

| HTTP | Code |
|---|---|
| 400 | INVALID_TRIP_DATES, UNSUPPORTED_LOCATION |
| 401 | UNAUTHORIZED |
| 403 | FORBIDDEN (where applicable) |
| 404 | NOT_FOUND (optional records, including another owner's record) |
| 422 | VALIDATION_ERROR |
| 429 | RATE_LIMITED |
| 502 | AI_GENERATION_FAILED |
| 503 | PROVIDER_UNAVAILABLE |
| 504 | GENERATION_TIMEOUT |
| 500 | INTERNAL_ERROR |

Wrong types/missing fields/range errors use 422. Well-typed but invalid date relationships use 400 INVALID_TRIP_DATES. Missing, expired or invalid auth uses 401.

Travel errors alone do not cause total generation failure: if AI succeeds, return 200 with empty failed-category offers and warnings. AI timeout uses 504; invalid AI structure uses 502; confirmed AI service outage may use 503; upstream AI rate limits may use 429. A travel-provider 429 is a warning within an otherwise valid 200 result, not an automatic whole-request 429.

Proposed warning codes: FLIGHTS_UNAVAILABLE, HOTELS_UNAVAILABLE, TRAVEL_RATE_LIMITED, TRAVEL_TIMEOUT, CURRENCY_UNAVAILABLE, TAXES_UNKNOWN, BUDGET_INCOMPLETE. Document any newly introduced codes before UI integration; frontend must display the safe message for unrecognized codes too.

Initial configuration defaults, pending measured tests:
- Travel lookup: 10 seconds per request.
- AI: 35 seconds per attempt.
- Overall generation: 60 seconds including all lookups, AI and validation.
- Frontend transport allowance: 70 seconds.
- At most one retry for an idempotent travel lookup on transient failure, only within the overall deadline. Honor Retry-After when it fits.
- No automatic retry of chargeable AI generation; no auth/validation/unsupported-input retries. Prevent duplicate submits.
- If generation reaches its overall deadline, return 504.
- Never expose provider secrets, tokens or raw debug responses.

GET /health returns 200 {"status":"ok","service":"travelmate-api"} and proves only local backend health.

## 6. Offline demo and fixtures

Offline demo is a separate explicit client path, not a query parameter or authentication bypass on /trips/generate. It uses bundled read-only fixtures, with no backend generation, hosted sign-in or provider calls. Online service initialization must not fire on entering demo.

The fixture manifest carries data_mode structural_mock and live_evidence false outside the public response. Diyar must preserve this context and show a DEMO/MOCK banner whenever these files are rendered, even though payload fields simulate live shapes. These examples are not production fallbacks and do not count as real-price evidence. Final 2–3 curated demo journeys remain FE-03 work.

Dates are fixed for reproducibility. Fixtures use validation_today_utc = 2026-10-15; dynamic integration tests must generate future dates relative to runtime. Never use an old fixture date as a production supported-search promise.

## 7. Internal ownership and flow

React validates input → FastAPI verifies JWT and validates request → travel adapter normalizes genuine offers → FastAPI selects offers → AI adapter proposes complete itinerary → FastAPI validates output, creates expense ledger and calculates totals → React renders.

- Adel: public schemas/routes, auth, deadlines, orchestration, offer selection, deterministic ledger/budget and final response.
- Ziyad: provider ID mapping, travel normalization/evidence and AI adapter typed output.
- Diyar: forms, API handling, mocks, demo context, and backend-determined results.
- Team lead: review decisions, fixture consistency, and cross-owner approval.

See [adapter-contracts.md](adapter-contracts.md) for input/output objects, failure envelopes and handoff checklist.

## 8. Optional storage

F-09 remains deferred. Generate never writes to the database. Saved-trip HTTP payloads are not finalized here. If prioritized, follow database-schema.md: React uses Auth only; FastAPI alone accesses public.trips through its server-only elevated client and enforces verified user ownership explicitly because that client bypasses RLS. Snapshots remain unverified historical user-submitted copies. Validate against the actual adopted contract version; do not execute a migration under PLAN-02.

## 9. Review gates before PLAN-02 Done

Prepared in this revision: field schema, expense ledger, adapter boundary proposal, structural examples and semantic checks.

Still pending:
- [ ] Diyar confirms forms/results/errors/demo context against these fixtures.
- [ ] Adel confirms schemas, ledger rules, UTC validation reference, error mappings and adapter boundary.
- [ ] Ziyad confirms provider normalization, AI output contract, route timezone handling and fee/occupancy evidence.
- [ ] Select the mandatory provider and verify supported cities/routes; confirm canonical labels suffice.
- [ ] Approve a food/local-transport estimation policy; until then these remain unknown in real output. Fixture rates are illustrative, not an approved policy.
- [ ] Approve a conversion method or keep non-USD quotes unavailable.
- [ ] Confirm fee-aware selection and timeout defaults using actual provider evidence.
- [ ] Record team-lead integration approval after the above reviews.

Provider-independent scaffolding and mock UI may proceed. This document does not claim a live provider has passed acceptance or that team review is complete.
