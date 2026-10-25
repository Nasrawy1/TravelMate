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