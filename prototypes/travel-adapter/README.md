# Travel Adapter Prototype (API-05 #18 / API-04 #17)

TravelMate travel and AI adapters, shaped for Adel's merged BE-04 models (`backend/app/services/models.py`) and the v0.4 contract in `docs/`. Not yet moved into `backend/app/adapters/`; BE-03 (#9) owns that integration.

## Contents

| Path | Purpose |
|---|---|
| `travalmate.py` | `search_travel` (Booking.com hotels; Google Flights live round trips in `live` mode; Skyscanner only in `indicative` mode) and `generate_itinerary` (Groq structured itinerary), plus a prototype `run_travelmate_engine` for local testing and evidence |
| `test_travelmate_adapters.py` | 95 offline tests (no network, no API quota), validated against BE-04 models and the v0.4 schema, plus the `--live-evidence` generator |
| `tests/fixtures/` | Real provider responses recorded on 2026-10-17, used by the offline tests |
| `evidence/` | Sanitized live evidence chains with SHA-256 manifests (`legacy-prototype-v1/` holds the superseded first runs) |
| `INTEGRATION_GUIDE.md` | **Handoff reference:** input/output schemas with real examples, BE-04 mapping, unavailability states, error and warning codes, keys, FastAPI usage |
| `.env.example` | Required environment variable names (placeholders only) |
| `requirements.txt` | Python dependencies |

## Quick start

```bash
cd prototypes/travel-adapter
pip install -r requirements.txt
python test_travelmate_adapters.py                  # offline tests
cp .env.example .env                                # add your own keys
python test_travelmate_adapters.py --live-evidence  # ONE real run (uses API quota)
```

## Current evidence

`evidence/tm-20261021173211-de83be15`: IST → Cairo, 2026-11-20 → 2026-11-23, 2 adults, flight mode `live`, **19.6 s end to end**.
- **Flights:** two parallel one-way Google Flights searches with real leg prices, SM 304 **$272** + MS 745 **$223** for both travelers, taxes included.
- **Hotels:** 20/20 verified (dates, adults, rooms, location).
- **AI:** itinerary validated (4,413 ms).
- **BE-04:** Adel's `ZiyadReportSlice` validated, and `calculate_budget` ran on the same run (`08_be04_budget_output.json`): provider subtotal 560.75.

Other runs (timeout sample, rejected AI output, flights disabled) are described in `INTEGRATION_GUIDE.md` section 10.

Start with `manifest.json`.

## Known limitations

Live round trips sum two one-way tickets, which can cost more than a single round-trip ticket on some routes. `trip_type: "one_way"` needs a contract extension. See `INTEGRATION_GUIDE.md` sections 2 and 11.
