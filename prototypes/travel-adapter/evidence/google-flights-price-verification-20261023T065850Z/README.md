# Google Flights price meaning: verification (PR #25 review, item 2)

**Run:** 2026-10-23, 06:58:55Z → 06:59:22Z (all six requests within 27 seconds, so prices are comparable).
**Script:** `prototypes/travel-adapter/verify_google_flights_pricing.py IST CAI 2026-11-20 2026-11-23` (reproducible, 6 requests).
**Files:** every request (API key redacted) and raw provider response is in this folder; `summary.json` lists the comparison.

## 1. Same flights, 1 adult vs 2 adults (one-way searches, USD)

| Direction | Flight | 1 adult | 2 adults | Ratio |
|---|---|---|---|---|
| Outbound IST → CAI 2026-11-20 | SM 304 | $100 | $200 | 2.00 |
| | MS 746 | $160 | $319 | 1.99 |
| | A3 991 + A3 930 | $233 | $418 | **1.79** |
| Return CAI → IST 2026-11-23 | SM 303 | $104 | $226 | **2.17** |
| | MS 745 | $130 | $259 | 1.99 |
| | TK 755 | $180 | $360 | 2.00 |

26 (outbound) and 33 (return) flights appear in both searches; ratios range from 1.79 to 2.21 (full list in `summary.json`).

**Reading:**
- The 2-adult price is the amount for the whole group. A per-person field would not change with the traveler count.
- It is priced by the provider and is not a fixed doubling: for example SM 303 costs $104 for 1 adult but $226 for 2 (ratio 2.17), and A3 991 costs $233 for 1 but $418 for 2 (ratio 1.79). Fare availability per seat changes the group total.

## 2. Provider booking details for the exact itinerary (2 adults)

`getBookingDetails` with the itinerary's `booking_token` (token stored as a hash only):

| Direction | Flight | Search price (2 adults) | Booking option | Booking price |
|---|---|---|---|---|
| Outbound | SM 304 | $200 | Air Cairo (airline) | **$200** |
| Return | SM 303 | $226 | Air Cairo (airline) | **$226** |

The airline's own booking price for the 2-adult itinerary equals the search price, so the search price is the bookable total for both travelers.

## 3. Taxes and mandatory fees

Google's official help page "What does the total price include?" (https://support.google.com/faqs/answer/2736504, read 2026-10-23):

> "Our prices include standard taxes and fees."
> "The airline may charge additional fees, such as baggage fees."

The API returns Google Flights prices; the raw responses have no separate tax field. Checked bags are not included (`bags.checked: 0` in the responses); optional bags are outside the required total.

## 4. Remaining manual check (Google Flights website)

The comparison with the Google Flights website for the same flights and traveler counts has to be done in a browser; it cannot be fetched by script. Steps:

1. Open Google Flights (USD) → One way → IST → CAI → 2026-11-20, set **1 adult**, and screenshot SM 304 and the price note at the bottom ("Prices include required taxes + fees for 1 adult").
2. Same search with **2 adults**, and screenshot SM 304 and the note ("… for 2 adults").
3. Repeat for CAI → IST on 2026-11-23 (SM 303).
4. Save the screenshots in this folder, next to a new run of the script made at the same time.

**Decision rule:**
- If the website shows the same totals with "for 2 adults", the meaning is confirmed and fees stay `included`.
- If it does not, the adapter must report fees as `unknown`, and the meaning must be confirmed with the API provider before it is used in the budget.
