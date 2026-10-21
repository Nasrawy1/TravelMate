# TravelMate Adapters – Integration Guide (API-05 #18 / API-04 #17)

Handoff reference for **Adel (BE-03 #9, BE-04 #19)** and **Nasrawy**. It covers the two adapter boundaries in `travalmate.py`:

| Function | Owner | Consumer |
|---|---|---|
| `search_travel(trip_request, ...)` | Ziyad | BE-03 (selection) → BE-04 (`ZiyadReportSlice`, `OfferCandidate`) |
| `generate_itinerary(trip_request, selected_offers, ...)` | Ziyad | BE-03 (public itinerary) → BE-04 (`ActivityItem`, `food`, `local_transport`) |

The output shapes are **validated in the test suite against Adel's merged BE-04 models** (`backend/app/services/models.py`, `budget.calculate_budget`) and against `docs/contracts/api-v0.4.schema.json`. Every example below is a real output of this code unless it is marked *simulated*:
- live flights come from run `evidence/tm-20261021173211-de83be15`;
- hotels and the AI itinerary come from run `evidence/tm-20261021155422-c17533e2`.

Ownership reminders (`docs/api-contracts.md` section 7):
- BE-03 owns orchestration, offer selection and the public response.
- BE-04 owns the authoritative budget.
- The adapters never select final offers for the user, never calculate budget totals and never decide `budget.status`.

---

## 1. Setup

Run every command from the `prototypes/travel-adapter/` folder:

```bash
cd prototypes/travel-adapter
pip install -r requirements.txt          # requests, groq, python-dotenv (+ jsonschema, pydantic for tests)
cp .env.example .env                     # then fill in your own keys (never commit .env)
python test_travelmate_adapters.py       # 95 offline tests, no API quota used
```

- All credentials come from environment variables (`.env.example` lists them, with placeholders only).
- The keys that were previously hardcoded in the script must be **revoked and replaced**.
- The repository `.gitignore` excludes `.env`, `.env.*` (including `.env.bak`) and the local `travelmate_cache.json`, `travelmate_raw_data.json` and `travelmate_final_report.json`.
- A scan of all 45 commits (2026-10-21) found no committed `.env` file and no real key value.

---

## 2. Providers, Endpoints, Limits and Latency

| Category | Provider | Integration type | Endpoint | Observed limits |
|---|---|---|---|---|
| Hotels (**mandatory**) | Booking COM `booking-com15` | RapidAPI third-party (not an official Booking.com API) | `GET /api/v1/hotels/searchHotels` (+ `searchDestination` for unpinned cities) | BASIC plan: **20 requests / month per key** (`x-ratelimit-requests-limit`) |
| Flights (**live**, `TRAVELMATE_FLIGHT_MODE=live`) | Google Flights `google-flights2` | RapidAPI third-party (Google Flights data, not an official Google API) | `GET /api/v1/searchFlights` as a **one-way search per direction** (2 parallel calls for a round trip, 1 for one-way) | BASIC plan: **150 requests / month**, hard limit, separate subscription (`GOOGLE_FLIGHTS_RAPIDAPI_KEYS`) |
| Flights (`indicative` mode only) | Skyscanner Scraper API | RapidAPI third-party (scrapes skyscanner.net route pages) | `GET /v1/skyscanner/route` | Free plan: **20 requests / month per key** |
| Exchange rates | ExchangeRate-API open access | Direct public API, no key | `GET https://open.er-api.com/v6/latest/USD` | Cached 12 h, rejected if older than 48 h |
| AI itinerary | Groq `openai/gpt-oss-120b` (`GROQ_MODEL`) | Direct official API | Chat Completions, JSON mode, `temperature=0.1` | 1,000 requests and 8,000 tokens per minute for this key |

**Latency (measured live on 2026-10-20/21):**

| Call | Measured |
|---|---|
| Groq itinerary (3 nights) | 3,624 / 3,793 / 3,914 / 4,305 / 4,413 / 4,507 ms |
| Booking `searchHotels` | ~2–4 s |
| Google Flights one-way `searchFlights` | 2.4–3 s in probes; up to ~15 s in a full run |
| **Whole request (end to end, live, 60 s deadline)** | **8.8 s and 19.6 s** |
| Old flow, no longer used: `getNextFlights` | 9 s / 23 s / over 30 s |

Each run records the AI value in `ai_itinerary.provenance.latency_ms`.

**Timeouts:**
- travel lookup: 10 s per request (contract default); **Google Flights: 20 s per request, and a timeout is not retried** (a retry would double the wait);
- AI: 35 s per attempt;
- default overall `deadline_at`: now + 60 s.

**Two engine rules protect the deadline:**
- flights and hotels run **in parallel**;
- the travel phase must finish **25 s before `deadline_at`**, so time is always reserved for the AI.

With one-way searches, the 60 s contract default is enough: the two full live runs took **8.8 s and 19.6 s**. The earlier round-trip flow (`getNextFlights`) once took more than 30 s and caused a timeout, which is why it was replaced.

### Live flights: Google Flights capabilities (verified live 2026-10-21, 9 requests used)

| Question | Answer | Evidence |
|---|---|---|
| Searches the requested dates? | **Yes.** | All 63 outbound options departed on 2026-11-20 and all return options on 2026-11-23 |
| Price for all adults? | **Yes, priced by the provider.** | The same flights cost $248 for 1 adult and $495 for 2. Another cost $617 vs $1,556, a ratio of 2.52, so it is a real group fare and not a multiplication |
| One-way search? | **Yes.** Omit `return_date`. | IST → CAI one-way $272 + CAI → IST one-way $223 = **$495**, the same as the round-trip fare. Each option carries its own `booking_token` |
| Honors `currency=USD`? | **Yes.** | The same search with `currency=EUR` returned prices about 0.89× (the market rate). The response has no currency field |
| Departure times? | **Yes, local airport times.** | Converted to UTC with IANA zones (12:15 Istanbul = 09:15Z) and verified against the requested local dates |
| Stops? | Counted from the segments | The provider `stops` field was `0` even for IST → ATH → CAI |
| Taxes? | Included (provider convention: Google shows totals including required taxes and fees) | No tax field. Checked bags are not included (`bags.checked: 0`) |

**How live flights are searched:**
- one **one-way search per direction**, run in parallel with each other and with the hotels;
- each leg keeps its **own real provider total for all adults**, so BE-04 prices the legs directly and nothing is split or invented;
- a round trip uses 2 calls (about 75 searches a month on 150 requests) and a one-way trip uses 1; cached repeats are free;
- the same flight returned several times (different fares or tokens) is kept once, at the cheapest price.

Options that fail any check are excluded and counted in `travel.flights.coverage.<direction>.excluded`: date mismatch, route mismatch (by city airports), `self_transfer` (separate tickets), invalid price, unknown time zone, malformed data, or duplicate.

Summing two one-way tickets can cost more than one round-trip ticket on some routes. The sum is a real, bookable price, and the provenance says so.

### Indicative flights: Skyscanner capabilities

These were verified live on 2026-10-17 and 2026-10-19; `travel.flights.coverage` records them on every indicative run.

| Question | Answer |
|---|---|
| Does it search the requested date? | **No.** It returns 13–16 cached quotes spread over about 12 months. The provider's own `usage_note` says "cached quotes … not a live search". |
| Does it honor `adults`? | **No.** Deep links carry no adult count, so each quote is a **single-adult one-way fare**. |
| Does it honor `currency=USD`? | **No.** Prices come back in GBP and are converted under the conversion policy. |
| Departure times? | Not provided, only the local departure date. Airport time zones are kept in provenance. |
| Taxes? | Skyscanner displays fares inclusive of taxes and carrier charges (provider convention), so `included_in_base: true`. |

**Flight modes (`TRAVELMATE_FLIGHT_MODE`):**
- `disabled` **(default)**:
  - flights are `unavailable` with reason `not_configured`;
  - **no flight provider call is made**;
  - both selected legs are `null`;
  - a `FLIGHTS_UNAVAILABLE` warning is added.

  This default exists because issue #18 says "unsupported precise searches must not supply authoritative trip costs", and BE-04 turns any selected flight into a `provider` cost line.
- `live` (**recommended once PLAN-02 records Google Flights as the flight provider**):
  - Google Flights live round trips in the v0.4 public flight shape (section 3.1);
  - `price_authority: "live_provider_quote"`.
- `indicative` (demos only):
  - quotes are fetched;
  - **only exact-date quotes** are selectable;
  - the price is single-adult quote × travelers (unverified);
  - a `FLIGHT_PRICES_INDICATIVE` warning is added.

  Adopting an alternative date always requires a **new request with a fresh hotel search**.

### Hotel verification

Booking.com honors dates, adults and rooms. An offer is kept **only if** all of these hold:
- `checkinDate` and `checkoutDate` equal the request;
- the provider label states the same nights and adults ("Price for 3 nights, 2 adults");
- the unit count matches the requested rooms whenever the provider states it;
- the property is within 60 km of the canonical city center.

Excluded offers are counted by reason in `travel.hotels.coverage.excluded`.

### Coverage (canonical city labels → provider IDs)

**Supported cities:** Amman, Baghdad, Cairo, Doha, Dubai, Erbil, Istanbul, Jeddah, London, Paris, Riyadh, Rome.
- Airports come from this mapping (always 3 letters), so they are never public fields.
- Cairo's Booking ID `-290692` is pinned (verified 2026-10-17).
- Other Booking IDs are looked up once, verified (type `city`, same country code, same name) and cached for 30 days.
- Any other city returns `unsupported_search` before any provider call.

### Currency conversion policy

- USD amounts are used as-is, and their `conversion` is `null`.
- Other currencies are converted only with live ExchangeRate-API rates at most 48 h old. Provenance then carries `conversion = {source, rate_to_usd, converted_at, rate_timestamp}`.
- If no valid rate exists, the quote is **excluded** and a `CURRENCY_UNAVAILABLE` warning is added.
- There are no hardcoded fallback rates.

---

## 3. Travel Adapter: `search_travel`

```python
from travalmate import search_travel
travel = search_travel(trip_request, categories=("flights", "hotels"), deadline_at=deadline, request_id="req-123")
```

### Input

The exact public request (`docs/api-contracts.md` section 3). `budget_usd` is optional here and ignored by the travel search.

```json
{"departure_city": "Istanbul", "destination_city": "Cairo", "start_date": "2026-11-20", "return_date": "2026-11-23", "adults": 2, "budget_usd": 1500}
```

| Field | Rule |
|---|---|
| `departure_city`, `destination_city` | Supported canonical label (text), and the two must differ |
| `start_date` | `YYYY-MM-DD`, strictly after today's **UTC** date |
| `return_date` | 1–7 nights after `start_date` |
| `adults` | Integer 1–4. Booleans, fractions and numeric strings are rejected |
| `budget_usd` | Number that stays > 0.00 after rounding to cents |
| `trip_type` (optional) | `"round_trip"` (default, the current v0.4 contract) or `"one_way"`. **`one_way` is a proposed contract extension:** v0.4 says "no one-way switch" and requires `return_departure_at`. With `one_way`, only the outbound flight is searched, and `return_date` stays the end of the stay (hotel and itinerary) |

Unknown fields (e.g., `rooms`, `origin`) are rejected as `invalid_input`. Rooms default to 1 internally and are never a public field.

### Output (real, trimmed to the selected hotel)

```json
{
  "request_id": "tm-20261021155422-c17533e2",
  "status": "ok",
  "trip_request": {"departure_city": "Istanbul", "destination_city": "Cairo", "start_date": "2026-11-20", "return_date": "2026-11-23", "adults": 2, "budget_usd": 1500.0},
  "flights": {
    "status": "unavailable", "reason_code": "not_configured", "price_authority": null,
    "selected_outbound_flight": null, "selected_return_flight": null,
    "offers": {"outbound": [], "return": []},
    "alternative_date_offers": {"outbound": [], "return": []},
    "coverage": {}
  },
  "hotels": {
    "status": "available", "reason_code": null,
    "offers": [{"hotel_id": 17410709, "name": "Cairo Nile HK Hotel", "star_rating": 3, "review_score": null, "nights": 3,
                "base_price_usd": 61.75, "taxes_and_fees_usd": 4.0, "total_price_usd": 65.75, "price_per_night_usd": 21.92, "fits_budget": null}],
    "public_offers": [{"id": "17410709", "source": "Booking COM booking-com15 (RapidAPI)", "retrieved_at": "2026-10-21T15:54:24Z",
                       "price": {"amount_usd": 61.75, "kind": "provider", "coverage": "entire_trip_all_travelers"},
                       "taxes": {"status": "additional_known", "additional_amount_usd": 4.0},
                       "name": "Cairo Nile HK Hotel", "area": null, "check_in": "2026-11-20", "check_out": "2026-11-23",
                       "occupancy_adults": 2, "room_qty": 1}],
    "coverage": {"hotels_returned": 20, "eligible": 20, "excluded": {"date_mismatch": 0, "occupancy_mismatch": 0, "...": 0}},
    "destination_mapping": {"dest_id": "-290692", "search_type": "CITY", "source": "pinned_mapping"}
  },
  "report_slice": {
    "flights_data": {"selected_outbound_flight": null, "selected_return_flight": null},
    "hotels_data": ["<the same objects as hotels.offers>"]
  },
  "flight_candidates": [],
  "hotel_candidates": [{"id": "17410709", "base_usd": 61.75, "additional_fees_usd": 4.0, "included_in_base": false}],
  "warnings": [{"code": "FLIGHTS_UNAVAILABLE", "message": "Flight prices are not configured for live search; the flight provider cannot return round-trip prices for all travelers."}],
  "provenance": [{
    "offer_id": "17410709", "category": "hotels", "source": "Booking COM booking-com15 (RapidAPI)", "provider_offer_id": 17410709,
    "retrieved_at": "2026-10-21T15:54:24Z", "cache_status": "refresh",
    "original_currency": "USD", "original_amount": 61.7500000000001, "quote_timestamp": null, "conversion": null,
    "provider_query": {"dest_id": "-290692", "arrival_date": "2026-11-20", "departure_date": "2026-11-23", "adults": "2", "room_qty": "1", "currency_code": "USD", "...": "..."},
    "coverage_evidence": "Provider label 'Price for 3 nights, 2 adults' and 'Hotel room'; check-in 2026-11-20 / check-out 2026-11-23; excludedPrice reported as additional taxes and fees, counted once.",
    "fees": {"status": "additional_known", "included_in_base": false, "additional_fees_usd": 4.0},
    "price_authority": "live_provider_quote", "distance_from_center_km": 0.6, "airport_timezones": null
  }],
  "data_mode": "live"
}
```

> The live evidence file shows `"review_score": 0.0` for this hotel. Booking reports `0` for properties without reviews, and the adapter now maps that to `null` (fix and test added after the run). All other values in the evidence are identical.

**What each part is for:**

| Key | Shape | Use |
|---|---|---|
| `flights` / `hotels` | `{status: available/unavailable, reason_code, ...}` | Category availability (`adapter-contracts.md`). BE-03 maps `available` → public `live` |
| `hotels.offers` = `report_slice.hotels_data` | Exact BE-04 `HotelOffer` (`hotel_id` is an int) | `BudgetInput.selected_hotel` |
| `hotels.public_offers` | v0.4 public `hotel` schema (validated in tests) | Public `travel_options.hotels.offers` |
| `report_slice` | BE-04 `ZiyadReportSlice` without `ai_recommendation_report` | `ZiyadReportSlice.model_validate({**report_slice, "ai_recommendation_report": ...})` |
| `hotel_candidates` / `flight_candidates` | BE-04 `OfferCandidate` (`id` is a str) | `BudgetInput.hotel_candidates` / `flight_candidates` for fee-aware selection |
| `provenance[]` | One entry per offer (contract fields + `fees`) | Internal evidence; never sent to React |

### Offer IDs (one ID per offer, everywhere)

| Offer | ID | Where it appears |
|---|---|---|
| Hotel | `str(hotel_id)`, e.g. `"17410709"` | `public_offers[].id`, `hotel_candidates[].id`, `provenance[].offer_id`, and BE-04 `selected_hotel_offer_id` / `CostItem.source_offer_id` |
| Live one-way trip | the outbound leg ID | `round_trip_offers[].id`, `flight_candidates[].id` |
| Flight leg | `airline-flight_date-origin-destination` | `provenance[].offer_id` |
| Round trip (live and indicative) | `<outbound leg id>__<return leg id>`, the exact synthetic format BE-04 builds, e.g. `"Air Cairo-2026-11-20-IST-CAI__EgyptAir-2026-11-23-CAI-IST"` | `round_trip_offers[].id`, `flight_candidates[].id`, `provenance[].offer_id`, and BE-04 `selected_flight_offer_id` / `source_offer_id` |

There are no other candidate ID fields.

### Fees (`included_in_base`) for both categories

| Case | `OfferCandidate` | Public `taxes` | BE-04 ledger |
|---|---|---|---|
| Hotel, `excludedPrice` = 0 | `included_in_base: true`, `additional_fees_usd: null` | `included`, `0.0` | No fee line |
| Hotel, `excludedPrice` > 0 | `included_in_base: false`, `additional_fees_usd: <amount>` | `additional_known` | One provider `taxes_fees` line, counted once |
| Hotel, fees missing or unconvertible | `included_in_base: false`, `additional_fees_usd: null` | `unknown`, `null` | One unknown `taxes_fees` line, plus a `TAXES_UNKNOWN` warning |
| Flight (live mode) | `included_in_base: true`, `additional_fees_usd: null` | `included`, `0.0` | No fee line |
| Flight (indicative mode) | `included_in_base: true`, `additional_fees_usd: null` | – | No fee line |

`HotelOffer.total_price_usd` is `base + taxes` exactly (BE-04 validator), or `null` when the taxes are unknown. It is **never** base + 0 when the fees are unknown.

### 3.1 Live flights output (real, `evidence/tm-20261021173211-de83be15`)

```json
"flights": {
  "status": "available", "reason_code": null, "price_authority": "live_provider_quote",
  "selected_outbound_flight": {
    "airline": "Air Cairo", "carrier_codes": ["SM"], "origin_airport": "IST", "destination_airport": "CAI",
    "flight_date": "2026-11-20", "requested_date": "2026-11-20", "date_matches_request": true, "days_from_requested_date": 0,
    "is_direct": true, "stops_label": "Direct", "price_per_person_usd": 136.0, "travelers": 2, "total_price_usd": 272.0,
    "quoted_at": "2026-10-21T17:32:15Z", "booking_link": "https://www.google.com/travel/flights?q=Flights%20from%20IST%20to%20CAI%20on%202026-11-20%20one%20way"
  },
  "selected_return_flight": {
    "airline": "EgyptAir", "carrier_codes": ["MS"], "origin_airport": "CAI", "destination_airport": "IST",
    "flight_date": "2026-11-23", "requested_date": "2026-11-23", "date_matches_request": true, "days_from_requested_date": 0,
    "is_direct": true, "stops_label": "Direct", "price_per_person_usd": 111.5, "travelers": 2, "total_price_usd": 223.0,
    "quoted_at": "2026-10-21T17:32:12Z", "booking_link": "https://www.google.com/travel/flights?q=Flights%20from%20CAI%20to%20IST%20on%202026-11-23%20one%20way"
  },
  "offers": {"outbound": ["<up to 3 legs>"], "return": ["<up to 3 legs>"]},
  "round_trip_offers": [
    {"id": "Air Cairo-2026-11-20-IST-CAI__EgyptAir-2026-11-23-CAI-IST", "source": "Google Flights (google-flights2, RapidAPI)",
     "retrieved_at": "2026-10-21T17:32:23Z", "price": {"amount_usd": 495.0, "kind": "provider", "coverage": "entire_trip_all_travelers"},
     "taxes": {"status": "included", "additional_amount_usd": 0.0}, "airline": "Air Cairo / EgyptAir",
     "departure_airport_code": "IST", "arrival_airport_code": "CAI",
     "outbound_departure_at": "2026-11-20T09:15:00Z", "return_departure_at": "2026-11-23T21:20:00Z", "adults": 2},
    {"id": "Air Cairo-2026-11-20-IST-CAI__Air Cairo-2026-11-23-CAI-IST", "price": {"amount_usd": 501.0, "...": "..."}},
    {"id": "EgyptAir-2026-11-20-IST-CAI__EgyptAir-2026-11-23-CAI-IST", "price": {"amount_usd": 542.0, "...": "..."}}
  ],
  "selected_offer": "<round_trip_offers[0]>",
  "schedule": {"outbound": {"flight_numbers": ["SM 304"], "departure_local": "2026-11-20 12:15", "departure_utc": "2026-11-20T09:15:00Z", "stops": 0, "...": "..."},
               "return": {"flight_numbers": ["MS 745"], "departure_local": "2026-11-23 23:20", "...": "..."}},
  "coverage": {"provider_calls": 2, "outbound": {"options_returned": 32, "excluded": {"invalid_price": 3, "duplicate": 0, "...": 0}}, "return": {"...": "..."}}
},
"flight_candidates": [{"id": "Air Cairo-2026-11-20-IST-CAI__EgyptAir-2026-11-23-CAI-IST", "base_usd": 495.0, "additional_fees_usd": null, "included_in_base": true}, "..."]
```

- **The legs carry the real provider prices:** $272 and $223 are each a provider one-way total for both adults. BE-04 receives them in `report_slice.flights_data` and sums them to $495 itself, so nothing is split or invented.
- `price_per_person_usd` is the provider group total divided by the adults. It is informative only; BE-04 uses `total_price_usd`.
- `booking_link` is a Google Flights search link for the leg. The provider's `booking_token` is not a URL; it is stored only as a hash in provenance.
- Each `round_trip_offers[]` item **is the v0.4 public `flight` object** (schema-validated in tests): two valid one-way quotes combined into one round trip, which the contract explicitly allows. BE-03 can pass it straight to `travel_options.flights.offers`.
- For `trip_type: "one_way"`, `selected_return_flight` is `null` and `round_trip_offers[].return_departure_at` is `null`. The latter is outside v0.4 until the contract extension is approved.
- Flight provenance adds per-leg `itinerary` details (flight numbers, local and UTC times, stops, transit airports, duration, checked bags), the actual query parameters for each direction, and `coverage_evidence` that names both leg prices.

### Exact-match vs mismatched flights (indicative mode, *simulated* exact date)

`date_matches_request` is **always computed** as `flight_date == requested_date`, never set by hand. `days_from_requested_date` is signed (+ means later). Only exact-date legs can be selected. Alternative-date legs stay in `alternative_date_offers`, never enter `report_slice` or `flight_candidates`, and are rejected by `generate_itinerary`.

```json
"selected_outbound_flight": {
  "airline": "Turkish Airlines", "carrier_codes": ["TK"], "origin_airport": "IST", "destination_airport": "CAI",
  "flight_date": "2026-11-01", "requested_date": "2026-11-01", "date_matches_request": true, "days_from_requested_date": 0,
  "is_direct": false, "stops_label": "With stops (count and transit airports not provided by provider)",
  "price_per_person_usd": 117.33, "travelers": 2, "total_price_usd": 234.66,
  "quoted_at": "2026-10-12T19:28:00Z", "booking_link": "https://www.skyscanner.net/transport/flights/IST/CAI/..."
},
"alternative_date_offers": {"outbound": [{
  "flight_date": "2026-11-04", "requested_date": "2026-11-01", "date_matches_request": false, "days_from_requested_date": 3,
  "...": "same SelectedFlight fields"
}]},
"flight_candidates": [{"id": "Turkish Airlines-2026-11-01-IST-CAI__Air Cairo-2026-11-05-CAI-IST", "base_usd": 384.0, "additional_fees_usd": null, "included_in_base": true}]
```

Flight provenance adds `conversion: {source, rate_to_usd: 1.33333333, converted_at, rate_timestamp}`, `quote_timestamp`, `transit_airports` and `airport_timezones: {departure: "Europe/Istanbul", destination: "Africa/Cairo"}`.

If no exact-date quote exists for **both** directions:
- `selected_outbound_flight` and `selected_return_flight` are `null`;
- `flight_candidates` is `[]`;
- `reason_code` is `no_results`;
- a `FLIGHTS_UNAVAILABLE` warning says how many alternative dates exist.

As a result, BE-04's `selected_flight_offer_id` is `null`.

---

## 4. AI Adapter: `generate_itinerary`

```python
from travalmate import generate_itinerary
ai = generate_itinerary(trip_request, selected_offers, travel_availability, estimation_policy, deadline_at=deadline, request_id="req-123")
```

### Input

```json
{
  "trip_request": {"departure_city": "Istanbul", "destination_city": "Cairo", "start_date": "2026-11-20", "return_date": "2026-11-23", "adults": 2, "budget_usd": 1500},
  "selected_offers": {"flight": null, "hotel": "<HotelOffer or public hotel offer, or null>"},
  "travel_availability": {"flights": "unavailable", "hotels": "live"},
  "estimation_policy": {"id": null, "food": null, "local_transport": null},
  "deadline_at": "2026-10-21T15:55:22Z",
  "request_id": "tm-20261021155422-c17533e2"
}
```

- `selected_offers.flight` is one of:
  - `{selected_outbound_flight, selected_return_flight, schedule}` (the `flights_data` legs plus the optional `flights.schedule`). Each leg must be an exact-date leg with a consistent flag, cover all adults, and match the requested date for its direction; the return leg is `null` for one-way trips. With `schedule`, the AI receives the real local departure times (e.g., `"outbound_departure_local": "2026-11-20 12:15"`);
  - a v0.4 round-trip offer (`flights.selected_offer`), checked against the requested **local** dates;
  - `null`.
- Ineligible flights are dropped with a `FLIGHT_DATE_MISMATCH_EXCLUDED` warning.
- A hotel whose nights or dates do not match is dropped with a `HOTEL_MISMATCH_EXCLUDED` warning.
- `estimation_policy` follows the contract shape `{id, food, local_transport}`, where `food` and `local_transport` are methodology descriptions. It is used **only** if `id` is listed in `TRAVELMATE_APPROVED_POLICY_IDS`; otherwise both estimates stay `unknown` and an unapproved id gets a `POLICY_NOT_APPROVED` warning.

**Works without travel offers.** With `flight: null` and `hotel: null` the AI still returns a complete itinerary. BE-03 can then answer 200 with `budget.status = "uncertain"` and `live_integration_status = "no_price"`.

### Success output (real, trimmed to 2 days)

```json
{
  "request_id": "tm-20261021155422-c17533e2",
  "status": "ok",
  "itinerary": [
    {"date": "2026-11-20", "empty_day_reason": "Travel day – arrival in Cairo", "activities": []},
    {"date": "2026-11-21", "empty_day_reason": null, "activities": [
      {"order": 1, "name": "Visit the Egyptian Museum", "area": "Tahrir Square",
       "description": "Explore ancient Egyptian artifacts, including the Tutankhamun collection.",
       "cost": {"amount_usd": null, "kind": "unknown", "coverage": null}}
    ]}
  ],
  "ancillary_estimates": {
    "food": {"amount_usd": null, "kind": "unknown", "basis": "No approved estimation policy.", "policy_id": null},
    "local_transport": {"amount_usd": null, "kind": "unknown", "basis": "No approved estimation policy.", "policy_id": null}
  },
  "budget_activities": [
    {"label": "Visit the Egyptian Museum", "kind": "unknown", "amount_usd": null, "activity_ref": {"date": "2026-11-21", "order": 1}, "basis": "AI could not estimate this cost."}
  ],
  "price_explanation": "The selected hotel, Cairo Nile HK Hotel, has a base price of $61.75. Taxes and fees add $4.0, bringing the total hotel cost to $65.75. Flight prices are unavailable, so no flight cost information can be provided.",
  "warnings": [],
  "provenance": {"provider": "Groq", "model": "openai/gpt-oss-120b", "temperature": 0.1, "latency_ms": 4507, "automatic_retries": 0}
}
```

**Validation rules.** Any violation returns `invalid_output` and the itinerary is never published:
- exactly nights + 1 days, in date order;
- days between the first and last need 1–4 activities; the first and last day may be empty only with a non-empty `empty_day_reason`;
- `order` is contiguous from 1 within each day;
- every activity needs a non-empty `name`, `area` and `description`;
- `cost.kind` is **only** `estimate` or `unknown`; `provider` is rejected;
- `unknown` requires `amount_usd: null`;
- the day and activity objects validate against the v0.4 schema (tested).

Two artifacts seen live on 2026-10-21 are normalized, each with an `AI_OUTPUT_NORMALIZED` warning:
- a **blank string** between activity objects is removed;
- a cost `{"amount_usd": null, "kind": "estimate"}` (an estimate with no number) becomes `unknown`. This never invents a value.

Everything else still fails: non-object items, `unknown` with an amount, and negative or non-finite amounts.

**Meal de-duplication.** Meals belong to the food category only:
- the prompt forbids meal-only activities;
- any meal activity (AI category `meal`, or a name matching breakfast/lunch/dinner/restaurant/...) gets cost `{amount_usd: 0, kind: estimate}` with basis "covered by the food category";
- a `MEAL_COST_REASSIGNED` warning is added when an amount was moved.

So meal costs are counted exactly once: in `ancillary_estimates.food` when a reviewed policy exists, otherwise inside the unknown food line.

**`price_explanation`** (kept from the prototype, supplementary only) is dropped, with a `PRICE_EXPLANATION_DROPPED` warning, if it contains any money value that is not in the backend data.

**Failure output.** The code is one of `timeout` | `rate_limited` | `unavailable` | `invalid_output`, which BE-03 maps to 504 / 429 / 503 / 502.

```json
{"request_id": "...", "status": "error", "error": {"code": "invalid_output", "message": "The AI output failed validation and was not published."},
 "diagnostics": {"problems": ["Day 2 activity 1 cost.kind must be 'estimate' or 'unknown' (got 'provider')."]}, "warnings": [], "provenance": {"...": "..."}}
```

- The AI call is made **at most once** (`max_retries=0`).
- It is skipped with `timeout` if fewer than 5 s remain before `deadline_at`.
- `diagnostics` is sanitized internal detail. Do not show it to users.

---

## 5. Feeding BE-04 (tested against `backend/app/services/models.py`)

```python
from app.services.models import BudgetInput, ZiyadReportSlice
from app.services.budget import calculate_budget

slice_ = ZiyadReportSlice.model_validate({**travel["report_slice"], "ai_recommendation_report": ai.get("price_explanation") or ""})
budget = calculate_budget(BudgetInput.model_validate({
    "budget_usd": trip_request["budget_usd"],
    "flights_data": travel["report_slice"]["flights_data"],       # or flight_candidates (not both)
    "selected_hotel": selected_hotel,                              # from hotels.offers, or hotel_candidates (not both)
    "activities": ai["budget_activities"],
    "food": ai["ancillary_estimates"]["food"]["amount_usd"],
    "local_transport": ai["ancillary_estimates"]["local_transport"]["amount_usd"],
}))
```

**Live round trips use BE-04's normal legs path.** Pass `report_slice.flights_data` as-is. BE-04 sums the two real leg totals and builds the same synthetic ID as `round_trip_offers[].id`.

**One-way trips use candidate mode**, because BE-04's legs path needs both legs. Pass `flights_data` with both legs `null` and `"flight_candidates": [<the candidate with id == selected_flight_offer_id>]`. BE-04 prices it once as a `provider` line, with no fee line because `included_in_base` is true.

**Result for live run `tm-20261021173211-de83be15`** (`08_be04_budget_output.json`):

| BE-04 cost line | Amount | `source_offer_id` |
|---|---|---|
| flights (provider) | 495.00 = 272.00 + 223.00 (sum of the two real legs) | `Air Cairo-2026-11-20-IST-CAI__EgyptAir-2026-11-23-CAI-IST` |
| accommodation (provider) | 61.75 | `17410709` |
| hotel taxes and fees (provider) | 4.00 | `17410709` |
| food, local transport | unknown | – |

`provider_subtotal_usd` is **560.75**, and `status` is `uncertain` because food and local transport are unknown without an approved policy.

**Changing the selected flight or hotel requires BE-03 to call `calculate_budget` again** with the new selection, and to call `generate_itinerary` again if the itinerary depends on it. This adds no new UI or endpoint, and the adapters never recalculate on their own.

---

## 6. Unavailability States

| Situation | Adapter output | Warning codes | BE-03 public result |
|---|---|---|---|
| Flights disabled (default) | `flights.status = unavailable`, `reason_code = not_configured`, both legs `null`, `flight_candidates = []` | `FLIGHTS_UNAVAILABLE` | 200, flights `unavailable`, `offers: []` |
| No exact-date flight (indicative mode) | Same, but `reason_code = no_results`; alternatives listed separately | `FLIGHTS_UNAVAILABLE` | 200 |
| No eligible flight in a direction, or one leg's search fails (live mode) | `round_trip_offers = []`, both legs `null`, `reason_code` = `no_results` or the provider error code; never half a round trip | `FLIGHTS_UNAVAILABLE` | 200 |
| No matching hotel | `hotels.status = unavailable`, `reason_code = no_results`, `offers = []`, `hotels_data = []`, `hotel_candidates = []` | `HOTELS_UNAVAILABLE` | 200 |
| Provider failure | `reason_code` = `rate_limited` / `timeout` / `auth_error` / `provider_error` / `invalid_response` / `unsupported_search` | `TRAVEL_RATE_LIMITED`, `TRAVEL_TIMEOUT`, `FLIGHTS_UNAVAILABLE` or `HOTELS_UNAVAILABLE` | 200 (a travel 429 is a warning, not a whole-request 429) |
| No flights **and** no hotels | Both categories unavailable; the AI still returns a full itinerary | Both | 200, `live_integration_status = "no_price"`, `budget.status = "uncertain"` |
| AI fails | `status = error` with an AI code | – | 504 / 429 / 503 / 502 |
| Invalid / unsupported input | `{"status": "error", "error": {"code": "invalid_input" or "unsupported_search", "message"}, "diagnostics": {"fields": [...]}}` | – | 422 / 400 (`UNSUPPORTED_LOCATION`) |

**Warning codes:**
- Contract codes: `FLIGHTS_UNAVAILABLE`, `HOTELS_UNAVAILABLE`, `TRAVEL_RATE_LIMITED`, `TRAVEL_TIMEOUT`, `CURRENCY_UNAVAILABLE`, `TAXES_UNKNOWN`.
- **New codes, documented here for UI review:** `FLIGHT_PRICES_INDICATIVE`, `FLIGHT_DATE_MISMATCH_EXCLUDED`, `HOTEL_MISMATCH_EXCLUDED`, `MEAL_COST_REASSIGNED`, `PRICE_EXPLANATION_DROPPED`, `POLICY_NOT_APPROVED`, `ESTIMATE_UNAVAILABLE`, `AI_UNAVAILABLE`, `AI_OUTPUT_NORMALIZED`.

Errors are always `{code, message}`. Python exception text, stack traces and credentials are never returned.

---

## 7. Retries, Keys and Cache

1. **Cache first:** identical searches are served from `travelmate_cache.json` (12 h) without using quota. Expired entries are never served.
2. **One key per request:** only the first configured key is used. There is **no key rotation or failover inside a request**.
3. **At most one retry** per travel lookup, and only for a transient failure (timeout, connection error, HTTP 5xx) or a `Retry-After` ≤ 10 s that fits `deadline_at`. Auth, validation and unsupported-input errors are never retried.
4. **Local `.env` dead-key pruning** (`TRAVELMATE_PRUNE_DEAD_KEYS=true`, default `false`, local maintenance only):
   - after a quota-exhausted 429 or an auth 401/403, the failing request still fails;
   - then that key is removed from the local `.env`, after writing a backup to `.env.bak`;
   - the next key becomes primary for **later** requests.

   Transient 429s never prune. Deployments without a local `.env` are never modified. **Team-lead confirmation needed:** promoting the next key across runs could be read as the quota bypass that #18 forbids.
5. **Local key rotation** (`TRAVELMATE_LOCAL_KEY_ROTATION=true`, default `false`, **local development only**):
   - a dead key (quota-exhausted 429, or auth 401/403) is removed from `.env`, after writing a `.env.bak` backup;
   - it is archived in `.env.exhausted` with the reason and the quota reset time (from `x-ratelimit-requests-reset`), copy-paste ready so it can be restored later;
   - the **same request continues** with the next key.

   Transient errors never rotate keys, and `provenance.key_slot` records which slot answered. `.env.exhausted` is ignored by git (`.env.*`). **Must stay `false` in shared or deployed environments:** issue #18 forbids rotating keys to bypass provider limits.
6. **No automatic AI retry.**

**Cache concurrency:**
- a thread lock plus a cross-process lock file;
- writes go to a temp file and then `os.replace`, so the cache is never half-written;
- if the lock cannot be taken within 5 s, the request continues without caching.

`save_report=True` only writes `travelmate_final_report.json`. **`save_report=False` does NOT disable cache writes;** use `cache_mode="off"` for that.

---

## 8. FastAPI Integration (BE-00 #15 / BE-03 #9)

The adapters are **synchronous** (blocking HTTP and waits). Never call them directly inside `async def` code on the event loop.

```python
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from travalmate import search_travel, generate_itinerary

app = FastAPI()

@app.post("/internal/trip-plan")
async def trip_plan(request_data: dict):
    deadline = datetime.now(timezone.utc) + timedelta(seconds=60)
    travel = await run_in_threadpool(search_travel, request_data, deadline_at=deadline)
    # ... BE-03 selection here ...
    ai = await run_in_threadpool(generate_itinerary, request_data, selected_offers, availability, None,
                                 deadline_at=deadline)
    ...
```

- The adapters **enforce `deadline_at` themselves**: each HTTP timeout, retry wait and the AI timeout is capped by the time left. `asyncio.wait_for` cannot kill the worker thread, so always pass `deadline_at`.
- A plain `def` endpoint also runs in the thread pool. AnyIO's default pool has about 40 workers, so size the deadline and the pool together.
- This example has not been run against BE-00 here (FastAPI is not installed in this prototype environment). Adel integrates it under BE-03.

---

## 9. Data Mapping Notes (suggestions only)

These are **suggested mappings that require alignment with the project database scope; they are not instructions to create or write tables.** Persistence is out of scope for #17 and #18.

- `report_slice.flights_data` is an **object** with `selected_outbound_flight` and `selected_return_flight`. The full exact-date lists are in `travel.flights.offers.outbound` / `.return`, and alternatives are in `travel.flights.alternative_date_offers`.
- `carrier_codes` belongs to flight legs; `transit_airports` is in the flight provenance entries.
- The prototype's price-ordered hotel tiers were **removed**. Offer selection and budgeting now belong to BE-03 / BE-04.
- React receives only BE-03's public result (v0.4), never this adapter envelope or `provenance`.

---

## 10. Tests and Evidence

```bash
python test_travelmate_adapters.py                  # 95 offline tests (0 API quota)
python test_travelmate_adapters.py --live-evidence  # ONE real run -> evidence/<request_id>/
```

The offline tests use real provider responses recorded on 2026-10-17 (Booking, Skyscanner) and 2026-10-21 (Google Flights) in `tests/fixtures/`, plus explicitly **simulated** failures. When the repository backend and `jsonschema` are present, they also validate outputs against **Adel's BE-04 models / `calculate_budget`** and the **v0.4 JSON Schema**. They cover:
- live flights:
  - two parallel one-way searches;
  - real per-leg provider totals, never multiplied or split;
  - BE-04 pricing the real legs (round trip) and candidate mode (one-way);
  - v0.4 schema compliance;
  - `trip_type` (`one_way`, invalid values);
  - de-duplication and normalization of unpadded dates;
  - local → UTC times, and stops counted from segments;
  - exclusion of date, route, self-transfer and invalid-price options;
  - no half round trip when one leg fails;
  - no retry on a Google timeout;
  - parallel search and the AI time reservation;
- AI normalization of blank items and of estimates without amounts;
- the date-flag rule and the exclusion of mismatched flights;
- `included_in_base` for both categories, and string IDs matching `source_offer_id`;
- `provider` cost kinds rejected, and meal costs de-duplicated;
- itinerary resilience without travel offers;
- `.env` dead-key pruning;
- `invalid_input`, `no_results`, `provider_error`, `rate_limited`, `auth_error`, `timeout` and `invalid_response`;
- malformed or incomplete AI output, and no AI retry;
- redaction and cache concurrency.

| Evidence | Content |
|---|---|
| `evidence/tm-20261021173211-de83be15` (**current, full chain**) | IST → Cairo, 2026-11-20 → 2026-11-23, 2 adults, flight mode `live` (two one-way searches). **Total response: 19.6 s.** **Flights:** real legs SM 304 $272 and MS 745 $223. **Hotels:** 20/20 verified. **AI:** validated, 4,413 ms. **BE-04:** sums the legs to 495.00; provider subtotal 560.75, `uncertain`. |
| `evidence/tm-20261021173058-9506e07a` | Same request, **8.8 s**. Flights and hotels succeeded; the AI output was **rejected** for `{"amount_usd": null, "kind": "estimate"}`, which led to the estimate-without-amount normalization (it validates on offline replay). |
| `evidence/tm-20261021165940-0411d285` | Previous round-trip flow (`getNextFlights`, candidate mode): full chain; same $495 total and BE-04 subtotal 560.75. |
| `evidence/tm-20261021165822-1909eb51` | Same request. Live flights and hotels succeeded; the AI output was **rejected** (`invalid_output`) because of blank strings between activities. That led to the blank-item normalization; the same raw output now validates when replayed offline. |
| `evidence/tm-20261021165616-43271ce8` | Real `timeout` sample from the **previous sequential version**: `getNextFlights` took more than 30 s, so hotels and the AI found no time left. This led to the parallel search and the AI time reservation. |
| `evidence/tm-20261021155422-c17533e2` | Flights `not_configured`; hotels 20/20 and AI validated (4,507 ms); BE-04 `uncertain`. |
| `evidence/legacy-prototype-v1/` | The 2026-10-19/20 runs (first live chain and a real `rate_limited` sample), kept unchanged. They use legacy field names, so do not use them as a contract reference. |

## 11. Known Limitations

- **Flights (live):**
  - two one-way tickets can cost more than one round-trip ticket on some routes (on IST–CAI both were $495);
  - economy class only;
  - checked bags are not included in the price;
  - `one_way` needs a contract extension before BE-03 can expose it.
- **Flights (indicative):** cached, date-independent, single-adult Skyscanner quotes. Demos only.
- **Provider status:** both flight providers are third-party RapidAPI services, not official airline or Google APIs.
- **Hotels:** only the first result page (about 20 properties). `area` is `null` unless Booking's label names a district; `room_qty` is `null` when the provider does not state the unit count.
- **Quota:**
  - Booking: 20 requests/month per key; a hotel search uses 1 (2 for a city without a pinned ID).
  - Google Flights: 150/month; a live round trip uses 2 and a one-way trip uses 1.
- **AI cost estimates:** the AI may mark every activity cost `unknown` (as in the live run). That is valid, but it leaves `activities` in BE-04 `missing_categories`.
