# BE-03 Live Run Evidence — 2026-10-25

## Request

POST /api/v1/trips/generate
Authorization: Bearer <redacted>
Content-Type: application/json

{"departure_city":"Istanbul","destination_city":"Rome","start_date":"2026-12-01","return_date":"2026-12-04","adults":2,"budget_usd":1500}

## Response

HTTP/1.1 503 Service Unavailable
x-request-id: 9cbf731d-4f82-4c7a-804c-3ff5c855bb24

{"error":{"code":"PROVIDER_UNAVAILABLE","message":"The itinerary service is unavailable.","details":null},"request_id":"9cbf731d-4f82-4c7a-804c-3ff5c855bb24"}

## Server log

INFO travelmate.request request method=POST path=/api/v1/trips/generate status=503 duration_ms=552.95 request_id=9cbf731d-4f82-4c7a-804c-3ff5c855bb24

No ERROR line, no traceback.

## Notes

- Real Supabase JWT from a confirmed test account.
- Endpoint verified auth, validated the request, called search_travel (both categories unavailable — no provider keys in .env), then called generate_itinerary (unavailable — no Groq API key).
- Route correctly mapped AI failure to 503 PROVIDER_UNAVAILABLE with standard envelope and matching X-Request-ID header.
- Live end-to-end run through real adapters. Proves the endpoint handles missing provider keys without crashing.
- No tokens, keys, or secrets included.




# BE-03 Success-Path Live Run — 2026-10-26

## Run metadata
- Commit: `7bc77eab29847b797bdd7c6bbdf438244641cf22`
- Branch: `be-03-generate-endpoint`
- Run at: 2026-10-26T17:22:38Z (request), duration 9.72s
- Run by: Ziyad (coordinated with Adel)
- Result: **HTTP 200**, `X-Request-ID: f7ecaba9-ac86-4d6f-91b5-7314cabfa0ff`

## Request (no JWT)
```json
{"departure_city":"Istanbul","destination_city":"Rome","start_date":"2026-12-01","return_date":"2026-12-04","adults":2,"budget_usd":1500}
```

## Response
- Full response JSON in `be03-success-response.json`
- `generation_status`: complete
- `live_integration_status`: price_received
- `itinerary`: 4 days (nights 3 + 1); last day `empty_day_reason` = "Travel day: return flight departs at 09:25"
- `travel_options.flights.status`: live (3 Google Flights offers)
- `travel_options.hotels.status`: live (20 Booking.com offers)
- `budget.selected_flight_offer_id`: `AJet-2026-12-01-SAW-FCO-VF73-1120__Air Serbia-2026-12-04-FCO-IST-JU401+JU426-0925` — same ID as `travel_options.flights.offers[0].id` and the `flights` cost item `source_offer_id`
- `budget.selected_hotel_offer_id`: `248647` — present in offers
- `budget.provider_subtotal_usd`: 574.56
- `budget.projected_total_usd`: null (activities, food, local_transport unknown)
- `budget.status`: uncertain
- `warnings`: []

## Chain (single request, same run)
- 17:22:38 request received
- 17:22:40 Booking destination lookup
- 17:22:41–42 Google Flights (outbound + return)
- 17:22:43 Booking hotel search
- 17:22:43–48 Groq itinerary generation
- 17:22:48 BE-04 budget + 200 response

## Live vs cache
**Live.** Runner used a fresh, empty `TRAVELMATE_HOME` folder. All four provider responses fetched during this run and saved to cache after fetching. Both travel categories are `live`.

## Auth note
`get_current_user_id` was replaced via the `configure_api` hook (no Supabase config on the runner's machine). Routing, validation, adapters, AI, BE-04, error mapping, request IDs, and logging are unmodified PR #34 code.

JWT verification is proven separately by:
- 152 backend tests
- The 503 run in this file (real Supabase JWT)
- BE-02 tests

## Reproduction
Env vars (names only): `GOOGLE_FLIGHTS_RAPIDAPI_KEYS`, `BOOKING_RAPIDAPI_KEYS`, `GROQ_API_KEY`, `GROQ_MODEL=openai/gpt-oss-120b`, `TRAVELMATE_FLIGHT_MODE=live`, `TRAVELMATE_HOME` (optional empty folder), `SUPABASE_JWKS_URL`, `SUPABASE_JWT_ISSUER`, `SUPABASE_JWT_AUDIENCE=authenticated`.

Commands:
```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
curl.exe -i -X POST http://127.0.0.1:8000/api/v1/trips/generate `
  -H "Authorization: Bearer <supabase-access-token>" -H "Content-Type: application/json" `
  --data-binary "@request.json"
```

## Notes
- No JWT, keys, or secrets in this file.
- The 503 run above remains as failure-path evidence.
- The auth substitution is disclosed above and is a limitation of the runner's environment, not a defect in the code.

