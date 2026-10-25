# TravelMate — Internal Adapter Contracts

**Version:** 0.4 candidate, 2026-10-15.  
**Status:** Proposed handoff for Adel and Ziyad; not a record of their agreement. Public HTTP authority: [api-contracts.md](api-contracts.md).

Adapters are Python module boundaries inside FastAPI, not new HTTP endpoints. Functions may use equivalent Pydantic objects; names below are proposed. The public JSON Schema provides request, offer and day definitions.

## Travel adapter: search_travel

Input (all fields required):
- trip_request: the exact public request object.
- categories: array containing flights, hotels, or both, limited to implemented providers.
- deadline_at: absolute UTC ISO timestamp from Adel's overall deadline.
- request_id: sanitized log correlation ID, never an access token.

Under the approved 2026-10-25 reconciliation, Adel validates city text (trimmed, nonblank, at most 200 characters), dates, adults and budget. Supported locations and name normalization come from the adapter's existing 80-city mapping, not a separate Backend allowlist or dynamic provider location search.

The adapter validates mapped city identities before dependent searches and AI generation, rejecting identical mapped cities with invalid_input for public 422 VALIDATION_ERROR. Preserve trimmed submitted text for the response and provider IDs internally. Queries for flights, hotels and AI must refer to the same intended cities.

An unsupported city produces a top-level unsupported_search for public 400 UNSUPPORTED_LOCATION. Safe field diagnostics are preserved when supplied; public details may be null otherwise. Category-level unsupported_search for coverage limitations and no_results for missing quotes remain distinct from invalid-city rejection. Existing provider/AI failures, partial success, deadline_at and bounded execution remain unchanged.

FE-04 uses suggestions aligned with the approved mapping. Live autocomplete is optional, requires an agreed backend interface, and must keep credentials server-side. Separate resolver integration, ambiguity and resolver-outage tests are superseded, not delivered.

Output:
- flights and hotels: each {status, offers, reason_code}.
- status: available or unavailable; offers use public flight/hotel schema.
- reason_code: null for available; otherwise not_configured, unsupported_search, no_results, rate_limited, timeout, auth_error, provider_error or invalid_response.
- warnings: array of safe {code, message}.
- provenance: array of internal evidence objects, one per returned offer.

Every provenance object contains:
- offer_id: returned offer ID.
- original_currency and original_amount: source base quote before conversion.
- quote_timestamp: nullable provider timestamp.
- conversion: null for USD; otherwise {source, rate_to_usd, converted_at}.
- provider_query: sanitized actual route/destination, dates, adults and room parameters (no headers or keys).
- coverage_evidence: nonempty explanation of group/round-trip/full-stay scope and fee treatment.
- airport_timezones: null for hotels; for flights {departure, destination} with IANA names used to verify local-date matching.

Retain this evidence in sanitized development output; never expose raw credentials or arbitrary supplier payloads to React. Public retrieved_at is assigned at retrieval.

Rules:
- available requires usable offers and reason_code null. unavailable requires [] and a reason.
- Unconfigured optional category is returned explicitly, not silently omitted.
- No fixture substitution. Provider failures become unavailable; no-results is not a reason to rotate keys.
- Currency conversion requires the reviewed policy. All flight/hotel prices are normalized before returning; uncertain occupancy or mismatched dates excludes the offer.
- Known base quotes with unknown taxes may be returned only with taxes.status unknown.
- Apply configured timeout bounded by deadline_at; at most one permitted transient/Retry-After travel retry. Configured-key failover is permitted under the 2026-10-22 team-lead decision below; execution remains bounded by the configured key pool and deadline.
- An unexpected adapter programming failure is caught by orchestration, logged safely and converted to a category warning, subject to successful AI generation.

## AI adapter: generate_itinerary

Input:
- trip_request: public request.
- selected_offers: {flight: flight offer or null, hotel: hotel offer or null}.
- travel_availability: {flights: live/unavailable, hotels: live/unavailable}.
- estimation_policy: {id: string or null, food: string or null, local_transport: string or null}. Null means no approved estimate basis. Descriptions must specify units/group/day coverage.
- deadline_at and request_id as above.

Output is exactly one of:
- Success: {status: "ok", itinerary: day[], ancillary_estimates: {food: estimate_object, local_transport: estimate_object}}.
- Failure: {status: "error", error: {code, message}}.

estimate_object fields are all required:
- amount_usd: nonnegative whole-trip/all-adult number, or null.
- kind: estimate or unknown.
- basis: nonempty methodology or missing-data explanation.
- policy_id: reviewed policy identifier or null.
Unknown means amount and policy_id are null. Estimates require a non-null matching policy_id and explanatory basis; if no policy is approved, both ancillary objects must be unknown. Activity estimates need meaningful descriptions and are always labeled estimates; uncertain amounts stay null.

Success itinerary uses the same day/activity schema as the public response: exactly nights + 1 dates, contiguous order and justified empty travel days. AI may not manufacture provider offers, select different options, calculate authoritative budget totals or return a saved-trip ID.

AI errors: timeout, rate_limited, unavailable, invalid_output. Ziyad parses and validates structured output; Adel independently validates before publishing. Map these to the public error envelope (504, 429, 503, 502 respectively). Do not auto-retry chargeable generation.

## Budget boundary: Adel

Inputs: validated request, normalized travel options, selected offer IDs, validated itinerary and ancillary estimates.

Adel constructs cost_items and applies the public ledger rules. Activity refs connect each cost line to exactly one activity. Provider costs come from selected offers only. AI-supplied subtotals/statuses are ignored.

Frontend receives the completed public result, never the raw internal adapter envelope. Error request_id is added by FastAPI.

## Handoff checklist

- [ ] Adel and Ziyad agree function names/types and validate a normalized sample.
- [ ] Ziyad supplies actual provider provenance, supported mapping and limitations.
- [ ] Diyar confirms the public result matches display needs.
- [ ] Team lead records agreement and provider/estimate decisions under PLAN-02.

## Team-lead decisions — 2026-10-22

Nasrawy approved the following limited decisions:
- Google Flights through the third-party `google-flights2` RapidAPI service is approved as the flight provider. This is not a direct official Google API.
- Retain two separate provider searches, one for the requested outbound direction/date and one for the return direction/date. Preserve each direction's actual provider price and sum them for the round-trip total; do not split an aggregate fare into invented per-leg amounts.
- Retain configured API-key rotation in the project, including switching to another configured key after quota exhaustion. This supersedes earlier project instructions requiring removal of that mechanism. Existing secret-handling, deadline and bounded-execution requirements remain applicable.
- These searches implement the existing round-trip scope. A public `one_way` option or `trip_type` field is not approved by this decision.
- Provider adoption does not certify passenger coverage, currency or mandatory-fee completeness. Their evidence, exclusion of indicative prices from authoritative budgeting, adapter handoff and integration tests remain required. This is not blanket approval of v0.4 or completion of #17/#18.

## Team-lead decision — 2026-10-25: fixed 80-city baseline

Nasrawy approved the fixed 80-city adapter mapping as the current city-validation baseline, superseding the 2026-10-24 free-text/dynamic resolver amendment. The adapter owns the supported set and its name normalization; BE-03 must reuse it rather than maintain a second allowlist. Dynamic resolver integration, acceptance of cities outside that set, ambiguity handling and resolver-outage tests are superseded scope, not completed features. Live autocomplete is optional and is not a BE-03 completion requirement. Unrelated integration, provider-evidence and contract-adoption gates remain unchanged.
