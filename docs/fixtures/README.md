# TravelMate v0.4 structural fixtures

These are synthetic contract examples, not fetched prices, approved estimate rates or provider-feasibility evidence. Load manifest.json with every response; preserve data_mode=structural_mock and live_evidence=false in UI context. Show DEMO/MOCK visibly. Never feed these into the normal live backend path as provider results.

| File | HTTP | Expected outcome |
|---|---|---|
| request.json | — | 2 adults, 2 nights, USD 1500 |
| within-budget.json | 200 | Provider 950 + estimates 190 = 1140; within_budget |
| over-budget.json | 200 | Same costs, budget 1000; over_budget |
| partial-prices.json | 200 | Hotel/tax 550 + activities 40; total null, uncertain |
| no-prices.json | 200 | No travel offers; activities 40; total null, uncertain |
| known-minimum-over-budget.json | 200 | Known 550 > budget 500; total null, over_budget |
| unknown-taxes.json | 200 | Base provider 900 + estimates 190; unknown tax, total null |
| unauthorized.json | 401 | Sign-in/session action |
| validation-error.json | 422 | Field error |
| ai-failure.json | 502 | Invalid AI output |
| timeout.json | 504 | Generation deadline |
| rate-limited.json | 429 | Retry-After header in manifest |

Each response case includes its matching request in manifest.json. Error HTTP status/headers live in the manifest, not invented response-body fields. All successful examples share a three-day itinerary.

Fixed dates are tested against 2026-10-15 UTC. Real tests must use future dates relative to runtime. Rome/Istanbul are illustrative labels, not verified provider coverage.

Validate without network/provider calls:
```bash
python docs/contracts/validate_fixtures.py
```
Requires Python and the jsonschema package (Draft 2020-12). Validation checks fields/formats plus dates, occupancy, cost references, fees, statuses and arithmetic. Negative mutations prove key invalid states are rejected.

These are development examples; final curated offline demo journeys and actual integration tests remain implementation tasks.
