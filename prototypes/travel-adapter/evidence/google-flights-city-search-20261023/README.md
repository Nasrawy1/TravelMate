# Google Flights: city-level search and nearby airports (2026-10-23)

Each file holds the request parameters (no API key), HTTP status, rate-limit headers, timing and the raw provider response.

| File | Request | Result |
|---|---|---|
| `01_airport_istanbul.json` | `searchAirport?query=Istanbul` | City ID `/m/09949m` = **IST + SAW** |
| `09_airport_dubai.json` | `searchAirport?query=Dubai` | City ID `/m/01f08r` = DXB, DWC **and SHJ (Sharjah), AUH (Abu Dhabi)**: other cities |
| `08_city_istanbul_to_dxb.json` | `searchFlights` `/m/09949m` → `DXB`, 2026-11-23, 1 adult | 33 options (SAW 4, IST 29); cheapest **$148 / $160 from SAW** vs $277 when searching IST only |
| `10_city_istanbul_to_city_dubai.json` | `searchFlights` `/m/09949m` → `/m/01f08r`, 2026-11-23, 1 adult | 52 options (arrivals DXB 42, **SHJ 10**); cheapest overall **$116 to SHJ**, cheapest to DXB $148 |

**What the adapter does with this:**
1. It searches **city to city** (the Google city ID), like the website. The number of requests stays the same.
2. **The main selected flight always uses the requested cities' own airports:** Istanbul = IST + SAW, Dubai = DXB + DWC.
3. **A cheaper flight through an airport of another city** (e.g., SHJ) is only reported as a separate, labeled alternative: `"Alternative: Lands in Sharjah (SHJ), not Dubai"`. It is never selected, never a BE-04 candidate, never in the report slice, and never sent to the AI.

These responses are also used as offline test fixtures (`tests/fixtures/google_flights_city_*`, `google_flights_search_airport_*`).
