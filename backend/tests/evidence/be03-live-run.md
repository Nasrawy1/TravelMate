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



 ## BE-03 Success-Path Live Run — 2026-10-27

 ## Run metadata

Commit: 45e432be93fb7d97d56b4d20404d4c71d2de9f03

Branch: be-03-generate-endpoint

Run at: 2026-10-27T14:39:39Z, duration 23.0s

Run by: Ziyad (coordinated with Adel)

Result: HTTP 200, X-Request-ID: 7a8d1998-a74f-474c-a266-2ecb0056f647 — same ID in server.log

## Request (no JWT)

{"departure_city":"Istanbul","destination_city":"Rome","start_date":"2026-12-01","return_date":"2026-12-04","adults":2,"budget_usd":1500}

## Response

Full response JSON in be03-success-response.json

generation_status: complete

live_integration_status: price_received

itinerary: 4 days (nights 3 + 1); last day empty_day_reason = "Travel day, flight departs at 09:25 from Rome."

travel_options.flights.status: live — 3 Google Flights offers

travel_options.hotels.status: live — 20 Booking.com offers

budget.selected_flight_offer_id: AJet-2026-12-01-SAW-FCO-VF73-1120__Air Serbia-2026-12-04-FCO-IST-JU401+JU426-0925 — same as offers[0].id and the flights cost item's source_offer_id

budget.selected_hotel_offer_id: 248647 — present in offers

budget.provider_subtotal_usd: 561.2

budget.estimated_subtotal_usd: 70.0 (activity estimates)

budget.projected_total_usd: null (food and local_transport unknown)

budget.status: uncertain

budget.missing_categories: ["food","local_transport"]

warnings: []

## Chain (single request, same run)

14:39:39Z request received

14:39:42Z Booking destination lookup

14:39:48Z Booking hotels

14:39:56Z Google Flights outbound

14:39:57Z Google Flights return

~14:39:57–15:40:02Z Groq itinerary generation

15:40:02Z BE-04 budget + HTTP 200 response (server.log)

 ## Live vs cache

Live. Fresh empty TRAVELMATE_HOME. Provider calls were saved to cache only after fetch (14:39:42, 14:39:48, 14:39:56, 14:39:57). Both travel categories live.

 ## Auth

Real Supabase JWT. create_app() unmodified. No configure_api substitution. This closes the auth gap flagged in the previous review round.

 ## Provider flakiness note

Two prior attempts during the same session returned 502 (AI invalid output) and 200-without-flights (Google Flights return leg exceeded 20 seconds, causing a travel timeout). Both were provider/model variance, not code defects; the route handled them correctly. The successful attempt is documented here   

 ## Reproduction

Env vars (names only): SUPABASE_URL, SUPABASE_JWKS_URL, SUPABASE_JWT_ISSUER, SUPABASE_JWT_AUDIENCE=authenticated, GOOGLE_FLIGHTS_RAPIDAPI_KEYS, BOOKING_RAPIDAPI_KEYS, GROQ_API_KEY, GROQ_MODEL=openai/gpt-oss-120b, TRAVELMATE_FLIGHT_MODE=live, TRAVELMATE_HOME (empty folder).

cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log

In another terminal:

curl.exe -i -X POST http://127.0.0.1:8000/api/v1/trips/generate `
  -H "Authorization: Bearer <supabase-access-token>" `
  -H "Content-Type: application/json" `
  --data-binary "@request.json"

 ## Notes

No JWT, keys, or secrets in this file.

The 503 run above remains as failure-path evidence.

The previous auth-substitution run is superseded by this real-JWT run.
