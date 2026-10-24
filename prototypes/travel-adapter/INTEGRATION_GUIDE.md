# TravelMate Adapters – Integration Guide (API-05 #18 / API-04 #17)

Handoff reference for **Adel (BE-03 #9, BE-04 #19)** and **Nasrawy**. It covers the two adapter boundaries in **`backend/app/adapters/travelmate.py`** (imported directly by BE-03; `prototypes/travel-adapter/travalmate.py` only loads it for the local CLI, offline tests and evidence):

| Function | Owner | Consumer |
|---|---|---|
| `search_travel(trip_request, ...)` | Ziyad | BE-03 (selection) → BE-04 (`ZiyadReportSlice`, `OfferCandidate`) |
| `generate_itinerary(trip_request, selected_offers, ...)` | Ziyad | BE-03 (public itinerary) → BE-04 (`ActivityItem`, `food`, `local_transport`) |

The output shapes are **validated in the test suite against Adel's merged BE-04 models** (`backend/app/services/models.py`, `budget.calculate_budget`) and against `docs/contracts/api-v0.4.schema.json`. Every example below is a real output of this code unless it is marked *simulated*:
- live flights come from run `evidence/tm-20261024135102-d24ded57` (current code, 2026-10-24);
- hotels and the AI itinerary come from run `evidence/tm-20261021155422-c17533e2`.

Ownership reminders (`docs/api-contracts.md` section 7):
- BE-03 owns orchestration, offer selection and the public response.
- BE-04 owns the authoritative budget.
- The adapters never select final offers for the user, never calculate budget totals and never decide `budget.status`.

---

## 0. Agreed Adapter Contract (Ziyad ↔ Adel, 2026-10-21)

Agreed between Ziyad (API-04/05) and Adel (BE-03/BE-04). The team lead records the adoption under PLAN-02 (#11), and **any later schema change goes back to him before adoption**. The final end-to-end integration test belongs to BE-03 (#9).

**Agreed points**
1. `hotels.offers[].hotel_id` is an **int** (BE-04 `HotelOffer`). The string ID is `hotel_candidates[].id` (`"17410709"`), and it equals BE-04's `selected_hotel_offer_id` and `CostItem.source_offer_id`.
2. `fits_budget` is always `null` from the adapter, because budgeting belongs to BE-04.
3. Warnings are `{code, message}` (`api-contracts.md`).
4. The AI adapter is called as `generate_itinerary(trip_request, selected_offers, travel_availability, estimation_policy, deadline_at=..., request_id=...)` (`adapter-contracts.md`). `deadline_at` and `request_id` are keyword arguments.
5. The AI output contains days `{date, activities, empty_day_reason}` with activities `{order, name, area, description, cost {amount_usd, kind, coverage}}`, `ancillary_estimates {food, local_transport}`, and `budget_activities` in the BE-04 `ActivityItem` shape (passed to `BudgetInput.activities`).

**Invocation agreed for BE-03 (FastAPI):**
- an `async def` endpoint;
- `await run_in_threadpool(search_travel, ..., deadline_at=travel_deadline)` and `await run_in_threadpool(generate_itinerary, ..., deadline_at=deadline)`;
- overall `deadline` = now + 60 s, and `travel_deadline` = `deadline` − 25 s;
- the same `request_id` for both calls;
- the AI `timeout` error maps to 504 `GENERATION_TIMEOUT`.

**Unified JSON example** (real values from `evidence/tm-20261021173211-de83be15`; the full version is `07_final_response.json`, with BE-04's result in `08_be04_budget_output.json`):

```json
{
  "travel_input": {"departure_city": "Istanbul", "destination_city": "Cairo", "start_date": "2026-11-20", "return_date": "2026-11-23", "adults": 2},
  "travel_output": {
    "flights": {"status": "available", "reason_code": null,
      "selected_outbound_flight": {"airline": "Air Cairo", "carrier_codes": ["SM"], "origin_airport": "IST", "destination_airport": "CAI", "flight_date": "2026-11-20", "requested_date": "2026-11-20", "date_matches_request": true, "days_from_requested_date": 0, "is_direct": true, "stops_label": "Direct", "price_per_person_usd": 136.0, "travelers": 2, "total_price_usd": 272.0, "quoted_at": "2026-10-21T17:32:15Z", "booking_link": "https://www.google.com/travel/flights?q=..."},
      "selected_return_flight": {"airline": "EgyptAir", "carrier_codes": ["MS"], "origin_airport": "CAI", "destination_airport": "IST", "flight_date": "2026-11-23", "requested_date": "2026-11-23", "date_matches_request": true, "days_from_requested_date": 0, "is_direct": true, "stops_label": "Direct", "price_per_person_usd": 111.5, "travelers": 2, "total_price_usd": 223.0, "quoted_at": "2026-10-21T17:32:12Z", "booking_link": "https://www.google.com/travel/flights?q=..."}},
    "hotels": {"status": "available", "reason_code": null,
      "offers": [{"hotel_id": 17410709, "name": "Cairo Nile HK Hotel", "star_rating": 3, "review_score": null, "nights": 3, "base_price_usd": 61.75, "taxes_and_fees_usd": 4.0, "total_price_usd": 65.75, "price_per_night_usd": 21.92, "fits_budget": null}]},
    "hotel_candidates": [{"id": "17410709", "base_usd": 61.75, "additional_fees_usd": 4.0, "included_in_base": false}],
    "warnings": []
  },
  "ai_input": {"trip_request": {"departure_city": "Istanbul", "destination_city": "Cairo", "start_date": "2026-11-20", "return_date": "2026-11-23", "adults": 2, "budget_usd": 1500},
    "selected_offers": {"flight": "<selected_outbound_flight + selected_return_flight>", "hotel": "<hotels.offers[0]>"},
    "travel_availability": {"flights": "live", "hotels": "live"},
    "estimation_policy": {"id": null, "food": null, "local_transport": null},
    "deadline_at": "2026-10-21T17:33:11Z", "request_id": "tm-20261021173211-de83be15"},
  "ai_output": {"status": "ok",
    "itinerary": [{"date": "2026-11-21", "empty_day_reason": null, "activities": [{"order": 1, "name": "Egyptian Museum visit", "area": "Tahrir Square", "description": "See the ancient artifacts including Tutankhamun's treasures.", "cost": {"amount_usd": 30.0, "kind": "estimate", "coverage": "all_travelers"}}]}],
    "ancillary_estimates": {"food": {"amount_usd": null, "kind": "unknown", "basis": "No approved estimation policy.", "policy_id": null}, "local_transport": {"amount_usd": null, "kind": "unknown", "basis": "No approved estimation policy.", "policy_id": null}},
    "budget_activities": [{"label": "Egyptian Museum visit", "kind": "estimate", "amount_usd": 30.0, "activity_ref": {"date": "2026-11-21", "order": 1}, "basis": "AI estimate for all travelers (not a provider price)."}]}
}
```

**Updates after the second PR #25 review (2026-10-24), submitted to the team lead for adoption.** BE-04's input (`report_slice`, `BudgetInput`) is unchanged.
1. **Flight IDs name the actual flight.** Adapter IDs are `airline-date-origin-destination-<flight numbers>-<local departure HHMM>` per leg, joined by `__` for a round trip (e.g. `Air Cairo-2026-11-23-IST-CAI-SM304-1215__Air Cairo-2026-11-26-CAI-IST-SM303-0800`). Before this fix, two flights of the same airline, day and route shared one ID, so an offer could carry one flight's price with another flight's times and evidence (the review case: $542 offer, $546 evidence). BE-04 still builds its own synthetic ID from the legs (`Air Cairo-2026-11-23-IST-CAI__Air Cairo-2026-11-26-CAI-IST`); the adapter reports it next to its own ID (`provenance[].be04_flight_offer_id`, `schedule.<direction>.be04_leg_id`), so both link to the same flights. Section 3, "Offer IDs".
2. **Every category is always an object** `{status, reason_code, offers, public_offers, ...}`: a category that was not requested is `unavailable` / `not_requested` (never `null`), `offers` is always an array (`[]` when unavailable), a missing provider key is `not_configured`, and an unexpected error in one category becomes that category's `provider_error` plus a warning, without failing the other category. `flights.offers` / `flights.public_offers` are the v0.4 public round trips (previously `round_trip_offers`); the per-direction BE-04 legs are `flights.legs`.
3. **Backend modules:** `from app.adapters.travelmate import search_travel, generate_itinerary` (or `app.adapters.flights.search_flights`, `app.adapters.hotels.search_hotels`, `app.adapters.ai.generate_itinerary`). Requirements are in `backend/requirements.txt`, settings in `backend/.env.example`, and `backend/tests/test_travel_adapters.py` tests them from the backend path.
4. **Currency:** automatic conversion is **off** until a conversion policy is approved; non-USD prices are excluded with a `CURRENCY_UNAVAILABLE` warning, and unknown fees stay `null` (section 2, "Currency conversion policy").

Unavailability follows section 6: an unavailable category returns `status: "unavailable"` with a `reason_code`, the legs are `null` and the hotel lists are `[]`, and `{code, message}` warnings are added. The AI still returns a full itinerary, so BE-03 answers 200 with `budget.status = "uncertain"` and `live_integration_status = "no_price"`.

---

## 1. Setup

**Backend (BE-03 integration).** The adapters are a normal backend module:

```bash
cd backend
pip install -r requirements-dev.txt      # includes requests, groq, python-dotenv, tzdata for the adapters
cp .env.example .env                     # fill in GROQ_API_KEY, BOOKING_RAPIDAPI_KEYS, GOOGLE_FLIGHTS_RAPIDAPI_KEYS
python -m pytest                         # includes tests/test_travel_adapters.py (offline, 0 API quota)
```

```python
from app.adapters.travelmate import search_travel, generate_itinerary
```

The adapter reads keys from environment variables; `.env` is loaded from `TRAVELMATE_HOME` (default: `backend/`). `TRAVELMATE_HOME` also holds the local cache file.

**Local CLI, full offline suite and evidence** (run from `prototypes/travel-adapter/`; this folder's `.env` is used):

```bash
cd prototypes/travel-adapter
pip install -r requirements.txt          # requests, groq, python-dotenv (+ jsonschema, pydantic for tests)
cp .env.example .env                     # then fill in your own keys (never commit .env)
python test_travelmate_adapters.py       # 121 offline tests, no API quota used
python travalmate.py                     # interactive CLI
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
| Exchange rates | ExchangeRate-API open access | Direct public API, no key | `GET https://open.er-api.com/v6/latest/USD` | **Not called by default** (`TRAVELMATE_FX_CONVERSION=false`). If enabled: cached 12 h, rejected if older than 48 h |
| AI itinerary | Groq `openai/gpt-oss-120b` (`GROQ_MODEL`) | Direct official API | Chat Completions, JSON mode, `temperature=0.1` | 1,000 requests and 8,000 tokens per minute for this key |

**AI model and limits (for the #17 approval):**

| Item | Value |
|---|---|
| Provider / model | Groq, direct official API, `openai/gpt-oss-120b` (`GROQ_MODEL`; changing it needs team-lead approval) |
| Call | One Chat Completions call per itinerary, JSON mode, `temperature=0.1`, `max_completion_tokens=8192` |
| Time | Per-attempt timeout 35 s, capped by `deadline_at`; skipped as `timeout` if less than 5 s are left |
| Retries | **None.** The SDK runs with `max_retries=0`, and the adapter never repeats a chargeable generation |
| Rate limits of the key | 1,000 requests and 8,000 tokens per minute (Groq console). A 429 maps to `rate_limited` |
| Input sent | The validated trip request and the eligible selected offers only (normalized; no keys, no raw provider payloads) |
| Output | Validated before use: exactly nights + 1 dates, ordered activities, justified empty travel days; anything else is `invalid_output` and is never published |
| Measured latency | 3.6 – 4.5 s for 3 nights (table below); 4,529 ms in run `evidence/tm-20261024135102-d24ded57` |

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
| Price for all adults? | **Yes: the group total, priced by the provider.** | See section 2.1 (1 vs 2 adults, provider booking details, website comparison) |
| One-way search? | **Yes.** Omit `return_date`. | IST → CAI one-way $272 + CAI → IST one-way $223 = **$495**, the same as the round-trip fare. Each option carries its own `booking_token` |
| Honors `currency=USD`? | **Yes.** | The same search with `currency=EUR` returned prices about 0.89× (the market rate). The response has no currency field |
| Departure times? | **Yes, local airport times.** | Converted to UTC with IANA zones (12:15 Istanbul = 09:15Z) and verified against the requested local dates |
| Stops? | Counted from the segments | The provider `stops` field was `0` even for IST → ATH → CAI |
| Taxes? | Included (provider convention: Google shows totals including required taxes and fees) | No tax field. Checked bags are not included (`bags.checked: 0`) |

**How live flights are searched:**
- one **one-way search per direction**, **city to city** (all airports of each city, section 2.2), run in parallel with each other and with the hotels;
- each leg keeps its **own real provider total for all adults**, so BE-04 prices the legs directly and nothing is split or invented;
- a round trip uses 2 calls (about 75 searches a month on 150 requests); cached repeats are free;
- the same flight returned several times (different fares or tokens) is kept once, at the cheapest price.

Options that fail any check are excluded and counted in `travel.flights.coverage.<direction>.excluded`: date mismatch, route mismatch (by city airports), `self_transfer` (separate tickets), invalid price, unknown time zone, malformed data, or duplicate.

Summing two one-way tickets can cost more than one round-trip ticket on some routes. The sum is a real, bookable price, and the provenance says so.

### 2.1 Google Flights price meaning and fees (PR #25 review, item 2)

Evidence folder: `evidence/google-flights-price-verification-20261023T065850Z/` (README, requests without keys, raw responses, `summary.json`). Reproduce with `python verify_google_flights_pricing.py IST CAI 2026-11-20 2026-11-23` (6 requests).

| Question | Result |
|---|---|
| Per person or whole group? | **Whole group.** The same flights were searched with 1 and with 2 adults in the same minute. Ratios range from 1.79 to 2.21 across 26 outbound and 33 return flights (e.g., SM 303: $104 vs $226); a per-person price would not change with the count. |
| Is the group total bookable? | The provider's `getBookingDetails` for the 2-adult itinerary returns the airline's own price, equal to the search price (SM 304 $200, SM 303 $226). |
| Taxes and mandatory fees? | Google's help page "What does the total price include?" (support.google.com/faqs/answer/2736504): *"Our prices include standard taxes and fees. The airline may charge additional fees, such as baggage fees."* Checked bags are not included. |
| Website comparison | **Pending:** browser screenshots of the same flights with 1 and 2 adults (steps in the evidence README). If the website disagrees, fees switch to `unknown` and the meaning is confirmed with the API provider before budgeting. |

### 2.2 City-level search and nearby-airport alternatives

Searching only a city's main airport missed cheaper flights from its other airports. For example, Istanbul → Dubai on 2026-11-23 cost $277 from IST, but **$160 from SAW**. The adapter therefore searches **city to city** with the Google city ID, like the website, at **the same number of requests**. Evidence: `evidence/google-flights-city-search-20261023/`.

| Rule | Behaviour |
|---|---|
| Search scope | Google city ID **pinned in code for all 12 cities** (verified live with `searchAirport`, `evidence/google-flights-city-lookup-20261023/`), so no lookup request is spent: Istanbul `/m/09949m`, Cairo `/m/01w2v`, Dubai `/m/01f08r`, Riyadh `/m/0dlm_`, Jeddah `/m/01pk8b`, Doha `/m/0f2yw`, Amman `/m/0c7zf`, Baghdad `/m/01fqm`, Erbil `/m/03n7br`, London `/m/04jpl`, Paris `/m/05qtj`, Rome `/m/06c62`. A city added later without an ID is looked up once, verified (same city name, contains one of our airports) and cached for 30 days; if that fails, its main airport is searched (`coverage.search_scope`). |
| **Main selected flight** | **Always** uses the requested cities' own airports (`SUPPORTED_CITIES[...]["airports"]`, e.g., Istanbul IST + SAW, Dubai DXB + DWC, London LHR + LGW + STN + LTN + LCY + SEN, Paris CDG + ORY, Rome FCO + CIA). It is the cheapest such flight in each direction. |
| Nearby-airport alternative | Google's "Dubai" area also includes **SHJ (Sharjah)** and **AUH (Abu Dhabi)**, and its "Paris" area includes **BVA (Beauvais)**; these are other cities. The label always uses our own city name ("Lands in Beauvais (BVA), not Paris"), not Google's area name. If the cheapest flight through such an airport is **cheaper** than the selected flight, it is reported **only** in `flights.nearby_airport_alternatives.<direction>` and labeled with the real city and airport. It is never selected, never in `flights.offers` / `flight_candidates` / `report_slice`, never sent to the AI, and adds a `NEARBY_AIRPORT_ALTERNATIVE` warning. |

Real example (return Istanbul → Dubai, 2026-11-23, 1 adult):

```json
"selected_return_flight": {"airline": "AJet", "origin_airport": "SAW", "destination_airport": "DXB", "total_price_usd": 148.0, "...": "..."},
"nearby_airport_alternatives": {"outbound": [], "return": [{
  "label": "Alternative: Lands in Sharjah (SHJ), not Dubai",
  "direction": "return", "airline": "Pegasus", "flight_numbers": ["PC 746"],
  "origin_airport": "SAW", "origin_city": "Istanbul", "destination_airport": "SHJ",
  "destination_airport_name": "Sharjah International Airport", "destination_city": "Sharjah",
  "flight_date": "2026-11-23", "departure_local": "2026-11-23 23:00", "stops_label": "Direct",
  "travelers": 1, "total_price_usd": 116.0, "saving_vs_selected_usd": 32.0,
  "price_authority": "live_provider_quote", "eligible": false, "reason": "airport_outside_requested_city",
  "usage": "alternative only; never selected, never sent to BE-04"}]}
```

Adopting an alternative is a user decision: it changes the arrival city, so BE-03 needs a new request.

### Indicative flights: Skyscanner capabilities

These were verified live on 2026-10-17 and 2026-10-19; `travel.flights.coverage` records them on every indicative run.

| Question | Answer |
|---|---|
| Does it search the requested date? | **No.** It returns 13–16 cached quotes spread over about 12 months. The provider's own `usage_note` says "cached quotes … not a live search". |
| Does it honor `adults`? | **No.** Deep links carry no adult count, so each quote is a **single-adult one-way fare**. |
| Does it honor `currency=USD`? | **No.** Prices come back in GBP. With conversion off (default) they are excluded with `CURRENCY_UNAVAILABLE`. |
| Departure times? | Not provided, only the local departure date. Airport time zones are kept in provenance. |
| Taxes? | Skyscanner displays fares inclusive of taxes and carrier charges (provider convention), so `included_in_base: true`. |

**Flight modes (`TRAVELMATE_FLIGHT_MODE`):**
- `disabled` **(default)**:
  - flights are `unavailable` with reason `not_configured`;
  - **no flight provider call is made**;
  - both selected legs are `null`;
  - a `FLIGHTS_UNAVAILABLE` warning is added.

  This default exists because issue #18 says "unsupported precise searches must not supply authoritative trip costs", and BE-04 turns any selected flight into a `provider` cost line.
- `live` (**approved provider: Google Flights**):
  - Google Flights live round trips in the v0.4 public flight shape (section 3.1);
  - `price_authority: "live_provider_quote"`.
- `indicative` (information only):
  - Skyscanner cached quotes are listed under `flights.indicative_quotes`;
  - they are **never selected and never sent to BE-04**, even on an exact-date match (section 3, "Indicative quotes");
  - adopting any shown date requires a **new request with a fresh hotel search**.

### Hotel verification

Booking.com honors dates, adults and rooms. An offer is kept **only if** all of these hold:
- `checkinDate` and `checkoutDate` equal the request;
- the provider label states the same nights and adults ("Price for 3 nights, 2 adults");
- the unit count matches the requested rooms whenever the provider states it;
- the property is within 60 km of the canonical city center.

Excluded offers are counted by reason in `travel.hotels.coverage.excluded`.

### Coverage (canonical city labels → provider IDs)

**Supported cities (80, extended 2026-10-24):** Abu Dhabi, Alexandria, Algiers, Amman, Amsterdam, Ankara, Antalya, Athens, Baghdad, Baku, Bangkok, Barcelona, Basra, Beijing, Beirut, Berlin, Brussels, Budapest, Cairo, Cape Town, Casablanca, Copenhagen, Dammam, Delhi, Doha, Dubai, Dublin, Erbil, Frankfurt, Geneva, Hong Kong, Hurghada, Islamabad, Istanbul, Izmir, Jakarta, Jeddah, Karachi, Kuala Lumpur, Kuwait City, Lahore, Lisbon, London, Los Angeles, Madrid, Male, Manama, Manchester, Marrakesh, Medina, Miami, Milan, Mumbai, Munich, Muscat, Nairobi, Najaf, New York, Paris, Phuket, Prague, Riyadh, Rome, Sarajevo, Seoul, Shanghai, Sharjah, Sharm El Sheikh, Singapore, Stockholm, Sulaymaniyah, Tashkent, Tbilisi, Tokyo, Toronto, Trabzon, Tunis, Vienna, Warsaw, Zurich.
- Aliases are accepted (e.g., `NYC` → New York, `Marrakech` → Marrakesh, `Kuwait` → Kuwait City, `New Delhi` → Delhi). The response uses the canonical label.
- Airports come from this mapping (always 3 letters), so they are never public fields.
- **Flights need no lookup request:** the original 12 cities and multi-airport cities use verified Google city IDs; single-airport cities are searched by their airport code (same flights). How each ID was verified: `evidence/city-table-20261024/README.md`.
- Booking IDs: Cairo `-290692` and Bangkok `-3414440` are pinned. Others are looked up once on first use, verified (type `city`, same country code, same name or alias) and cached for 30 days; that first lookup costs one Booking request. If it cannot be verified, hotels are `unavailable` / `unsupported_search` with a warning, and flights still work.
- Any other city returns `unsupported_search` before any provider call (from both `search_travel` and `generate_itinerary`), with one entry per unsupported field for BE-03's 400 `UNSUPPORTED_LOCATION` details:
  ```json
  {"status": "error", "error": {"code": "unsupported_search", "message": "Unsupported city: Porto."},
   "diagnostics": {"reason": "city_not_in_coverage",
                   "fields": [{"field": "departure_city", "message": "departure_city is not a supported city. Choose one of the supported cities."}],
                   "supported_cities": ["Abu Dhabi", "..."]}}
  ```
- The same city under two names (e.g., `NYC` and `new york`) is `invalid_input` on `destination_city` (422 `VALIDATION_ERROR`).
- UI city list: `sorted(SUPPORTED_CITIES)` from `app.adapters.travelmate` (also returned in `diagnostics.supported_cities`).

### Currency conversion policy

**Changed after the PR #25 review (item 4): conversion is off until the team approves a conversion policy.**
- Both live providers are queried in USD (`currency_code=USD` for Booking, `currency=USD` for Google Flights), and every live price observed so far was USD. USD amounts are used as-is, and their `conversion` is `null`.
- A **non-USD price is excluded** and a `CURRENCY_UNAVAILABLE` warning explains why ("not priced in USD (currency conversion is disabled until a conversion policy is approved)"). No exchange-rate request is made.
- Hotel taxes quoted in another currency are **unknown** (`taxes_and_fees_usd: null`, `taxes.status: "unknown"`, `TAXES_UNKNOWN`), never 0.
- The conversion code is kept behind `TRAVELMATE_FX_CONVERSION=true` (default `false`) for when a policy is approved: live ExchangeRate-API rates at most 48 h old, `conversion = {source, rate_to_usd, converted_at, rate_timestamp}` in provenance, no hardcoded fallback rates.

---

## 3. Travel Adapter: `search_travel`

```python
from app.adapters.travelmate import search_travel
travel = search_travel(trip_request, categories=("flights", "hotels"), deadline_at=deadline, request_id="req-123")
```

`categories` must contain `flights`, `hotels` or both; anything else is `invalid_input`. A category that is not requested is still returned (`unavailable` / `not_requested`).

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

Unknown fields (e.g., `rooms`, `origin`, `trip_type`) are rejected as `invalid_input`. Public requests are **round trips only** (v0.4: "no one-way switch"; PR #25 review, item 3). Rooms default to 1 internally. One-way search exists only as an adapter-internal option (`search_travel(..., trip_type="one_way")`) for a future contract change, and is not exposed publicly.

### Output (real, trimmed to the selected hotel)

```json
{
  "request_id": "tm-20261021155422-c17533e2",
  "status": "ok",
  "trip_request": {"departure_city": "Istanbul", "destination_city": "Cairo", "start_date": "2026-11-20", "return_date": "2026-11-23", "adults": 2, "budget_usd": 1500.0},
  "flights": {
    "status": "unavailable", "reason_code": "not_configured", "price_authority": null,
    "offers": [], "public_offers": [], "selected_offer": null,
    "selected_outbound_flight": null, "selected_return_flight": null, "schedule": null,
    "legs": {"outbound": [], "return": []}, "nearby_airport_alternatives": {"outbound": [], "return": []},
    "indicative_quotes": null, "coverage": {}
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
| `flights` / `hotels` | Always an object: `{status: available/unavailable, reason_code, offers, public_offers, ...}`; `offers` and `public_offers` are `[]` when unavailable | Category availability (`adapter-contracts.md`). BE-03 maps `available` → public `live` |
| `flights.offers` = `flights.public_offers` | v0.4 public `flight` objects (round trips, schema-validated) | Public `travel_options.flights.offers` |
| `flights.legs` | BE-04 `SelectedFlight` options per direction (`outbound`, `return`) | Information; the selected pair is in `report_slice.flights_data` |
| `hotels.offers` = `report_slice.hotels_data` | Exact BE-04 `HotelOffer` (`hotel_id` is an int) | `BudgetInput.selected_hotel` |
| `hotels.public_offers` | v0.4 public `hotel` schema (validated in tests) | Public `travel_options.hotels.offers` |
| `report_slice` | BE-04 `ZiyadReportSlice` without `ai_recommendation_report` | `ZiyadReportSlice.model_validate({**report_slice, "ai_recommendation_report": ...})` |
| `hotel_candidates` / `flight_candidates` | BE-04 `OfferCandidate` (`id` is a str) | `BudgetInput.hotel_candidates` / `flight_candidates` for fee-aware selection |
| `provenance[]` | One entry per offer (contract fields + `fees`) | Internal evidence; never sent to React |

### Offer IDs (one ID per offer, everywhere)

| Offer | ID | Where it appears |
|---|---|---|
| Hotel | `str(hotel_id)`, e.g. `"17410709"` | `public_offers[].id`, `hotel_candidates[].id`, `provenance[].offer_id`, and BE-04 `selected_hotel_offer_id` / `CostItem.source_offer_id` |
| Flight leg | `airline-date-origin-destination-<flight numbers>-<local departure HHMM>`, e.g. `"Air Cairo-2026-11-23-IST-CAI-SM304-1215"` | `schedule.<direction>.leg_id`, `provenance[].itinerary.<direction>.leg_id` |
| Round trip (live) | `<outbound leg id>__<return leg id>`, e.g. `"Air Cairo-2026-11-23-IST-CAI-SM304-1215__Air Cairo-2026-11-26-CAI-IST-SM303-0800"` | `flights.offers[].id`, `selected_offer.id`, `flight_candidates[].id`, `provenance[].offer_id` |
| BE-04 synthetic flight ID | `airline-date-origin-destination` per leg (built by BE-04 from the legs), e.g. `"Air Cairo-2026-11-23-IST-CAI__Air Cairo-2026-11-26-CAI-IST"` | BE-04 `selected_flight_offer_id` / `CostItem.source_offer_id`; reported by the adapter as `provenance[].be04_flight_offer_id` and `schedule.<direction>.be04_leg_id` |

**Why two flight IDs:** BE-04's synthetic ID is not unique (two Air Cairo IST → CAI flights on the same day share it). The adapter ID adds the flight numbers and the local departure time, so an offer's price, times and evidence always belong to the same flights (tests `test_same_airline_same_day_flights_get_distinct_ids`, `test_cheaper_later_flight_brings_its_own_times_and_evidence`, and `flight_offers_match_their_evidence: true` in the live manifest). BE-04 receives one leg per direction in `report_slice.flights_data`, so its synthetic ID still names exactly the selected flights; to link it back, use `provenance[].be04_flight_offer_id`. *Proposal for Adel (optional):* if BE-04 should echo the adapter ID, it can accept it as an optional field; no change is needed for the current integration.

There are no other candidate ID fields.

### Fees (`included_in_base`) for both categories

| Case | `OfferCandidate` | Public `taxes` | BE-04 ledger |
|---|---|---|---|
| Hotel, `excludedPrice` = 0 | `included_in_base: true`, `additional_fees_usd: null` | `included`, `0.0` | No fee line |
| Hotel, `excludedPrice` > 0 | `included_in_base: false`, `additional_fees_usd: <amount>` | `additional_known` | One provider `taxes_fees` line, counted once |
| Hotel, fees missing or unconvertible | `included_in_base: false`, `additional_fees_usd: null` | `unknown`, `null` | One unknown `taxes_fees` line, plus a `TAXES_UNKNOWN` warning |
| Flight (live mode) | `included_in_base: true`, `additional_fees_usd: null` | `included`, `0.0` | No fee line |

`HotelOffer.total_price_usd` is `base + taxes` exactly (BE-04 validator), or `null` when the taxes are unknown. It is **never** base + 0 when the fees are unknown.

### 3.1 Live flights output (real, `evidence/tm-20261024135102-d24ded57`)

```json
"flights": {
  "status": "available", "reason_code": null, "price_authority": "live_provider_quote",
  "offers": [
    {"id": "Air Cairo-2026-11-23-IST-CAI-SM304-1215__Air Cairo-2026-11-26-CAI-IST-SM303-0800", "source": "Google Flights (google-flights2, RapidAPI)",
     "retrieved_at": "2026-10-24T13:51:06Z", "price": {"amount_usd": 352.0, "kind": "provider", "coverage": "entire_trip_all_travelers"},
     "taxes": {"status": "included", "additional_amount_usd": 0.0}, "airline": "Air Cairo",
     "departure_airport_code": "IST", "arrival_airport_code": "CAI",
     "outbound_departure_at": "2026-11-23T09:15:00Z", "return_departure_at": "2026-11-26T06:00:00Z", "adults": 2},
    {"id": "Nile Air-2026-11-23-SAW-CAI-NP192-1605__Air Cairo-2026-11-26-CAI-IST-SM303-0800", "price": {"amount_usd": 422.0, "...": "..."}},
    {"id": "Air Cairo-2026-11-23-IST-CAI-SM304-1215__AJet-2026-11-26-CAI-SAW-VF392-1405", "price": {"amount_usd": 425.0, "...": "..."}}
  ],
  "public_offers": "<the same list as offers>",
  "selected_offer": "<offers[0]>",
  "selected_outbound_flight": {
    "airline": "Air Cairo", "carrier_codes": ["SM"], "origin_airport": "IST", "destination_airport": "CAI",
    "flight_date": "2026-11-23", "requested_date": "2026-11-23", "date_matches_request": true, "days_from_requested_date": 0,
    "is_direct": true, "stops_label": "Direct", "price_per_person_usd": 100.0, "travelers": 2, "total_price_usd": 200.0,
    "quoted_at": "2026-10-24T13:50:53Z", "booking_link": "https://www.google.com/travel/flights?q=Flights%20from%20IST%20to%20CAI%20on%202026-11-23%20one%20way"
  },
  "selected_return_flight": {
    "airline": "Air Cairo", "carrier_codes": ["SM"], "origin_airport": "CAI", "destination_airport": "IST",
    "flight_date": "2026-11-26", "requested_date": "2026-11-26", "date_matches_request": true, "days_from_requested_date": 0,
    "is_direct": true, "stops_label": "Direct", "price_per_person_usd": 76.0, "travelers": 2, "total_price_usd": 152.0,
    "quoted_at": "2026-10-24T13:50:53Z", "booking_link": "https://www.google.com/travel/flights?q=Flights%20from%20CAI%20to%20IST%20on%202026-11-26%20one%20way"
  },
  "schedule": {"outbound": {"leg_id": "Air Cairo-2026-11-23-IST-CAI-SM304-1215", "be04_leg_id": "Air Cairo-2026-11-23-IST-CAI", "flight_numbers": ["SM 304"],
                            "departure_local": "2026-11-23 12:15", "departure_utc": "2026-11-23T09:15:00Z", "stops": 0, "original_amount": 200.0, "...": "..."},
               "return": {"leg_id": "Air Cairo-2026-11-26-CAI-IST-SM303-0800", "be04_leg_id": "Air Cairo-2026-11-26-CAI-IST", "flight_numbers": ["SM 303"],
                          "departure_local": "2026-11-26 08:00", "original_amount": 152.0, "...": "..."}},
  "legs": {"outbound": ["<up to 3 BE-04 legs>"], "return": ["<up to 3 BE-04 legs>"]},
  "nearby_airport_alternatives": {"outbound": [], "return": []},
  "indicative_quotes": null,
  "coverage": {"provider_calls": 2, "search_scope": {"origin": {"search_id": "/m/09949m", "source": "pinned_mapping"}, "destination": {"search_id": "/m/01w2v", "source": "pinned_mapping"}},
               "outbound": {"options_returned": 166, "excluded": {"invalid_price": 27, "duplicate": 1, "...": 0}}, "return": {"...": "..."}}
},
"flight_candidates": [{"id": "Air Cairo-2026-11-23-IST-CAI-SM304-1215__Air Cairo-2026-11-26-CAI-IST-SM303-0800", "base_usd": 352.0, "additional_fees_usd": null, "included_in_base": true}, "..."]
```

- **The legs carry the real provider prices:** $200 and $152 are each a provider one-way total for both adults. BE-04 receives them in `report_slice.flights_data` and sums them to $352 itself, so nothing is split or invented.
- **The selected offer is taken as a whole:** its legs, schedule and provenance are the same flights its ID names, and its price equals the sum of those legs.
- `price_per_person_usd` is the provider group total divided by the adults. It is informative only; BE-04 uses `total_price_usd`.
- `booking_link` is a Google Flights search link for the leg. The provider's `booking_token` is not a URL; it is stored only as a hash in provenance.
- Each `flights.offers[]` item **is the v0.4 public `flight` object** (schema-validated in tests): two valid one-way quotes combined into one round trip, which the contract explicitly allows. BE-03 can pass it straight to `travel_options.flights.offers`.
- Flight provenance adds per-leg `itinerary` details (flight numbers, local and UTC times, stops, transit airports, duration, checked bags), the actual query parameters for each direction, and `coverage_evidence` that names both leg prices.

### Indicative quotes (`indicative` mode): information only

**Changed after the PR #25 review (item 1).** Skyscanner cached single-adult quotes are **never** selected and never become `flight_candidates`, **even when a quote matches the requested date**, so an indicative price can never reach BE-04 as a `provider` cost. In this mode:
- `flights.status` is `unavailable` with `reason_code: "not_configured"`;
- both selected legs are `null` and `flight_candidates` is `[]`;
- the quotes are listed under `flights.indicative_quotes` (`exact_date` / `alternative_dates`, `usage: "information only; never selected, never sent to BE-04"`);
- their provenance entries carry `informational_only: true`;
- a `FLIGHT_PRICES_INDICATIVE` warning is added.

`date_matches_request` is still **always computed** as `flight_date == requested_date` (signed `days_from_requested_date`). The test `test_indicative_price_never_enters_selection_or_budget` proves that an exact-date indicative quote leaves BE-04's flight line `unknown`.

---

## 4. AI Adapter: `generate_itinerary`

```python
from app.adapters.travelmate import generate_itinerary
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

**Live round trips use BE-04's normal legs path.** Pass `report_slice.flights_data` as-is. BE-04 sums the two real leg totals and builds its synthetic ID from the legs; that ID equals `provenance[].be04_flight_offer_id` of the selected offer (the adapter's own `selected_offer.id` adds flight numbers and departure times).

(One-way trips are not public. If the contract adds them later, the internal one-way option prices through BE-04 candidate mode: legs `null` plus `"flight_candidates": [<selected candidate>]`.)

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
| Cheaper flight only via another city's airport (live mode) | Main flight unchanged (requested cities' airports only); the cheaper one is listed in `nearby_airport_alternatives` with its label | `NEARBY_AIRPORT_ALTERNATIVE` | 200; show it as an optional alternative |
| Indicative mode | `flights.status = unavailable`, `reason_code = not_configured`, legs `null`, `flight_candidates = []`; quotes only under `indicative_quotes` | `FLIGHT_PRICES_INDICATIVE` | 200, flights `unavailable` |
| Category not requested (`categories=("hotels",)` or `("flights",)`) | That category is `unavailable` / `not_requested`, `offers = []` (never `null`) | none | 200 |
| Provider key missing | `unavailable` / `not_configured` | `FLIGHTS_UNAVAILABLE` or `HOTELS_UNAVAILABLE` | 200 |
| Unexpected adapter error in one category | That category is `unavailable` / `provider_error`; the other category is unaffected | `FLIGHTS_UNAVAILABLE` or `HOTELS_UNAVAILABLE` | 200 |
| Non-USD price (conversion off) | The offer is excluded; non-USD taxes stay unknown | `CURRENCY_UNAVAILABLE` | 200 |
| No eligible flight in a direction, or one leg's search fails (live mode) | `offers = []`, both legs `null`, `reason_code` = `no_results` or the provider error code; never half a round trip | `FLIGHTS_UNAVAILABLE` | 200 |
| No matching hotel | `hotels.status = unavailable`, `reason_code = no_results`, `offers = []`, `hotels_data = []`, `hotel_candidates = []` | `HOTELS_UNAVAILABLE` | 200 |
| Provider failure | `reason_code` = `rate_limited` / `timeout` / `auth_error` / `provider_error` / `invalid_response` / `unsupported_search` | `TRAVEL_RATE_LIMITED`, `TRAVEL_TIMEOUT`, `FLIGHTS_UNAVAILABLE` or `HOTELS_UNAVAILABLE` | 200 (a travel 429 is a warning, not a whole-request 429) |
| No flights **and** no hotels | Both categories unavailable; the AI still returns a full itinerary | Both | 200, `live_integration_status = "no_price"`, `budget.status = "uncertain"` |
| AI fails | `status = error` with an AI code | – | 504 / 429 / 503 / 502 |
| Invalid / unsupported input | `{"status": "error", "error": {"code": "invalid_input" or "unsupported_search", "message"}, "diagnostics": {"fields": [...]}}` | – | 422 / 400 (`UNSUPPORTED_LOCATION`) |

**Warning codes:**
- Contract codes: `FLIGHTS_UNAVAILABLE`, `HOTELS_UNAVAILABLE`, `TRAVEL_RATE_LIMITED`, `TRAVEL_TIMEOUT`, `CURRENCY_UNAVAILABLE`, `TAXES_UNKNOWN`.
- **New codes, documented here for UI review:** `NEARBY_AIRPORT_ALTERNATIVE`, `FLIGHT_PRICES_INDICATIVE`, `FLIGHT_DATE_MISMATCH_EXCLUDED`, `HOTEL_MISMATCH_EXCLUDED`, `MEAL_COST_REASSIGNED`, `PRICE_EXPLANATION_DROPPED`, `POLICY_NOT_APPROVED`, `ESTIMATE_UNAVAILABLE`, `AI_UNAVAILABLE`, `AI_OUTPUT_NORMALIZED`.

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

   Transient 429s never prune. Deployments without a local `.env` are never modified. Approved by the team lead (PR #25 review).
5. **Local key rotation** (`TRAVELMATE_LOCAL_KEY_ROTATION=true`, default `false`, **local development only**):
   - a dead key (quota-exhausted 429, or auth 401/403) is removed from `.env`, after writing a `.env.bak` backup;
   - it is archived in `.env.exhausted` with the reason and the quota reset time (from `x-ratelimit-requests-reset`), copy-paste ready so it can be restored later;
   - the **same request continues** with the next key.

   Transient errors never rotate keys, and `provenance.key_slot` records which slot answered. `.env.exhausted` is ignored by git (`.env.*`). **Approved by the team lead (PR #25 review)** for local development; keep it `false` in shared or deployed environments.
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
from app.adapters.travelmate import search_travel, generate_itinerary

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
- The adapters are importable from the backend path (`backend/tests/test_travel_adapters.py`). The endpoint and response assembly belong to BE-03 (Adel).

---

## 9. Data Mapping Notes (suggestions only)

These are **suggested mappings that require alignment with the project database scope; they are not instructions to create or write tables.** Persistence is out of scope for #17 and #18.

- `report_slice.flights_data` is an **object** with `selected_outbound_flight` and `selected_return_flight`. The per-direction lists are in `travel.flights.legs.outbound` / `.return`, the public round trips in `travel.flights.offers`, and indicative-mode quotes (information only) in `travel.flights.indicative_quotes`.
- `carrier_codes` belongs to flight legs; `transit_airports` is in the flight provenance entries.
- The prototype's price-ordered hotel tiers were **removed**. Offer selection and budgeting now belong to BE-03 / BE-04.
- React receives only BE-03's public result (v0.4), never this adapter envelope or `provenance`.

---

## 10. Tests and Evidence

```bash
python test_travelmate_adapters.py                  # 121 offline tests (0 API quota)
cd ../../backend && python -m pytest                # backend suite incl. tests/test_travel_adapters.py (0 API quota)
python test_travelmate_adapters.py --live-evidence  # ONE real run -> evidence/<request_id>/
```

The offline tests use real provider responses recorded on 2026-10-17 (Booking, Skyscanner) and 2026-10-21 (Google Flights) in `tests/fixtures/`, plus explicitly **simulated** failures. When the repository backend and `jsonschema` are present, they also validate outputs against **Adel's BE-04 models / `calculate_budget`** and the **v0.4 JSON Schema**. They cover:
- live flights:
  - two parallel one-way searches, city to city (pinned IDs, verified lookup, fallback to the main airport);
  - main flight always from the requested cities' airports; cheaper nearby-airport flights only as labeled alternatives;
  - real per-leg provider totals, never multiplied or split;
  - BE-04 pricing the real legs;
  - v0.4 schema compliance;
  - `trip_type` rejected as a public field (internal one-way option only);
  - indicative quotes never selected or budgeted, even on an exact date;
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
| `evidence/tm-20261021173211-de83be15` (agreed sample, before the flight-ID fix) | IST → Cairo, 2026-11-20 → 2026-11-23, 2 adults, flight mode `live` (two one-way searches). **Total response: 19.6 s.** **Flights:** real legs SM 304 $272 and MS 745 $223. **Hotels:** 20/20 verified. **AI:** validated, 4,413 ms. **BE-04:** sums the legs to 495.00; provider subtotal 560.75, `uncertain`. |
| `evidence/tm-20261024135102-d24ded57` | **Current code (after the second PR #25 review):** Istanbul ↔ Cairo, 2026-11-23 → 11-26, 2 adults, **9.5 s end to end**. 3 flight offers with unique IDs, `flight_offers_match_their_evidence: true`; selected SM 304 $200 + SM 303 $152 = $352; hotels 20/20; AI validated (4,529 ms); BE-04 accepted (`selected_flight_offer_id` = the adapter's `be04_flight_offer_id`, provider subtotal 435.99, `uncertain`). |
| `evidence/tm-20261023142808-0a421e2f` | **Latest full chain with the city-level search:** Istanbul (`/m/09949m`) ↔ Cairo (`/m/01w2v`, verified live), 2 adults, **9.5 s end to end**; flights $200 + $184, hotels 20/20, AI validated, BE-04 accepted. |
| `evidence/google-flights-city-search-20261023` | City-level search: Istanbul IST + SAW, and Dubai's Google area including SHJ / AUH; cheapest $160 from SAW vs $277 from IST; the Sharjah alternative ($116). |
| `evidence/google-flights-price-verification-20261023T065850Z` | **Price meaning check (PR #25 review, item 2):** the same flights with 1 and 2 adults (both directions, within 27 s), the provider booking details for the 2-adult itineraries, and Google's tax statement. Website screenshots still pending (see its README). |
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
- **Flights (indicative):** cached, date-independent, single-adult Skyscanner quotes, shown for information only.
- **Provider status:** both flight providers are third-party RapidAPI services, not official airline or Google APIs.
- **Hotels:** only the first result page (about 20 properties). `area` is `null` unless Booking's label names a district; `room_qty` is `null` when the provider does not state the unit count.
- **Quota:**
  - Booking: 20 requests/month per key; a hotel search uses 1 (2 for a city without a pinned ID).
  - Google Flights: 150/month; a live round trip uses 2.
- **AI cost estimates:** the AI may mark every activity cost `unknown` (as in the live run). That is valid, but it leaves `activities` in BE-04 `missing_categories`.
