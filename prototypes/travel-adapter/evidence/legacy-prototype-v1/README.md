# Legacy evidence (prototype output v1, superseded)

These two runs were recorded on 2026-10-19/20 with the first secured prototype. They are kept **unchanged** (their `manifest.json` hashes still match) as historical evidence:

| Run | What it proves |
|---|---|
| `tm-20261020001307-906a0090` | First successful live chain: 20/20 Booking.com hotels verified for dates, adults, rooms and location; AI itinerary validated (3,793 ms). |
| `tm-20261019233725-6f31e191` | Real `rate_limited` response (Booking BASIC monthly quota exhausted), handled without key rotation. |

Their JSON uses the **legacy v1 field names** (`outbound_flights`, `eligibility`, `price_per_adult_usd`, budget tiers, `time_of_day` activities, ...). Do not use them as a contract reference. The current adapter shape is in `../../INTEGRATION_GUIDE.md`, and the current evidence is in the sibling `tm-*` folders under `evidence/`.
