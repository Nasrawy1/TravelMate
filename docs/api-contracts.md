# TravelMate — API Contracts

**Version:** 0.4 (approved public integration baseline)  
**Status:** Approved by Nasrawy on 2026-10-27 as the public integration baseline, including the fixed 80-city reconciliation approved on 2026-10-25. This records contract adoption, not completion of implementation or live acceptance tests.  
**Scope authority:** Team-lead-approved scope v1.3 and architecture v1.2. Public contract adoption is recorded under PLAN-02 (#11) by the 2026-10-27 decision below.

## 1. Purpose and authoritative artifacts

This contract defines React ↔ FastAPI HTTP messages. [Internal adapter contracts](adapter-contracts.md) define FastAPI ↔ Ziyad's adapters. [JSON Schema](contracts/api-v0.4.schema.json) is the normative field/type/required/nullability definition; the semantic rules below are also mandatory. [Fixtures](fixtures/README.md) demonstrate valid shapes and arithmetic, not real prices or provider feasibility.

v0.4 changes the response: required `budget.cost_items`, offer `taxes`, nullable hotel `room_qty`, and daily `empty_day_reason` are added. Request fields, endpoints and status enums are unchanged from v0.3. Use this adopted v0.4 baseline when integrating branches. Do not silently validate v0.4 using v0.3 models.

## 2. HTTP and conventions

- Local base: `http://localhost:8000/api/v1`; JSON bodies; public fields use snake_case.
- Currency: USD only; budget and totals cover all adults and the entire trip. Server arithmetic uses decimal-safe amounts and rounds each normalized ledger item to cents before summing; display two decimals. Reject NaN/infinity.
- Calendar dates: YYYY-MM-DD. The validation reference is today's **UTC calendar date**, consistently in client tests and server validation; start_date must be strictly later. This is a validation convention, not a conversion of destination travel dates.
- Travel dates refer to local dates at the relevant departure airport/hotel. UTC offer timestamps end in Z. The flight adapter retains airport timezone information internally to verify that UTC departures correspond to the requested local travel dates.
- Every schema property is required unless its enclosing object is absent by design; unknown allowed values are explicit nulls. Arrays such as warnings, notes and offers are always present, including when empty. Unknown properties are rejected.
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
| departure_city | string | City name supported by the adapter's approved 80-city mapping; 1–200 characters after trimming |
| destination_city | string | Same city-text rules; must map to a different city from departure |
| start_date | date string | Future UTC calendar date under validation convention above |
| return_date | date string | 1–7 nights after start_date |
| adults | integer | 1–4 adults; reject booleans, fractions and numeric strings |
| budget_usd | number | Positive whole-trip, all-adult budget |

No currency selector, one-way switch or client user_id. City fields remain strings, validated against the adapter's approved fixed 80-city mapping. No new required country, airport or provider-ID field is added.

### Budget cent normalization — implementation observation

Inspection of BE-03 commit `bbe1a841a9a27a81ceecf632086cb72b3847d833`,
`backend/app/api/schemas/trips.py`, confirms that the public request schema converts
numeric budgets with `Decimal(str(value))` and returns
`value.quantize(Decimal("0.01"))`. With the inspected default Decimal context
(precision 28, `ROUND_HALF_EVEN`), `1500.129` becomes `1500.13`, `1500.125`
becomes `1500.12`, and `1500.135` becomes `1500.14`. Budgets must remain positive
after cent rounding; nonfinite, nonpositive and unquantizable oversized values are
rejected. The endpoint passes that normalized value into budget calculation and
returns it in `budget.budget_usd`; it is not an exact echo of a subcent input.
The frontend review correction compares the response budget exactly against this
normalized request expectation, without changing returned costs, totals or statuses.

This is an observed implementation behavior, **not a newly approved contract
amendment or an agreement from Adel**. The adopted schema allows positive JSON
numbers and does not itself specify cent precision or tie-breaking. Adel's explicit
confirmation of the intended public budget tie-breaking rule remains pending.
The adapter's standalone half-up budget helper is distinct from the public request
schema, which normalizes the budget first for this endpoint.

### City validation — approved reconciliation 2026-10-25

Nasrawy approved the fixed 80-city adapter mapping as the current city-validation baseline, superseding the 2026-10-24 free-text/dynamic resolver amendment. The adapter owns the supported set and its name normalization; BE-03 must reuse it rather than maintain a second allowlist. Dynamic resolver integration, acceptance of cities outside that set, ambiguity handling and resolver-outage tests are superseded scope, not completed features. Live autocomplete is optional and is not a BE-03 completion requirement. Implementation and provider-evidence gates remain required. Public contract adoption is recorded by the 2026-10-27 decision below.

- Trim surrounding whitespace; reject wrong types, blank text or more than 200 characters with 422 VALIDATION_ERROR and field details. Unicode is valid text, but aliases and country/region qualifiers are supported only when the adapter maps them to a supported city.
- The adapter owns the 80-city mapping and supported name normalization. Reuse it in BE-03; do not duplicate or widen the accepted set independently. No dynamic provider location resolver is required.
- Cities outside that set return 400 UNSUPPORTED_LOCATION, even if another service could resolve them. Preserve safe field diagnostics when the adapter supplies them; details may be null when none are supplied.
- Identical mapped departure/destination cities return 422 VALIDATION_ERROR, including supported aliases/case variants. Flight, hotel and AI context must refer to the same intended mapped cities; never substitute another city.
- Response trip city strings echo trimmed submitted text; canonical identifiers/provider metadata stay internal. Other request/response fields and BE-04 budget rules remain unchanged.
- A supported city with no quotes uses category no_results; missing category coverage uses category unsupported_search. These do not automatically invalidate the city. Existing partial-success, provider/AI failure, deadline and bounded-execution rules remain in force.
- Separate dynamic ambiguity and resolver-outage tests are superseded, not completed features. General provider/AI failure tests remain required.

FE-04 provides accessible search/autocomplete aligned with the supported mapping. Local suggestions are sufficient and must not claim live verification. Live autocomplete is optional and requires an agreed backend interface before use; no new lookup endpoint is required by BE-03. Suggestions do not guarantee prices or coverage.

## 4. Successful response and required fields

HTTP 200 requires a complete, validated itinerary, even when travel prices are unavailable. No persistence occurs and no saved trip ID is returned.

| Object/field | Required interpretation |
|---|---|
| generation_status | Always complete on HTTP 200; partial is not supported |
| live_integration_status | price_received if at least one valid live flight/hotel offer exists, otherwise no_price |
| trip | City strings match trimmed request text; start_date, return_date and adults match request; nights equals date difference |
| itinerary | Exactly nights + 1 entries, ordered, one per date inclusive |
| travel_options | Both flights and hotels objects always present |
| budget | Original budget (cent-normalized in the inspected BE-03 implementation; see observation above), selected offer IDs, itemized costs, subtotals, projected total, status, missing categories and notes |
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
- Approved on 2026-10-22: the Google Flights adapter uses two separate direction/date searches and combines their actual provider prices into one complete round-trip offer. Do not invent per-leg prices by splitting an aggregate fare. The public scope remains round trip.
- source identifies the actual data service; retrieved_at is the UTC retrieval time, not a guarantee of booking availability. Preserve any older supplier quotation timestamp internally.
- Only offers matching the request's dates, route and passenger/occupancy scope qualify. Arbitrary route-page deals are not eligible.
- Request USD upstream when possible. Non-USD amounts require a documented conversion source/rate/time retained internally before normalization. Without an approved conversion method, exclude the offer from USD-priced results and warn; never relabel GBP as USD.

Each offer has taxes:
- included: additional_amount_usd = 0; the price already includes all known mandatory fees.
- additional_known: additional_amount_usd > 0, the mandatory additional total for all travelers/whole stay or round trip; this amount is NOT already in price.amount_usd.
- unknown: additional_amount_usd = null; fee completeness cannot be established. A known base quote can remain visible, but the budget must disclose missing taxes_fees and cannot claim a complete projected total.
- Where fees are partly known, normalize the known portion into price with internal evidence, then mark remaining fee uncertainty unknown. Never discard known charges.

**Selection rule:** Prefer comparable offers with known fee totals (included/additional_known); choose the lowest base + additional total, tie-break by ID. If all eligible offers have unknown fees, choose lowest known base, warn that this is not a verified cheapest final total. Select exactly one offer per available category, or null when no valid offer exists. Diyar highlights the backend selection and never selects independently. This replaces the provisional v0.3 selection rule in the adopted v0.4 baseline.

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
1. Include exactly one base line for flights and one for accommodation. If no valid selected offer exists, use unknown; this contract does not invent estimates for missing flights/hotels.
2. Provider base lines equal the selected offer's base price. Non-selected alternatives never enter the ledger.
3. Add exactly one provider taxes_fees line for each selected offer with additional_known fees; add one unknown taxes_fees line for each with unknown fees. Included fees require no extra line.
4. Include one activities entry per itinerary activity; preserve its amount/kind and activity_ref. No duplicate activity references. These are whole-group one-occurrence costs, counted once.
5. Include one food and one local_transport entry for the whole trip. Use an estimate only when a reviewed estimation policy exists; otherwise unknown. Do not multiply by days or adults again after normalization.
6. For this contract, provider ledger entries come only from selected flight/hotel quotes and their fees. Activity/food/transport expenses are estimates or unknown. Extra categories or supplier activity offers require a contract revision.
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
- No automatic retry of chargeable AI generation or validation/unsupported-input retries. The team-lead-approved configured-key rotation policy below is an exception to the earlier blanket prohibition on credential failover; it does not authorize duplicate chargeable AI generation. Prevent duplicate submits.
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

## 9. Contract adoption and implementation evidence

Nasrawy approved this public v0.4 integration baseline on 2026-10-27. The fixed 80-city adapter mapping is authoritative; the superseded dynamic resolver, ambiguity and resolver-outage requirements are not acceptance requirements.

The adopted baseline retains:
- Google Flights through the approved RapidAPI service as the mandatory live-price provider, with two real directional searches forming a round-trip offer.
- Fee-aware selection and deterministic BE-04 ledger arithmetic.
- UTC calendar-date input validation and the existing overall deadline/error rules.
- Unknown food/local-transport costs until a separate estimation policy is approved.
- Exclusion of non-USD quotes when no approved conversion method exists.
- Unchanged response fields, authentication requirements, partial-success behavior and no trip persistence during generation.

Contract approval does not certify implementation or attribute individual sign-off to Diyar, Adel or Ziyad. Their frontend/backend/provider verification remains evidence to record against the relevant implementation issues. Existing provider coverage, fee/occupancy evidence and failure-path checks remain required.

BE-03 (#9) / PR #34 still requires one successful, consistent evidence chain using a real Supabase bearer token without overriding authentication: authenticated request → real travel provider → AI → BE-04 budget → HTTP 200 response. Separate authenticated failure and authentication-bypassed success runs do not by themselves satisfy that chain. This documentation approval does not merge PR #34 or close BE-03.

## Team-lead decisions — 2026-10-22

Nasrawy approved the following limited decisions:
- Google Flights through the third-party `google-flights2` RapidAPI service is approved as the flight provider. This is not a direct official Google API.
- Retain two separate provider searches, one for the requested outbound direction/date and one for the return direction/date. Preserve each direction's actual provider price and sum them for the round-trip total; do not split an aggregate fare into invented per-leg amounts.
- Retain configured API-key rotation in the project, including switching to another configured key after quota exhaustion. This supersedes earlier project instructions requiring removal of that mechanism. Existing secret-handling, deadline and bounded-execution requirements remain applicable.
- These searches implement the existing round-trip scope. A public `one_way` option or `trip_type` field is not approved by this decision.
- Provider adoption does not certify passenger coverage, currency or mandatory-fee completeness. Their evidence, exclusion of indicative prices from authoritative budgeting, adapter handoff and integration tests remain required. This is not blanket approval of v0.4 or completion of #17/#18.

## Team-lead decision — 2026-10-25: fixed 80-city baseline

Nasrawy approved the fixed 80-city adapter mapping as the current city-validation baseline, superseding the 2026-10-24 free-text/dynamic resolver amendment. The adapter owns the supported set and its name normalization; BE-03 must reuse it rather than maintain a second allowlist. Dynamic resolver integration, acceptance of cities outside that set, ambiguity handling and resolver-outage tests are superseded scope, not completed features. Live autocomplete is optional and is not a BE-03 completion requirement. Unrelated integration, provider-evidence and contract-adoption gates remain unchanged.

## Team-lead decision — 2026-10-27: public v0.4 adoption

Nasrawy authorized alignment of the contract with the fixed 80-city decision and recording final public integration-contract adoption. This supersedes the earlier Draft/candidate status and the outstanding public contract-adoption gate in the historical notes above. It does not retroactively claim individual developer reviews or provider acceptance.

Section 3 and the JSON Schema use the adapter-owned supported set and name normalization. City text remains a string, unsupported cities return 400 UNSUPPORTED_LOCATION, and identical mapped cities return 422 VALIDATION_ERROR. No new resolver, public lookup endpoint or response fields are introduced. Live autocomplete remains optional.

Implementation acceptance, especially the authenticated live success run for BE-03, remains separate from this contract decision.
