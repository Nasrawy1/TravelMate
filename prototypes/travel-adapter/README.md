# Travel Adapter Prototype (API-05 #18 / API-04 #17)

Secured prototype of the TravelMate travel and AI adapters, uploaded as step 1 of [#18](https://github.com/Nasrawy1/TravelMate/issues/18).
It is **not yet integrated** into `backend/app/adapters/` and **not yet aligned** with the v0.4 contract in `docs/` (alignment is tracked in PR #25).

## Contents

| Path | Purpose |
|---|---|
| `travalmate.py` | `search_travel` (Booking.com hotels + Skyscanner indicative flights), `generate_itinerary` (Groq structured itinerary) and the `run_travelmate_engine` prototype pipeline |
| `test_travelmate_adapters.py` | 60 offline tests (no network, no API quota) and the `--live-evidence` generator |
| `tests/fixtures/` | Real provider responses recorded on 2026-10-17, used by the offline tests |
| `evidence/` | Sanitized live evidence chains (inputs → raw provider data → normalized context → AI input/output → final response) with SHA-256 manifests |
| `INTEGRATION_GUIDE.md` | Providers, limits, function contracts, error envelope, FastAPI usage, DB/UI mapping and known limitations |
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

## Evidence

| Run | Result |
|---|---|
| `evidence/tm-20261020001307-906a0090` | Successful chain: IST → Cairo, 2026-11-19 → 2026-11-22, 2 adults, 1 room. 20/20 hotels verified (dates, adults, rooms, location); AI itinerary validated (3,793 ms). |
| `evidence/tm-20261019233725-6f31e191` | Real `rate_limited` sample: Booking monthly quota exhausted, handled without key rotation. |

Each run's `manifest.json` lists the chain checks and file hashes. Start with `07_final_response.json` for the final result.

## Known limitations

- Flight quotes are cached, single-adult and date-independent (indicative only); see `INTEGRATION_GUIDE.md` section 2.
- The output shape differs from `docs/contracts/api-v0.4.schema.json`. The differences are listed in PR #25 and wait for agreement under PLAN-02 (#11).
