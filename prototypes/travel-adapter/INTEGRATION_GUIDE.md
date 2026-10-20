# TravelMate Adapters – Integration Guide


---

## 1. Setup

Run every command from the `prototypes/travel-adapter/` folder:

```bash
cd prototypes/travel-adapter
pip install -r requirements.txt          # requests, groq, python-dotenv
cp .env.example .env                     # then fill in your own keys (never commit .env)
python test_travelmate_adapters.py       # offline tests, no API quota used
```

- All credentials come from environment variables (see `.env.example`). Nothing is hardcoded.
- **The keys that were previously hardcoded in the script must be revoked and replaced** in the RapidAPI and Groq dashboards.
- The repository `.gitignore` excludes `.env` files and the local `travelmate_cache.json`, `travelmate_cache.json.lock`, `travelmate_raw_data.json` and `travelmate_final_report.json` files, so they are never committed.

---

## 2. Providers, Endpoints and Limits

| Category | Provider | Integration type | Endpoint | Access / limits (observed) |
|---|---|---|---|---|
| Hotels (**mandatory**) | Booking COM `booking-com15` | RapidAPI third-party (not an official Booking.com API) | `GET /api/v1/hotels/searchDestination`, `GET /api/v1/hotels/searchHotels` | RapidAPI key. BASIC plan: **20 requests / month per key**, observed via `x-ratelimit-requests-limit` on 2026-10-19 |
| Flights (optional) | Skyscanner Scraper API | RapidAPI third-party (scrapes skyscanner.net route pages) | `GET /v1/skyscanner/route` | RapidAPI key. Free plan: **20 requests / month per key**, observed 2026-10-19 |
| Exchange rates | ExchangeRate-API open access | Direct public API, no key | `GET https://open.er-api.com/v6/latest/USD` | No key. Rates are cached 12 h and rejected if older than 48 h |
| AI itinerary | Groq, model `openai/gpt-oss-120b` (`GROQ_MODEL`) | Direct official API | Chat Completions, JSON mode, `temperature=0.1` | Groq key. One attempt per request, `max_retries=0`. Latency and `x-ratelimit-*` headers are recorded in `ai_itinerary.provenance` |

**AI latency (measured live 2026-10-20, run `tm-20261020001307-906a0090`):**
- **3,793 ms** for a 3-night itinerary (1,111 prompt tokens + 1,438 completion tokens).
- Groq limits observed for this key and model: 1,000 requests and 8,000 tokens per minute. That is roughly 3 itinerary calls per minute before token throttling.
- Every run records its latency in `ai_itinerary.provenance.latency_ms`. The AI call timeout is `min(60 s, time left before deadline_at)`.

### Flight endpoint capabilities (important)
Verified with live responses on 2026-10-17 and 2026-10-19 (`flights_data.coverage` records this on every run):

| Question | Answer |
|---|---|
| Does it search the requested date? | **No.** It returns ~13-16 cached quotes spread over ~12 months (provider `usage_note`: "cached quotes … not a live search"). |
| Does it honor `adults`? | **No.** Deep links carry no adult count, so each quote is treated as a **single-adult one-way fare**. |
| Does it honor `currency=USD`? | **No.** Prices come back in GBP and are converted under the conversion policy. |
| Departure times? | Not provided. Only the local departure date. Time zones come from the airport table (`origin_timezone`, `destination_timezone`). |
| Transit airports? | Usually not provided (single leg even when `direct=false`). Shown as "count not provided by provider". |

So:
- Only **exact-date** quotes are eligible (`outbound_flights`, `return_flights`). Other dates go to `alternative_date_flights` and are **never** used in calculations.
- Every flight price has `price_authority: "indicative"` and `group_price_verified: false`. `group_total_usd = price_per_adult_usd × adults` is an unverified estimate for adults > 1.
- **Adopting an alternative date requires a new request**, with a fresh hotel search and fresh calculations.

### Hotel verification
Booking.com honors dates, adults and rooms. Each offer is kept **only if**:
- `checkinDate` and `checkoutDate` equal the request.
- The provider label states the same nights and adults ("Price for 3 nights, 2 adults").
- The unit count matches `rooms` whenever the provider states it.
- The property is within 60 km of the canonical city center.

Price = `grossPrice + excludedPrice` (taxes and fees not included in the gross price), so known fees are counted exactly once. Missing or unconvertible taxes give `taxes_status: "unknown"` and `total_price_usd: null`, **never 0**.

### Coverage (canonical city → provider ID)
Supported cities: Amman, Baghdad, Cairo, Doha, Dubai, Erbil, Istanbul, Jeddah, London, Paris, Riyadh (`SUPPORTED_CITIES`).
- Cairo's Booking ID (`-290692`) is pinned (verified 2026-10-17).
- Other IDs are looked up once, verified (type `city`, same country code, same name) and cached for 30 days.
- Any other city returns `unsupported_search` without calling a provider.

### Currency conversion policy
- USD amounts are used as-is.
- Other currencies are converted only with live ExchangeRate-API rates (at most 48 h old). Each converted offer records `rate_per_usd`, `rate_source`, `rate_timestamp` and `rate_retrieved_at` in `provenance.currency_conversion`.
- If no valid rate exists, the quote is **excluded** and a warning is added. There are no hardcoded fallback rates.

---

## 3. Adapter Functions

```python
from travalmate import run_travelmate_engine, search_travel, generate_itinerary

# Full pipeline (validation -> search_travel -> subtotals -> generate_itinerary). Never raises.
result = run_travelmate_engine(request_data, deadline_at=deadline, request_id="req-123")

# Travel adapter only: both category objects, normalized offers, provenance. Never raises.
travel = search_travel(trip_request, deadline_at=deadline, request_id="req-123")

# AI adapter only. Never raises; the AI is called at most once.
itinerary = generate_itinerary(trip_request, selected_offers, travel_availability,
                               estimation_policy=None, deadline_at=deadline, request_id="req-123")
```

| Argument | Meaning |
|---|---|
| `deadline_at` | Absolute deadline (aware datetime or ISO-8601 string; naive values are treated as UTC). Default: now + 90 s. Every HTTP attempt, retry wait and the AI call must fit inside it. |
| `request_id` | Correlation ID returned in every response and written to logs. |
| `selected_offers` | `{"outbound_flight": offer, "return_flight": offer, "hotel": offer}` taken from `search_travel` results. Ineligible offers (e.g., alternative dates) are dropped before the AI call. |
| `estimation_policy` | `{"policy_id": "...", "food_usd_per_person_per_day": n, "local_transport_usd_per_person_per_day": n}`. Used only if `policy_id` is listed in `TRAVELMATE_APPROVED_POLICY_IDS`; otherwise food and transport are `"unknown"`. |
| `save_report` | `True` writes `travelmate_final_report.json`. **It only controls the report file. It does NOT disable the local provider cache.** |
| `cache_mode` | `"default"` (read and write cache), `"refresh"` (skip reads, still write), `"off"` (no cache reads or writes). |

**Changing the selected flight or hotel requires backend recalculation.** Call the backend budget logic, and `generate_itinerary` if the itinerary depends on it, with the new selection. No new UI or endpoint is involved; the adapter never recalculates on its own.

---

## 4. Request Payload

```json
{
    "trip_type": "round_trip",
    "origin": "IST",
    "destination_city": "Cairo",
    "check_in_date": "2026-11-19",
    "check_out_date": "2026-11-22",
    "adults": 2,
    "budget_usd": 1500
}
```

| Field | Rule |
|---|---|
| `trip_type` | `"one_way"` or `"round_trip"` |
| `origin` | Exactly 3 letters (`^[A-Za-z]{3}$`). Must not be an airport of the destination city |
| `destination_city` | Text (letters, spaces, `-`, `'`, `.`), 2–80 characters. Must be a supported city, otherwise `unsupported_search` |
| `check_in_date` | `YYYY-MM-DD`, today (server-local date) or later. Also the outbound flight date |
| `check_out_date` | `YYYY-MM-DD`, strictly after `check_in_date`, maximum 30 nights. Also the return flight date |
| `adults` | Integer 1–30 (booleans rejected) |
| `budget_usd` | Number that stays > 0.00 after rounding to cents (NaN / Infinity rejected) |
| *(internal)* `destination_airport` | Optional, 3 letters, must belong to the city. Default: the city's main airport |
| *(internal)* `rooms` | Optional integer 1–30, ≤ adults. Default 1 |

Everything is validated **before** any external call.

---

## 5. Response Structure (`run_travelmate_engine`)

Every key is always present (empty value when not applicable).

| Key | Content |
|---|---|
| `status` | `"success"` (mandatory hotel category available) or `"error"` |
| `request_id`, `generated_at`, `message`, `warnings` | Metadata. `warnings` are user-safe strings |
| `error` | `null` or the error envelope (section 6) |
| `data_mode` | `"live"`, `"includes_cached"` or `"stale_cache_fallback"` (stale data is always labeled) |
| `search_parameters` | Validated **public** fields + `nights`, `currency` |
| `travel_availability` | `{mandatory_category, flights: {status, reason, price_authority, error}, hotels: {...}}`. Status: `available` / `no_results` / `unavailable` / `error` |
| `flights_data` | **Object** with `outbound_flights` and `return_flights` arrays (eligible exact-date offers), `alternative_date_flights` `{outbound: [], return: []}` (NOT eligible), plus `capabilities`, `limitations`, `coverage` |
| `hotels_data` | Array of eligible hotel offers, with `tier_code`, `tier_name`, `tier_basis` and `fits_budget` (`true` / `false` / `null` when taxes are unknown) |
| `hotels_coverage` | Counts of returned, eligible and excluded offers by reason |
| `budget_summary` | `basis` (`flight_plus_hotel` or `hotel_only_flight_price_unavailable`), `flight_subtotal_usd`, price authorities, `scope_note` |
| `budget_tiers_within_limit` | Tiers that fit the budget: `flight_subtotal_usd`, `hotel_total_usd`, `flight_hotel_subtotal_usd`, `remaining_after_flight_hotel_usd` (or `remaining_after_hotel_only_usd` when no eligible flight exists), `subtotal_is_indicative` |
| `budget_tiers_excluded` | Tiers excluded with `reason` (`exceeds_budget`, `no_hotels_in_tier`, `only_unknown_tax_hotels`) |
| `selected_offers` | Prototype default selection (cheapest eligible flights + best-rated tier hotel within budget). Backend may override |
| `ai_itinerary` | `{status, itinerary, ancillary_estimates, error, provenance}`. `itinerary` has exactly nights + 1 ordered days; it is `null` whenever validation failed |
| `ai_recommendation_report` | Supplementary AI price explanation. It is dropped (empty string) if it contains any money value not present in the backend data |
| `provenance` | Sanitized request-level provenance per provider: endpoint, actual query parameters, `retrieved_at`, `cache_status`, HTTP status, key slot number (never the key), rate-limit headers |

Each **offer** also carries its own `offer_id`, `eligibility` (checks performed), `price_authority` and `provenance` (provider, integration type, retrieval time, provider offer ID, currency conversion evidence).

**Hotel tiers are based on price ordering only.** Hotels are sorted by total price and split into 4 equal bands: D (cheapest) → C → B → A. Stars and ratings only choose the representative hotel inside a band.

---

## 6. Error Envelope

```json
{"code": "rate_limited", "message": "The provider rate limit was reached. Please try again later.",
 "category": "hotels", "retryable": true, "retry_after_seconds": null,
 "details": {"reason": "http_429", "provider_message": "...", "http_status": 429}}
```

| `code` | Meaning |
|---|---|
| `invalid_input` | Request failed validation. `details.fields = [{field, message}]` |
| `unsupported_search` | Valid input outside coverage, or provider rejected the parameters (HTTP 400/404/422) |
| `no_results` | Provider answered but no offer matched dates / destination / occupancy |
| `rate_limited` | HTTP 429 or quota exhausted (`details.provider_message` says which) |
| `timeout` | `deadline_at` reached, or provider / AI timed out |
| `auth_error` | Missing, invalid or unsubscribed key (HTTP 401/403) |
| `invalid_response` | Non-JSON or unexpected provider structure |
| `provider_failure` | Provider 5xx, connection failure or hidden error in a 200 response |
| `unavailable` | Category disabled, AI not configured or AI provider unreachable |
| `invalid_output` | AI output failed schema or semantic validation; it is never published |
| `internal_error` | Unexpected bug. Generic message only (details in the server log, with credentials redacted) |

The HTTP status mapping is owned by BE-03 (#9). Messages and details are built by the adapter and never contain Python exception text, stack traces or credentials.

### Retries, keys and cache
1. **Cache first:** identical searches are served from `travelmate_cache.json` (12 h) without using quota.
2. **Transient failures** (timeout, connection error, HTTP 5xx): 1 retry with backoff, only if it fits the deadline.
3. **HTTP 429 with `Retry-After` ≤ 10 s:** waited once, only if it fits the deadline.
4. **Next key** only after `auth_error` (a misconfigured key). Moving to the next key on an exhausted quota happens only with `TRAVELMATE_KEY_ROTATION_ON_QUOTA=true`. **Default is false**, because issue #18 forbids rotating keys to bypass limits. With one key configured, the adapter runs in single-key mode.
5. **Stale cache fallback** (`TRAVELMATE_ALLOW_STALE_CACHE_FALLBACK=true`, default false): an expired cached response up to 7 days old can be served after rate_limited / timeout / provider_failure, always labeled `cache_status: "stale_fallback"`.
6. **AI generation is never retried automatically.**

**Cache concurrency:** reads and writes are serialized by a thread lock plus a cross-process lock file (`travelmate_cache.json.lock`). Writes go to a temp file and then `os.replace`, so the cache is never half-written. Concurrent writers merge entries; if the lock cannot be taken within 5 s, the request continues without caching.

---

## 7. FastAPI Integration (BE-00 #15 / BE-03 #9)

The adapters are **synchronous** (blocking HTTP plus waits). Never call them directly inside `async def` code on the event loop. Two safe options:

```python
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from travalmate import run_travelmate_engine

app = FastAPI()
REQUEST_BUDGET_SECONDS = 90

# Option A: plain "def" endpoint -> FastAPI runs it in its worker thread pool automatically
@app.post("/internal/trip-plan")
def trip_plan_sync(request_data: dict):
    deadline = datetime.now(timezone.utc) + timedelta(seconds=REQUEST_BUDGET_SECONDS)
    return run_travelmate_engine(request_data, deadline_at=deadline)

# Option B: "async def" endpoint -> push the blocking call to the thread pool explicitly
@app.post("/internal/trip-plan-async")
async def trip_plan_async(request_data: dict):
    deadline = datetime.now(timezone.utc) + timedelta(seconds=REQUEST_BUDGET_SECONDS)
    return await run_in_threadpool(run_travelmate_engine, request_data, deadline_at=deadline)
```

- The **adapter itself enforces `deadline_at`**: each HTTP timeout, retry wait and the AI timeout is capped by the time left. `asyncio.wait_for` around `run_in_threadpool` can stop waiting but cannot kill the thread, so always pass `deadline_at`.
- The default thread pool (AnyIO) has ~40 workers. Each request can block a worker for up to the deadline, so size `REQUEST_BUDGET_SECONDS` and the pool together.
- Map `result["status"]` / `result["error"]["code"]` to HTTP responses in BE-03. The adapter does not choose HTTP codes.
- Keep `save_report=False` (the default) on the server.
- This example has not been run in this repository (FastAPI is not installed here). Adel should adapt it to the BE-00 structure.

---

## 8. Database – Suggested Mapping (needs alignment with the project DB scope)

These four tables are **suggested mappings only, not instructions to create tables**. Align them with the project database scope first.

| Suggested table | Source in response | Notes |
|---|---|---|
| `searches` | `request_id`, `search_parameters`, `status`, `error.code`, `data_mode`, `generated_at`, `budget_summary` | One row per call |
| `flight_options` | `flights_data.outbound_flights` and `flights_data.return_flights` (both arrays inside the `flights_data` **object**); optionally `alternative_date_flights` with `eligible = false` | Use the `direction` field. `transit_airports` and `carrier_codes` are lists (store as JSON/text). Keep `price_authority` and `provenance` |
| `hotel_options` | `hotels_data` | Keep `taxes_status` (unknown ≠ 0), `tier_code` (price ordering), `fits_budget`, `provenance` |
| `budget_tiers` | `budget_tiers_within_limit` | Link through `hotel_offer_id` and the flight offer IDs. Values are flight-plus-hotel subtotals, not authoritative totals |

- Use UTF-8 / `utf8mb4` text, since some hotel names are Arabic.
- `ai_itinerary.itinerary` (days → activities) can be stored as JSON. Persistence itself is out of scope for #17 and #18.

---

## 9. Frontend Mapping

| UI element | Source |
|---|---|
| Error / warning banners | `error.message`, `error.details.fields[]` (field-level errors), `warnings[]` |
| Flight cards | `flights_data.outbound_flights` / `return_flights`. Show an **"Indicative price"** badge (`price_authority`) and "Price per adult × adults (unverified)" when `group_price_verified` is false |
| "Other dates" panel | `flights_data.alternative_date_flights`. Must be visibly separate. Choosing one means **starting a new search** |
| Hotel cards | `hotels_data`: `name` (use `dir="auto"`), `star_rating`, `review_score`, `distance_from_center_km`, `total_price_usd` (show "Taxes unknown" when `taxes_status == "unknown"`), `photo_url` |
| Budget comparison table | `budget_tiers_within_limit`. Label columns "Flight + hotel subtotal" and "Remaining after flight + hotel", and show `budget_summary.scope_note` |
| Itinerary | `ai_itinerary.itinerary` (only when `ai_itinerary.status == "success"`); `ancillary_estimates` shown as estimates / "unknown" |
| Price explanation | `ai_recommendation_report` (Markdown/text, hide when empty) |

Do not recalculate any amount in the frontend.

---

## 10. Tests and Evidence

```bash
python test_travelmate_adapters.py                  # 60 offline tests
python test_travelmate_adapters.py --live-evidence  # ONE real run -> evidence/<request_id>/
```

- **Offline tests** use real provider responses recorded on 2026-10-17 (`tests/fixtures/`), plus explicitly **simulated** failures. They cover:
  - invalid_input, no_results, provider_failure, rate_limited, auth_error, timeout and invalid_response
  - key rotation rules and Retry-After handling
  - date / occupancy / destination mismatches
  - negative / NaN / Infinity prices, unknown taxes and the currency policy
  - malformed / incomplete AI output and no automatic AI retry
  - estimation policies, credential redaction, and cache concurrency
- **Live evidence** writes `01_inputs → 02_raw_provider_data → 03_normalized_context → 04_ai_input → 05_ai_raw_output → 06_validated_ai_output → 07_final_response` from the same run, plus a `manifest.json` with SHA-256 hashes and chain checks. The run aborts if any credential pattern is found in the files.
- **Live evidence runs:**
  - `evidence/tm-20261020001307-906a0090` (**successful chain**): IST → Cairo round trip, 2026-11-19 → 2026-11-22, 2 adults, 1 room, $1,500.
    - Hotels: 20 of 20 verified for dates, adults, rooms and location (live, Booking key slot #1, single attempt).
    - Flights: fetched live; no exact-date quote, alternatives kept separate and converted from GBP.
    - AI itinerary: 4 days, validated, 3,793 ms.
    - No key rotation during the run.
  - `evidence/tm-20261019233725-6f31e191` (real failure sample): the hotel search stopped with `rate_limited` (Booking BASIC plan monthly quota exhausted) and the adapter did not rotate keys.

## 11. Known Limitations / Blockers
- **Flights:** indicative cached quotes only. Exact-date matches are rare, and multi-adult pricing is unverified. Not suitable as authoritative trip cost.
- **Hotels:** only the first result page (about 20 properties). Rooms are verified only when Booking states the unit count.
- **Quota:** free RapidAPI plans allow 20 requests/month per key, and one full round trip uses 3–4 requests (one more for a city without a pinned ID).
- **AI meals as activities:** the AI may list meals (e.g., "Dinner at a local restaurant") as activities with cost estimates. Those then count toward the activity estimate even though food is `unknown` without an approved policy. This is not yet blocked; see the API-04 follow-up.
