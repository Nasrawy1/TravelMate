# City table extension (2026-10-24)

68 well-known cities were added to `SUPPORTED_CITIES` (80 in total). No lookup request is made at run time for flights.

| File | Content |
|---|---|
| `build_cities.py` | Generator (no API quota): Wikidata (Freebase city ID, city center) + `airportsdata` (time zone, airport city and country) |
| `new_cities.json` | Generated records, with the Wikidata item and how each city was matched |
| `live_sample_check.json` | Google Flights `searchAirport` checks (12 requests) |

**How the search IDs were verified**
1. **Source check:** the Wikidata Freebase IDs equal the 12 Google city IDs that were verified live on 2026-10-21/23 (Baghdad matched by name; its airport points to a district).
2. **Multi-airport cities** (Milan, Stockholm, Bangkok, Tokyo, Seoul, Beijing, Shanghai, New York, Toronto) use the Google city ID, verified live: each ID was returned by Google for that city, and its area lists the city's airports. Exception: Stockholm's area lists ARN and NYO (Nyköping) but not BMA, so Stockholm flights come from ARN. Other-city airports in these areas (BGY Bergamo, NYO Nyköping) can only appear as labeled nearby-airport alternatives.
3. **Single-airport cities** are searched by the airport code itself (same flights, no wrong-area risk). Example: Google's "Alexandria" area lists CAI (Cairo) and the closed ALY, not HBE, so a city search would have been wrong.
4. Kuwait City and Manama were corrected from the country items to the city items (`/m/0fq5j`, `/m/054jj`); Manama's ID was also confirmed live.

**Hotels:** Booking.com IDs are verified on first use (`searchDestination`: type city, same country, same name or alias), then cached for 30 days. Bangkok was verified live (`-3414440`) and pinned.

**Live end-to-end check (2026-10-24, 2 adults, 2026-11-23 → 11-27):** Istanbul → Bangkok (flights 3 offers from $1,199; hotels 20), Riyadh → Sharm El Sheikh (3 offers from $868), Baghdad → Kuala Lumpur (3 offers from $1,778).
